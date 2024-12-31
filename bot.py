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
    code = await get_unique_code()

    if code:
        await callback_query.message.reply(
            f"Ваш уникальный код: {code} 🎟️\n\n"
            "Этот код больше не доступен для получения повторно."
        )
    else:
        await callback_query.message.reply(
            "Извините, все коды были выданы. Пожалуйста, попробуйте позже."
        )

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

    # Удаляем старый вебхук перед установкой нового
    asyncio.run(bot.delete_webhook())  # Удаляем старый вебхук

    # Устанавливаем новый вебхук
    asyncio.run(bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH))  # Устанавливаем новый

    # Запуск приложения с обработкой вебхуков
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook)
    web.run_app(app, host="0.0.0.0", port=10000)
