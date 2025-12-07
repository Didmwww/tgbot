import asyncio
import logging
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientSession # <--- Важный импорт

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8355863525:AAFfUha1BtbUe6KOmAWGK6Rv7oRTpj_rWRI'  # <--- ВСТАВЬ ТОКЕН!
LEADER_TAG = "@KafkaTheTeamLeader"
DB_NAME = 'clients_base.db'

# Логирование
logging.basicConfig(level=logging.INFO)

# --- СПЕЦИАЛЬНАЯ НАСТРОЙКА ДЛЯ PYTHONANYWHERE ---
# Мы создаем свой класс сессии, который принудительно включает работу через прокси
class PythonAnywhereSession(AiohttpSession):
    async def create_session(self, *args, **kwargs) -> ClientSession:
        # trust_env=True заставляет aiohttp читать настройки прокси из системы
        return ClientSession(
            trust_env=True,
            json_serialize=self.json_dumps,
            json_deserialize=self.json_loads
        )

# 1. Задаем адрес прокси в системе
proxy_url = "http://proxy.server:3128"
os.environ["HTTP_PROXY"] = proxy_url
os.environ["HTTPS_PROXY"] = proxy_url

# 2. Используем наш специальный класс
session = PythonAnywhereSession()
bot = Bot(token=API_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, 
                name TEXT,
                age TEXT,
                city TEXT,
                start_date TEXT,
                job TEXT DEFAULT 'Не указано',
                family TEXT DEFAULT 'Не указано',
                hobbies TEXT DEFAULT 'Не указано',
                criminal TEXT DEFAULT 'Не указано',
                credits TEXT DEFAULT 'Не указано',
                notes TEXT DEFAULT 'Нет заметок',
                day1_ind INTEGER DEFAULT 0,
                day2_sphere INTEGER DEFAULT 0,
                day3_warm INTEGER DEFAULT 0,
                day4_analyst INTEGER DEFAULT 0,
                day5_warm INTEGER DEFAULT 0,
                day_pre_transfer INTEGER DEFAULT 0
            )
        ''')
        await db.commit()

# --- МАШИНА СОСТОЯНИЙ ---
class ClientForm(StatesGroup):
    name = State()
    age = State()
    city = State()
    start_date = State()

class RatingForm(StatesGroup):
    waiting_for_photo = State()

class NoteForm(StatesGroup):
    waiting_for_note_text = State()

# --- СПИСОК ЗАДАНИЙ РЕЙТИНГА ---
RATING_TASKS = {
    "1": "Присутствие на брифинге (2б)",
    "2": "Своевременный отчет (2б)",
    "3": "Попросили анализ диалога у ТимЛида (2б)",
    "4": "Сделан вброс (Инд/Сфера/Аналитика) (2б)",
    "5": "Добавлена важность аналитика (2б)",
    "6": "Доброе утро в общий чат до 10:00 (2б)",
    "7": "Найти необычное увлечение у лида (2б)",
    "8": "Расставить личные границы (2б)",
    "9": "Активность на брифинге (3б)",
    "10": "Сделал прогрев (3б)",
    "11": "Полная фильтрация лида (4б)",
    "12": "Обсудить какого партнера ищете (4б)",
    "13": "Вовремя скинутое Д/З (4б)",
    "14": "7+ лидов активной базы > 2 дней (4б)",
    "15": "4 Г/с и 2 ед. контента 3-м лидам (8б)",
    "16": "Задача 'Восстановление' от ТимЛида (10б)"
}

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    kb = [
        [InlineKeyboardButton(text="👥 Мои Клиенты", callback_data="list_clients")],
        [InlineKeyboardButton(text="➕ Добавить клиента", callback_data="add_client")],
        [InlineKeyboardButton(text="🏆 Система рейтинга", callback_data="rating_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def rating_kb():
    buttons = []
    for key, val in RATING_TASKS.items():
        buttons.append([InlineKeyboardButton(text=f"{key}. {val}", callback_data=f"rate_task_{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def client_actions_kb(client_id, data):
    status_icons = ["❌", "✅"]
    kb = [
        [InlineKeyboardButton(text=f"День 1: Индикатор {status_icons[data[12]]}", callback_data=f"toggle_{client_id}_day1_ind")],
        [InlineKeyboardButton(text=f"День 2: Сфера {status_icons[data[13]]}", callback_data=f"toggle_{client_id}_day2_sphere")],
        [InlineKeyboardButton(text=f"День 3: Прогрев {status_icons[data[14]]}", callback_data=f"toggle_{client_id}_day3_warm")],
        [InlineKeyboardButton(text=f"День 4: Аналитик {status_icons[data[15]]}", callback_data=f"toggle_{client_id}_day4_analyst")],
        [InlineKeyboardButton(text=f"День 5: Прогрев {status_icons[data[16]]}", callback_data=f"toggle_{client_id}_day5_warm")],
        [InlineKeyboardButton(text=f"Перед передачей {status_icons[data[17]]}", callback_data=f"toggle_{client_id}_day_pre_transfer")],
        [InlineKeyboardButton(text="📝 Заметки / Инфо", callback_data=f"info_{client_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{client_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="list_clients")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ХЕНДЛЕРЫ: ОСНОВНЫЕ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(f"Привет, {message.from_user.first_name}! Это твоя личная база.", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "main_menu")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu_kb())

# --- ХЕНДЛЕРЫ: ДОБАВЛЕНИЕ КЛИЕНТА ---
@dp.callback_query(F.data == "add_client")
async def start_add_client(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите Имя клиента:")
    await state.set_state(ClientForm.name)
    await callback.answer()

@dp.message(ClientForm.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите возраст:")
    await state.set_state(ClientForm.age)

@dp.message(ClientForm.age)
async def process_age(message: types.Message, state: FSMContext):
    await state.update_data(age=message.text)
    await message.answer("Введите город:")
    await state.set_state(ClientForm.city)

@dp.message(ClientForm.city)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Дата начала общения (например, 07.12.2025):")
    await state.set_state(ClientForm.start_date)

@dp.message(ClientForm.start_date)
async def process_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO clients (user_id, name, age, city, start_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, data['name'], data['age'], data['city'], message.text)
        )
        await db.commit()
    await message.answer(f"Клиент {data['name']} добавлен в твою базу!", reply_markup=main_menu_kb())
    await state.clear()

# --- ХЕНДЛЕРЫ: СПИСОК ---
@dp.callback_query(F.data == "list_clients")
async def show_clients(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, name FROM clients WHERE user_id = ?", (user_id,)) as cursor:
            clients = await cursor.fetchall()
    
    if not clients:
        await callback.message.edit_text("Ваш список клиентов пуст.", reply_markup=main_menu_kb())
        return

    kb_builder = []
    for client in clients:
        kb_builder.append([InlineKeyboardButton(text=client[1], callback_data=f"view_{client[0]}")])
    kb_builder.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text("Ваши личные клиенты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_builder))

@dp.callback_query(F.data.startswith("view_"))
async def view_client(callback: types.CallbackQuery):
    client_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM clients WHERE id = ? AND user_id = ?", (client_id, user_id)) as cursor:
            data = await cursor.fetchone()
    
    if not data:
        await callback.answer("Ошибка доступа или клиент удален.", show_alert=True)
        return

    text = (f"👤 **{data[2]}**\n"
            f"🎂 Возраст: {data[3]}\n"
            f"🏙 Город: {data[4]}\n"
            f"📅 Начало: {data[5]}\n"
            f"-------------------\n"
            f"Статус обработки:")
    await callback.message.edit_text(text, reply_markup=client_actions_kb(client_id, data), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_status(callback: types.CallbackQuery):
    _, client_id, field1, field2 = callback.data.split("_")
    column = f"{field1}_{field2}"
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(f"SELECT {column} FROM clients WHERE id = ? AND user_id = ?", (client_id, user_id)) as cursor:
            res = await cursor.fetchone()
            if not res:
                await callback.answer("Ошибка доступа")
                return
            new_val = 0 if res[0] else 1
        await db.execute(f"UPDATE clients SET {column} = ? WHERE id = ?", (new_val, client_id))
        await db.commit()
        async with db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)) as cursor:
            data = await cursor.fetchone()
    await callback.message.edit_reply_markup(reply_markup=client_actions_kb(client_id, data))

@dp.callback_query(F.data.startswith("delete_"))
async def delete_client(callback: types.CallbackQuery):
    client_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM clients WHERE id = ? AND user_id = ?", (client_id, user_id))
        await db.commit()
    await callback.answer("Клиент удален!")
    await show_clients(callback)

# --- ИНФО И ЗАМЕТКИ ---
@dp.callback_query(F.data.startswith("info_"))
async def show_full_info(callback: types.CallbackQuery):
    client_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM clients WHERE id = ? AND user_id = ?", (client_id, user_id)) as cursor:
            data = await cursor.fetchone()
    if not data: return 
    
    info_text = (f"📂 **Полное досье на {data[2]}:**\n\n"
                 f"📝 **ЗАМЕТКИ:**\n{data[11]}\n\n"
                 f"_(Остальные поля пока по умолчанию)_")
    
    kb = [
        [InlineKeyboardButton(text="✏️ Изменить заметку", callback_data=f"edit_note_{client_id}")],
        [InlineKeyboardButton(text="🔙 К карточке", callback_data=f"view_{client_id}")]
    ]
    await callback.message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("edit_note_"))
async def start_edit_note(callback: types.CallbackQuery, state: FSMContext):
    client_id = callback.data.split("_")[2]
    await state.update_data(client_id=client_id)
    await callback.message.answer("✍️ Напишите новый текст заметки:")
    await state.set_state(NoteForm.waiting_for_note_text)
    await callback.answer()

@dp.message(NoteForm.waiting_for_note_text)
async def save_note(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id = data['client_id']
    user_id = message.from_user.id
    new_note = message.text
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE clients SET notes = ? WHERE id = ? AND user_id = ?", (new_note, client_id, user_id))
        await db.commit()
    await message.answer("✅ Заметка обновлена!")
    await state.clear()
    kb = [[InlineKeyboardButton(text="🔙 К карточке", callback_data=f"view_{client_id}")]]
    await message.answer("Вернуться к клиенту:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- РЕЙТИНГ ---
@dp.callback_query(F.data == "rating_menu")
async def rating_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите выполненное задание:", reply_markup=rating_kb())

@dp.callback_query(F.data.startswith("rate_task_"))
async def process_rating_choice(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    task_name = RATING_TASKS[task_id]
    await state.update_data(task_id=task_id)
    await callback.message.answer(f"Выбрано: {task_name}\n\n📸 Отправь скриншот подтверждения:")
    await state.set_state(RatingForm.waiting_for_photo)
    await callback.answer()

@dp.message(RatingForm.waiting_for_photo, F.photo)
async def process_rating_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['task_id']
    photo_id = message.photo[-1].file_id
    caption = f"✅ Выполнено задание: **№{task_id}**\n👤 Сотрудник: {message.from_user.full_name}\n👉 {LEADER_TAG}"
    await message.answer_photo(photo=photo_id, caption=caption)
    await message.answer("Отчет отправлен!", reply_markup=main_menu_kb())
    await state.clear()

# --- ЗАПУСК ---
async def main():
    await init_db()
    # Сбрасываем старые апдейты, чтобы не было ошибки "query is too old"
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())