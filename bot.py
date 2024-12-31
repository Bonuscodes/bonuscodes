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

logging.basicConfig(level=logging.DEBUG)
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

# Функция для получения всех кодов
async def get_all_codes():
    conn = await get_db_connection()
    codes = await conn.fetch("SELECT code, site_url FROM codes")
    await conn.close()
    return codes

# Функция для добавления нового кода
async def add_code_to_db(code: str, site_url: str):
    conn = await get_db_connection()
    # Проверяем, если код уже существует
    existing_code = await conn.fetchval("SELECT 1 FROM codes WHERE code = $1", code)
    if existing_code:
        await conn.close()
        return False  # Код уже существует
    await conn.execute("INSERT INTO codes (code, site_url) VALUES ($1, $2)", code, site_url)
    await conn.close()
    return True

# Функция для удаления кода
async def delete_code_from_db(code: str):
    conn = await get_db_connection()
    deleted_count = await conn.execute("DELETE FROM codes WHERE code = $1", code)
    await conn.close()
    return deleted_count > 0

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

# Обработчик команды /list_codes
@dp.message_handler(commands=["list_codes"])
async def list_codes(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    codes = await get_all_codes()
    if codes:
        codes_text = "\n".join([f"Код: {code['code']}, URL: {code['site_url']}" for code in codes])
        await message.reply(f"Список всех кодов:\n\n{codes_text}")
    else:
        await message.reply("Нет кодов в базе данных.")

# Обработчик команды /add_code
@dp.message_handler(commands=["add_code"])
async def add_code(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    # Парсим команду для добавления
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        await message.reply("Использование: /add_code <код> <URL>")
        return

    code, site_url = parts[1], parts[2]
    success = await add_code_to_db(code, site_url)

    if success:
        await message.reply(f"Код {code} успешно добавлен.")
    else:
        await message.reply(f"Код {code} уже существует в базе данных.")

# Обработчик команды /delete_code
@dp.message_handler(commands=["delete_code"])
async def delete_code(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    # Парсим команду для удаления
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.reply("Использование: /delete_code <код>")
        return

    code = parts[1]
    success = await delete_code_from_db(code)

    if success:
        await message.reply(f"Код {code} успешно удален.")
    else:
        await message.reply(f"Код {code} не найден в базе данных.")

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
    # Создаем таблицы при старте
    asyncio.run(create_tables())
    
    # Устанавливаем вебхук
    asyncio.run(bot.set_webhook(WEBHOOK_URL + "/webhook"))
    
    # Запуск приложения с обработкой вебхуков
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook)
    web.run_app(app, host="0.0.0.0", port=10000)
