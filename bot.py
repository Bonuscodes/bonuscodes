import asyncpg
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiohttp import web
from urllib.parse import urlparse

API_TOKEN = os.getenv('API_TOKEN')
admin_ids_str = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]
CHANNEL_ID = os.getenv('CHANNEL_ID')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST', 'localhost')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

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
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_site = State()

@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Получить код 🎟️", callback_data="get_code"))
    await message.reply(
        f"👋 Привет, {message.from_user.first_name}! Я — бот для получения уникальных кодов 🧑‍💻.\n\n"
        "📝 Просто нажми на кнопку, чтобы получить свой код! 🎉",
        reply_markup=keyboard
    )

WEBHOOK_PATH = '/webhook'

async def webhook(request):
    try:
        json_str = await request.json()
        update = types.Update(**json_str)
        await dp.process_update(update)
        return web.Response()
    except Exception as e:
        logger.error(f"Ошибка в вебхуке: {e}")
        return web.Response(status=500)

if __name__ == "__main__":
    from asyncio import run
    run(create_tables())
    run(bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH))

    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook)
    web.run_app(app, host="0.0.0.0", port=10000)
