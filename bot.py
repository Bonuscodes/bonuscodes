import sqlite3
import requests  # Библиотека для получения IP-адреса пользователя
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher import FSMContext
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage  # Подключаем MemoryStorage

API_TOKEN = '8007886958:AAEy-Yob9wAOpDWThKX3vVB0ApJB3E6b3Qc'  # Токен вашего бота
ADMIN_IDS = [781745483]  # Замените на реальные ID администраторов

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()  # Создаем объект MemoryStorage
dp = Dispatcher(bot, storage=storage)  # Указываем хранилище для dispatcher
dp.middleware.setup(LoggingMiddleware())

# Функция для отладки
def debug_print(message):
    print(f"DEBUG: {message}")

# Создаем таблицы в базе данных и добавляем столбцы, если их нет
conn = sqlite3.connect('codes.db')
cursor = conn.cursor()

# Создание таблицы с кодами, если ее нет
cursor.execute('''CREATE TABLE IF NOT EXISTS codes (
                    code TEXT PRIMARY KEY, 
                    site_url TEXT)''')

# Проверяем, есть ли столбец site_url в таблице
cursor.execute('''PRAGMA table_info(codes)''')
columns = [column[1] for column in cursor.fetchall()]
debug_print(f"Текущие столбцы в таблице codes: {columns}")

# Если столбца site_url нет, добавляем его
if 'site_url' not in columns:
    cursor.execute('ALTER TABLE codes ADD COLUMN site_url TEXT')
    debug_print("Столбец site_url был добавлен в таблицу.")
else:
    debug_print("Столбец site_url уже существует.")

# Создаем таблицу для использованных IP
cursor.execute('''CREATE TABLE IF NOT EXISTS used_ips (user_id INTEGER PRIMARY KEY, ip_address TEXT)''')
conn.commit()
conn.close()

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_site = State()

# Функция для добавления кода и сайта в базу данных
def add_code_to_db(code, site_url):
    debug_print(f"Добавление кода: {code}, сайта: {site_url}")
    conn = sqlite3.connect('codes.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO codes (code, site_url) VALUES (?, ?)", (code, site_url))
    conn.commit()
    conn.close()

# Функция для получения IP-адреса пользователя
def get_ip_address(user_id):
    try:
        response = requests.get(f'http://ipinfo.io/{user_id}/json')
        return response.json()['ip']
    except requests.exceptions.RequestException as e:
        debug_print(f"Ошибка при получении IP: {e}")
        return None

# Функция для проверки, был ли код использован с данного IP
def is_code_used_from_ip(ip_address):
    conn = sqlite3.connect('codes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM used_ips WHERE ip_address = ?", (ip_address,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Добавление IP в базу данных
def add_ip_to_db(ip_address, user_id):
    conn = sqlite3.connect('codes.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO used_ips (ip_address, user_id) VALUES (?, ?)", (ip_address, user_id))
    conn.commit()
    conn.close()

# Команда /addcode для администраторов
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
    conn = sqlite3.connect('codes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT code, site_url FROM codes LIMIT 1")
    code = cursor.fetchone()
    if code:
        cursor.execute("DELETE FROM codes WHERE code = ?", (code[0],))  # Удаляем код после использования
        conn.commit()
        conn.close()
        return code
    else:
        conn.close()
        return None

# Проверка, использовался ли код для данного пользователя
def is_code_used(user_id):
    conn = sqlite3.connect('codes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM used_ips WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

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

# Обработчик команды /getcode через кнопку
@dp.callback_query_handler(lambda c: c.data == "get_code")
async def send_code(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Получаем IP-адрес пользователя
    ip_address = get_ip_address(user_id)
    if ip_address is None:
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 Не удалось получить ваш IP-адрес. Попробуйте позже.",
        )
        return

    # Проверяем, использовался ли код с этого IP
    if is_code_used_from_ip(ip_address):
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Вы уже получили код с этого IP-адреса!</b> 🚨\n\n"
            "Каждый IP-адрес может получить код только один раз. Спасибо за понимание! 😊",
            parse_mode=ParseMode.HTML
        )
        return

    code_data = get_code()

    if code_data:
        code, site_url = code_data
        # Красивое сообщение с кодом и кнопкой для перехода на уникальный сайт
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
        add_user(user_id)  # Добавляем пользователя в базу данных как использовавшего код
        add_ip_to_db(ip_address, user_id)  # Добавляем IP в базу данных
    else:
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Коды закончились!</b> 🚨\n\n"
            "К сожалению, все коды использованы. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
