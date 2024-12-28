import sqlite3
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher import FSMContext
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.contrib.fsm_storage.memory import MemoryStorage

API_TOKEN = '8007886958:AAEy-Yob9wAOpDWThKX3vVB0ApJB3E6b3Qc'  # Токен вашего бота
ADMIN_IDS = [781745483]  # Замените на реальные ID администраторов
CHANNEL_ID = "@scattercasinostream"  # Название вашего канала

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()  # Создаем объект MemoryStorage
dp = Dispatcher(bot, storage=storage)  # Указываем хранилище для dispatcher
dp.middleware.setup(LoggingMiddleware())

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Функция для подключения к базе данных
def get_db_connection():
    return sqlite3.connect('codes.db')

# Создание таблиц в базе данных, если их нет
def create_tables():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS codes (
                            code TEXT PRIMARY KEY, 
                            site_url TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS used_ips (user_id INTEGER PRIMARY KEY)''')
        conn.commit()

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_site = State()

# Функция для добавления кода и сайта в базу данных
def add_code_to_db(code, site_url):
    logger.debug(f"Добавление кода: {code}, сайта: {site_url}")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO codes (code, site_url) VALUES (?, ?)", (code, site_url))
        conn.commit()

# Проверка подписки пользователя на канал
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки пользователя {user_id}: {e}")
        return False

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
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT code, site_url FROM codes LIMIT 1")
        code = cursor.fetchone()
        if code:
            cursor.execute("DELETE FROM codes WHERE code = ?", (code[0],))
            conn.commit()
            return code
    return None

# Проверка, использовался ли код для данного пользователя
def is_code_used(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM used_ips WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

# Добавление пользователя в базу данных
def add_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO used_ips (user_id) VALUES (?)", (user_id,))
        conn.commit()

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

    # Проверяем, подписан ли пользователь на канал
    if not await check_subscription(user_id):
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 Чтобы получить код, нужно подписаться на наш канал: https://t.me/scattercasinostream 🚨\n\n"
            "Пожалуйста, подпишитесь на канал, а затем нажмите кнопку 'Получить код' еще раз.",
        )
        return

    if is_code_used(user_id):
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Вы уже получили код!</b> 🚨\n\n"
            "Каждый пользователь может получить код только один раз. Спасибо за понимание! 😊",
            parse_mode=ParseMode.HTML
        )
        return

    code_data = get_code()

    if code_data:
        code, site_url = code_data
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
    else:
        await bot.send_message(
            callback_query.from_user.id,
            "🚨 <b>Коды закончились!</b> 🚨\n\n"
            "К сожалению, все коды использованы. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )

# Команда /viewcodes для администраторов (для просмотра всех кодов)
@dp.message_handler(commands=['viewcodes'])
async def cmd_view_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, site_url FROM codes")
            codes = cursor.fetchall()

        if codes:
            response = "Список всех кодов:\n\n"
            for code, site_url in codes:
                response += f"🔑 Код: <code>{code}</code>\n🌐 Сайт: {site_url}\n\n"
            await message.answer(response, parse_mode=ParseMode.HTML)
        else:
            await message.answer("🚨 Нет доступных кодов в базе данных.")
    else:
        await message.answer("❌ У вас нет прав для использования этой команды.")

# Команда /clearcodes для администраторов (для удаления всех кодов)
@dp.message_handler(commands=['clearcodes'])
async def cmd_clear_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM codes")  # Удаляем все коды из базы данных
            conn.commit()

        await message.answer("✅ Все коды были успешно удалены.")
    else:
        await message.answer("❌ У вас нет прав для использования этой команды.")

# Запуск бота
if __name__ == "__main__":
    create_tables()  # Создание таблиц при запуске бота
    executor.start_polling(dp, skip_updates=True)
