import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher import FSMContext
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

API_TOKEN = '8007886958:AAEy-Yob9wAOpDWThKX3vVB0ApJB3E6b3Qc'  # Токен вашего бота
ADMIN_IDS = [781745483]  # Замените на реальные ID администраторов

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

def debug_print(message):
    print(f"DEBUG: {message}")

def init_db():
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS codes (
                                code TEXT PRIMARY KEY, 
                                site_url TEXT)''')
            
            cursor.execute('''PRAGMA table_info(codes)''')
            columns = [column[1] for column in cursor.fetchall()]
            debug_print(f"Текущие столбцы в таблице codes: {columns}")

            if 'site_url' not in columns:
                cursor.execute('ALTER TABLE codes ADD COLUMN site_url TEXT')
                debug_print("Столбец site_url был добавлен в таблицу.")
            
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
    except sqlite3.Error as e:
        debug_print(f"Ошибка при добавлении пользователя, IP и кода в базу данных: {e}")

# Функция для добавления кода и сайта в базу данных
def add_code_to_db(code, site_url):
    try:
        debug_print(f"Добавление кода: {code}, сайта: {site_url}")
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO codes (code, site_url) VALUES (?, ?)", (code, site_url))
            conn.commit()
    except sqlite3.Error as e:
        debug_print(f"Ошибка при добавлении кода в базу данных: {e}")

# Функция для получения всех кодов из базы данных
def get_all_codes():
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, site_url FROM codes")
            return cursor.fetchall()
    except sqlite3.Error as e:
        debug_print(f"Ошибка при получении всех кодов: {e}")
        return []

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_site = State()

# Обработчик команды /addcode для администраторов
@dp.message_handler(commands=['addcode'])
async def cmd_add_code(message: types.Message):
    if message.from_user.id in ADMIN_IDS:  # Проверка, является ли пользователь администратором
        await message.answer("🔑 Введите код, который нужно добавить:")
        await Form.waiting_for_code.set()  # Переходим в состояние ожидания кода
    else:
        await message.answer("❌ У вас нет прав для использования этой команды.")

# Обработчик для получения кода
@dp.message_handler(state=Form.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip()  # Получаем код
    await state.update_data(code=code)  # Сохраняем код в состояние
    await message.answer(f"✅ Код '{code}' получен. Теперь отправьте ссылку для этого кода:")
    await Form.waiting_for_site.set()  # Переходим в состояние ожидания сайта

# Обработчик для получения сайта
@dp.message_handler(state=Form.waiting_for_site)
async def process_url(message: types.Message, state: FSMContext):
    site_url = message.text.strip()  # Получаем ссылку
    user_data = await state.get_data()  # Получаем сохраненные данные
    code = user_data['code']  # Берем код из данных

    # Добавляем код и сайт в базу данных
    add_code_to_db(code, site_url)

    await message.answer(f"✅ Код '{code}' с сайтом '{site_url}' успешно добавлен в базу данных.")

    # Завершаем состояние
    await state.finish()

# Функция для раздачи кодов с уникальными сайтами
def get_code():
    try:
        with sqlite3.connect('codes.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, site_url FROM codes LIMIT 1")
            code = cursor.fetchone()
            if code:
                cursor.execute("DELETE FROM codes WHERE code = ?", (code[0],))
                conn.commit()
                return code
        return None
    except sqlite3.Error as e:
        debug_print(f"Ошибка при получении кода: {e}")
        return None

# Обработчик команды /start
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    # Интерактивная клавиатура с кнопками
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Получить код 🎟️", callback_data="get_code"))

    await message.reply(
        f"👋 Привет, {message.from_user.first_name}! Я — бот для получения уникальных кодов 🧑‍💻.\n\n"
        "📝 Просто нажми на кнопку, чтобы получить свой код! 🎉\n"
        "🔹 Удачи и не забывай использовать код на нашем сайте! 🔹",
        reply_markup=keyboard
    )

# Обработчик команды /viewcodes для администраторов
@dp.message_handler(commands=["viewcodes"])
async def view_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:  # Проверка, является ли пользователь администратором
        codes = get_all_codes()
        if codes:
            response = "📜 Список доступных кодов:\n\n"
            for code, site_url in codes:
                response += f"<b>Код:</b> {code} - <b>Сайт:</b> {site_url}\n"
            await message.answer(response, parse_mode=ParseMode.HTML)
        else:
            await message.answer("🚨 Нет доступных кодов.")
    else:
        await message.answer("❌ У вас нет прав для использования этой команды.")

# Обработчик команды /getcode через кнопку
@dp.callback_query_handler(lambda c: c.data == "get_code")
async def send_code(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Для теста используем фиктивный IP-адрес
    ip_address = "unknown_ip"  # Здесь замените на реальный IP, если используете webhook

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
        add_user(user_id, ip_address, code)  # Добавляем пользователя, его IP и код в базу данных
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
