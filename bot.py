import asyncpg
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiohttp import web
import asyncio

# Загрузка переменных из окружения
API_TOKEN = os.getenv('API_TOKEN')
admin_ids_str = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]
CHANNEL_ID = os.getenv('CHANNEL_ID')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST', 'localhost')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Проверки на обязательные параметры
if not API_TOKEN:
    raise ValueError("Не задан API_TOKEN")
if not ADMIN_IDS:
    raise ValueError("Не заданы ADMIN_IDS")
if not CHANNEL_ID:
    raise ValueError("Не задан CHANNEL_ID")
if not DB_USER:
    raise ValueError("Не задан DB_USER")
if not DB_PASSWORD:
    raise ValueError("Не задан DB_PASSWORD")
if not DB_NAME:
    raise ValueError("Не задан DB_NAME")
if not WEBHOOK_URL:
    raise ValueError("Не задан WEBHOOK_URL (например, https://ваш-домен.onrender.com)")

bot = Bot(token=API_TOKEN)
Bot.set_current(bot)  # Установить текущий бот
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функции для работы с базой данных
async def get_db_connection():
    return await asyncpg.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        host=DB_HOST,
    )

async def create_tables():
    conn = await get_db_connection()
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY, 
            site_url TEXT
        )
    ''')
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS used_ips (
            user_id INTEGER PRIMARY KEY,
            ip_address TEXT
        )
    ''')
    await conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_used_ips_user_id ON used_ips (user_id);
    ''')
    await conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_codes_code ON codes (code);
    ''')
    await conn.close()

# Функция для получения уникального кода
async def get_unique_code():
    conn = await get_db_connection()
    code = await conn.fetchval("SELECT code FROM codes LIMIT 1")  # Получаем первый доступный код
    if code:
        await conn.execute("DELETE FROM codes WHERE code = $1", code)  # Удаляем код из базы после выдачи
    await conn.close()
    return code

# Состояния для машины состояний
class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_site = State()

# Обработчик команды /start
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Получить код 🎟️", callback_data="get_code"))
    await message.reply(
        f"👋 Привет, {message.from_user.first_name}! Я — бот для получения уникальных кодов 🧑‍💻.\n\n"
        "📝 Просто нажми на кнопку, чтобы получить свой код! 🎉",
        reply_markup=keyboard
    )

# Обработчик callback на кнопку получения кода
@dp.callback_query_handler(text="get_code")
async def send_code(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    logger.info(f"Получение кода для пользователя {user_id}")

    code = await get_unique_code()

    logger.info(f"Код для пользователя {user_id}: {code}")

    if code:
        await callback_query.message.reply(
            f"Ваш уникальный код: {code} 🎟️\n\n"
            "Этот код больше не доступен для получения повторно."
        )
    else:
        await callback_query.message.reply(
            "Извините, все коды были выданы. Пожалуйста, попробуйте позже."
        )

# Команда для администраторов: Добавить код
@dp.message_handler(commands=['add_code'])
async def add_code(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав для добавления кода.")
        return

    # Получаем аргумент (код и URL сайта)
    try:
        text = message.text.strip().split(maxsplit=1)[1]
        code, site_url = text.split(',')
        conn = await get_db_connection()
        await conn.execute("INSERT INTO codes (code, site_url) VALUES ($1, $2)", code, site_url)
        await conn.close()
        await message.reply(f"Код {code} успешно добавлен!")
    except IndexError:
        await message.reply("Ошибка! Использование: /add_code <код>, <сайт>")
    except ValueError:
        await message.reply("Ошибка! Формат должен быть: <код>, <сайт>")

# Команда для администраторов: Просмотр всех кодов
@dp.message_handler(commands=['view_codes'])
async def view_codes(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав для просмотра кодов.")
        return

    conn = await get_db_connection()
    rows = await conn.fetch("SELECT code, site_url FROM codes")
    await conn.close()

    if rows:
        codes_list = "\n".join([f"{row['code']} - {row['site_url']}" for row in rows])
        await message.reply(f"Все коды:\n{codes_list}")
    else:
        await message.reply("Нет доступных кодов.")

# Команда для администраторов: Удалить код
@dp.message_handler(commands=['delete_code'])
async def delete_code(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав для удаления кода.")
        return

    # Получаем код для удаления
    try:
        code = message.text.strip().split(maxsplit=1)[1]
        conn = await get_db_connection()
        result = await conn.fetch("DELETE FROM codes WHERE code = $1 RETURNING code", code)

        if result:
            await conn.close()
            await message.reply(f"Код {code} успешно удален.")
        else:
            await conn.close()
            await message.reply(f"Код {code} не найден.")
    except IndexError:
        await message.reply("Ошибка! Использование: /delete_code <код>")

# Вебхук для приема обновлений
WEBHOOK_PATH = '/webhook'

async def webhook(request):
    try:
        json_str = await request.json()
        update = types.Update(**json_str)
        await dp.process_update(update)
        return web.Response()
    except Exception as e:
        logger.exception("Ошибка в вебхуке")  # Подробное логирование
        return web.Response(status=500)

if __name__ == "__main__":
    asyncio.run(create_tables())  # Создаем таблицы при старте
    
    # Устанавливаем вебхук
    asyncio.run(bot.set_webhook(WEBHOOK_URL + "/webhook"))  # Устанавливаем вебхук
    
    # Запуск приложения с обработкой вебхуков
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook)
    web.run_app(app, host="0.0.0.0", port=10000)
