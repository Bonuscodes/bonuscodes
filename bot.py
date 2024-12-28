import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher import FSMContext
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

API_TOKEN = 'YOUR_BOT_API_TOKEN'
ADMIN_IDS = [781745483]  # Замените на реальные ID администраторов

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Логирование для отладки
def debug_print(message):
    print(f"DEBUG: {message}")

def init_db():
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS codes (
                                code TEXT PRIMARY KEY, 
                                site_url TEXT)''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS used_codes (
                                user_id INTEGER, 
                                ip_address TEXT,
                                code TEXT,
                                PRIMARY KEY (user_id, ip_address, code))''')
            conn.commit()
    except sqlite3.Error as e:
        debug_print(f"Ошибка при инициализации базы данных: {e}")

# Проверка, использовался ли код для данного пользователя и IP
def is_code_used(user_id, ip_address, code):
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM used_codes WHERE user_id = ? AND ip_address = ? AND code = ?", 
                           (user_id, ip_address, code))
            result = cursor.fetchone()
            if result:
                debug_print(f"Код уже использовался: {code} для пользователя {user_id} с IP {ip_address}")
            return result is not None
    except sqlite3.Error as e:
        debug_print(f"Ошибка при проверке использования кода: {e}")
        return False

# Добавление пользователя, его IP и кода в базу данных
def add_user(user_id, ip_address, code):
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO used_codes (user_id, ip_address, code) VALUES (?, ?, ?)", 
                           (user_id, ip_address, code))
            conn.commit()
            debug_print(f"Добавлен пользователь {user_id}, IP {ip_address}, код {code}")
    except sqlite3.Error as e:
        debug_print(f"Ошибка при добавлении пользователя, IP и кода в базу данных: {e}")

# Функция для получения и удаления кода
def get_code():
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, site_url FROM codes LIMIT 1")
            code = cursor.fetchone()
            if code:
                # Удаляем код после его использования
                cursor.execute("DELETE FROM codes WHERE code = ?", (code[0],))
                conn.commit()
                debug_print(f"Код {code[0]} выдан и удален из базы данных")
                return code
        return None
    except sqlite3.Error as e:
        debug_print(f"Ошибка при получении кода: {e}")
        return None

# Обработчик команды /start
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Получить код 🎟️", callback_data="get_code"))

    await message.reply(
        f"👋 Привет, {message.from_user.first_name}! Я — бот для получения уникальных кодов 🧑‍💻.\n\n"
        "📝 Просто нажми на кнопку, чтобы получить свой код! 🎉\n"
        "🔹 Удачи и не забывай использовать код на нашем сайте! 🔹",
        reply_markup=keyboard
    )

# Обработчик команды /getcode через кнопку
@dp.callback_query_handler(lambda c: c.data == "get_code")
async def send_code(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Получаем реальный IP-адрес пользователя
    ip_address = callback_query.from_user.language_code  # Здесь замените на реальный IP через webhooks, если используете

    code_data = get_code()

    if code_data:
        code, site_url = code_data

        # Проверяем, использовался ли код этим пользователем и IP
        if is_code_used(user_id, ip_address, code):  
            await bot.send_message(
                callback_query.from_user.id,
                "🚨 <b>Вы уже получили код!</b> 🚨\n\n"
                "Каждый пользователь может получить код только один раз с одного IP. Спасибо за понимание! 😊",
                parse_mode=ParseMode.HTML
            )
            return

        # Красивое сообщение с кодом и кнопкой для перехода на сайт
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Перейти на сайт 🌐", url=site_url)
        )
        await bot.send_message(
            callback_query.from_user.id,
            f"<b>Ваш уникальный код:</b> <code>{code}</code>\n\n"
            f"🎉 Наслаждайтесь! Приятных покупок! 💸\n"
            f"Переходите на наш сайт: {site_url}",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        
        # Сохраняем пользователя, его IP и код в базу данных как использованный
        add_user(user_id, ip_address, code)
    else:
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Коды закончились!</b> 🚨\n\n"
            "К сожалению, все коды использованы. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )

# Запуск бота
if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
