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
from aiogram.utils.exceptions import ChatNotFound

# Загрузка переменных из окружения
API_TOKEN = os.getenv('API_TOKEN')
admin_ids_str = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Канал для проверки подписки
CHANNEL_LINK = "https://t.me/scattercasinostream"  # Ссылка на ваш канал
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

async def get_unique_code():
    conn = await get_db_connection()
    result = await conn.fetchrow("SELECT code, site_url FROM codes LIMIT 1")  # Получаем первый доступный код и сайт
    if result:
        await conn.execute("DELETE FROM codes WHERE code = $1", result['code'])  # Удаляем код из базы после выдачи
    await conn.close()
    return result

# Состояния для машины состояний
class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_site = State()

# Проверка подписки на канал
async def check_subscription(user_id: int):
    try:
        # Задержка перед проверкой подписки (2 секунды)
        await asyncio.sleep(2)
        
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        # Логируем статус пользователя
        logger.debug(f"User {user_id} status in channel: {member.status}")
        
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except ChatNotFound:
        logger.error(f"Channel not found or user {user_id} is not a member of the channel")
        return False
    except Exception as e:
        logger.error(f"Error checking subscription for user {user_id}: {str(e)}")
        return False

# Проверка IP-адреса
async def check_ip(user_id: int, ip_address: str):
    conn = await get_db_connection()
    exists = await conn.fetchval("SELECT 1 FROM used_ips WHERE user_id = $1 AND ip_address = $2", user_id, ip_address)
    await conn.close()
    return exists is not None

# Команды для администратора
@dp.message_handler(commands=["add_code"], user_id=ADMIN_IDS)
async def add_code(message: types.Message):
    # Получение кода и URL сайта от администратора
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        await message.reply("Использование: /add_code <код> <сайт>")
        return
    
    code, site_url = parts[1], parts[2]
    
    conn = await get_db_connection()
    await conn.execute("INSERT INTO codes (code, site_url) VALUES ($1, $2)", code, site_url)
    await conn.close()
    
    await message.reply(f"Код {code} успешно добавлен!")

@dp.message_handler(commands=["show_codes"], user_id=ADMIN_IDS)
async def show_codes(message: types.Message):
    conn = await get_db_connection()
    codes = await conn.fetch("SELECT * FROM codes")
    await conn.close()

    if not codes:
        await message.reply("Нет доступных кодов.")
        return

    code_list = "\n".join([f"Код: {code['code']} - Сайт: {code['site_url']}" for code in codes])
    await message.reply(f"Список кодов:\n{code_list}")

@dp.message_handler(commands=["delete_code"], user_id=ADMIN_IDS)
async def delete_code(message: types.Message):
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.reply("Использование: /delete_code <код>")
        return
    
    code = parts[1]
    
    conn = await get_db_connection()
    result = await conn.execute("DELETE FROM codes WHERE code = $1", code)
    await conn.close()
    
    if result == "DELETE 0":
        await message.reply(f"Код {code} не найден.")
    else:
        await message.reply(f"Код {code} успешно удален!")

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
    ip_address = callback_query.message.chat.id  # Примечание: реальный способ получения IP-адреса зависит от конфигурации
    
    # Проверка подписки на канал
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await callback_query.message.reply(
            f"Для получения кода необходимо подписаться на канал! 🎉\n\n"
            f"Подпишитесь на канал: {CHANNEL_LINK}"
        )
        return

    # Проверка, получил ли пользователь уже код
    conn = await get_db_connection()
    already_received = await conn.fetchval("SELECT 1 FROM used_ips WHERE user_id = $1", user_id)
    if already_received:
        await callback_query.message.reply(
            "Вы уже получили свой код!"
        )
        return

    # Проверка на уникальность IP-адреса
    ip_exists = await check_ip(user_id, ip_address)
    if ip_exists:
        await callback_query.message.reply(
            "С этого IP-адреса уже был выдан код. Попробуйте с другого устройства!"
        )
        return

    # Выдача уникального кода и сайта
    result = await get_unique_code()
    if result:
        code = result['code']
        site_url = result['site_url']
        
        await callback_query.message.reply(
            f"Ваш уникальный код: {code} 🎟️\n\n"
            f"Сайт для использования кода: {site_url}\n\n"
            "Этот код больше не доступен для получения повторно."
        )
        
        # Сохраняем данные в базе о том, что пользователь получил код и его IP
        await conn.execute("INSERT INTO used_ips (user_id, ip_address) VALUES ($1, $2)", user_id, ip_address)
        await conn.close()
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
    
    # Устанавливаем вебхук
    asyncio.run(bot.set_webhook(WEBHOOK_URL + "/webhook"))
    
    # Запуск приложения с обработкой вебхуков
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook)
    web.run_app(app, host="0.0.0.0", port=10000)
