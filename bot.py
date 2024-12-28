import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage  # Используем хранилище

# Настроим логгирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = '8007886958:AAEy-Yob9wAOpDWThKX3vVB0ApJB3E6b3Qc'  # Токен вашего бота
ADMIN_IDS = [781745483]  # Замените на реальные ID администраторов

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()  # Создаем объект MemoryStorage
dp = Dispatcher(bot, storage=storage)  # Указываем хранилище для dispatcher

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
cursor.execute('''CREATE TABLE IF NOT EXISTS used_ips (user_id INTEGER PRIMARY KEY)''')
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
        cursor.execute("DELETE FROM codes WHERE code = ?", (code[0],))
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

# Добавление пользователя в базу данных
def add_user(user_id):
    conn = sqlite3.connect('codes.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO used_ips (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

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

    if is_code_used(user_id):
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Вы уже получили код!</b> 🚨\n\n"
            "Каждый пользователь может получить код только один раз. Спасибо за понимание! 😊",
            parse_mode="HTML"
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
            parse_mode="HTML",
            reply_markup=keyboard
        )
        add_user(user_id)  # Добавляем пользователя в базу данных как использовавшего код
    else:
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Коды закончились!</b> 🚨\n\n"
            "К сожалению, все коды использованы. Попробуйте позже.",
            parse_mode="HTML"
        )

# Команда /viewcodes для администраторов (для просмотра всех кодов)
@dp.message_handler(commands=['viewcodes'])
async def cmd_view_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:  # Проверка, является ли пользователь администратором
        conn = sqlite3.connect('codes.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, site_url FROM codes")  # Получаем все коды и ссылки
        codes = cursor.fetchall()
        conn.close()

        if codes:
            response = "Список всех кодов:\n\n"
            for code, site_url in codes:
                response += f"🔑 Код: <code>{code}</code>\n🌐 Сайт: {site_url}\n\n"
            await message.answer(response, parse_mode="HTML")
        else:
            await message.answer("🚨 Нет доступных кодов в базе данных.")
    else:
        await message.answer("❌ У вас нет прав для использования этой команды.")

# Команда /clearcodes для администраторов (для удаления всех кодов)
@dp.message_handler(commands=['clearcodes'])
async def cmd_clear_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:  # Проверка, является ли пользователь администратором
        conn = sqlite3.connect('codes.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM codes")  # Удаляем все коды из базы данных
        conn.commit()
        conn.close()

        await message.answer("✅ Все коды были успешно удалены.")
    else:
        await message.answer("❌ У вас нет прав для использования этой команды.")

# Запуск бота
if __name__ == "__main__":
    dp.run_polling(skip_updates=True)
