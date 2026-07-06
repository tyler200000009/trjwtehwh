# -*- coding: utf-8 -*-
"""
ZCS Tournament Bot v2 — регистрация команд + админка (матчи, рассылка)
aiogram 3.x

Запуск:
1. pip install -r requirements.txt
2. Впиши токен в BOT_TOKEN (или переменную окружения BOT_TOKEN)
3. По желанию поменяй пароль админки ADMIN_PASSWORD (по умолчанию 8989)
4. python bot.py

Вход в админку: отправить боту команду  /admin 8989
Выход из админки: кнопка "⬅️ Выйти из админки"
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# ==================== НАСТРОЙКИ ====================

BOT_TOKEN = os.getenv("8804396220:AAFUGS_bECvk7DnjmOGtf4l4C0Oni1crIMU")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "8989")

DB_PATH = "zcs_teams.db"
TOURNAMENT_NAME = "ZCS Tournament 2x2"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

authenticated_admins: set[int] = set()

# ==================== БАЗА ДАННЫХ ====================


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captain_user_id INTEGER,
            captain_username TEXT,
            team_name TEXT,
            logo_file_id TEXT,
            p1_nick TEXT,
            p1_account TEXT,
            p1_phone TEXT,
            p2_nick TEXT,
            p2_account TEXT,
            p2_phone TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team1_id INTEGER,
            team2_id INTEGER,
            team1_name TEXT,
            team2_name TEXT,
            score1 INTEGER,
            score2 INTEGER,
            winner_name TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
        """
    )
    conn.commit()
    conn.close()


def load_admins_from_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    rows = cur.fetchall()
    conn.close()
    for (uid,) in rows:
        authenticated_admins.add(uid)


def add_admin_to_db(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin_from_db(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def save_team(data: dict, user_id: int, username: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO teams (
            captain_user_id, captain_username, team_name, logo_file_id,
            p1_nick, p1_account, p1_phone,
            p2_nick, p2_account, p2_phone,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
        """,
        (
            user_id,
            username,
            data.get("team_name"),
            data.get("logo_file_id"),
            data.get("p1_nick"),
            data.get("p1_account"),
            data.get("p1_phone"),
            data.get("p2_nick"),
            data.get("p2_account"),
            data.get("p2_phone"),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    team_id = cur.lastrowid
    conn.close()
    return team_id


def get_all_teams():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM teams ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_team(team_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM teams WHERE id=?", (team_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_teams_by_captain(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM teams WHERE captain_user_id=? ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_team(team_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM teams WHERE id=?", (team_id,))
    conn.commit()
    conn.close()


def save_match(team1_id, team2_id, team1_name, team2_name, score1, score2, winner_name) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO matches (team1_id, team2_id, team1_name, team2_name, score1, score2, winner_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            team1_id, team2_id, team1_name, team2_name, score1, score2, winner_name,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    match_id = cur.lastrowid
    conn.close()
    return match_id


def get_matches_for_team(team_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM matches WHERE team1_id=? OR team2_id=? ORDER BY id DESC",
        (team_id, team_id),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_captain_ids() -> list[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT captain_user_id FROM teams")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ==================== FSM СОСТОЯНИЯ ====================


class Registration(StatesGroup):
    team_name = State()
    logo = State()
    p1_nick = State()
    p1_account = State()
    p1_phone = State()
    p2_nick = State()
    p2_account = State()
    p2_phone = State()
    confirm = State()


class MatchAssign(StatesGroup):
    choose_team1 = State()
    choose_team2 = State()
    enter_score = State()
    choose_winner = State()


class Broadcast(StatesGroup):
    waiting_content = State()


# ==================== КЛАВИАТУРЫ (ОБЫЧНЫЕ КНОПКИ ВНИЗУ) ====================


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Регистрация команды")],
            [KeyboardButton(text="👤 Мой профиль")],
        ],
        resize_keyboard=True,
    )


def admin_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список команд")],
            [KeyboardButton(text="⚔️ Назначить матч")],
            [KeyboardButton(text="📢 Уведомление всем")],
            [KeyboardButton(text="⬅️ Выйти из админки")],
        ],
        resize_keyboard=True,
    )


def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def phone_request_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_logo_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="skip_logo")]]
    )


def confirm_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no"),
            ]
        ]
    )


def teams_choice_kb(teams_rows, prefix: str, exclude_id: int | None = None):
    buttons = []
    for row in teams_rows:
        team_id, team_name = row[0], row[3]
        if exclude_id is not None and team_id == exclude_id:
            continue
        buttons.append(
            [InlineKeyboardButton(text=f"#{team_id} {team_name}", callback_data=f"{prefix}_{team_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def winner_choice_kb(team1_id, team1_name, team2_id, team2_name):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏆 {team1_name}", callback_data=f"winner_{team1_id}")],
            [InlineKeyboardButton(text=f"🏆 {team2_name}", callback_data=f"winner_{team2_id}")],
            [InlineKeyboardButton(text="🤝 Ничья", callback_data="winner_draw")],
        ]
    )


# ==================== ХЕЛПЕРЫ ====================


def is_admin(user_id: int) -> bool:
    return user_id in authenticated_admins


def team_card_text(data: dict, captain_username: str | None) -> str:
    return (
        f"🏆 <b>Заявка на {TOURNAMENT_NAME}</b>\n\n"
        f"👥 Команда: <b>{data.get('team_name')}</b>\n"
        f"🎮 Формат: 2 на 2\n\n"
        f"<b>Игрок 1</b>\n"
        f"Ник: {data.get('p1_nick')}\n"
        f"Аккаунт: {data.get('p1_account')}\n"
        f"Телефон: {data.get('p1_phone')}\n\n"
        f"<b>Игрок 2</b>\n"
        f"Ник: {data.get('p2_nick')}\n"
        f"Аккаунт: {data.get('p2_account')}\n"
        f"Телефон: {data.get('p2_phone')}\n\n"
        f"Капитан (Telegram): @{captain_username or 'без username'}"
    )


def team_row_text(row) -> str:
    (
        team_id, cap_id, cap_username, team_name, logo_file_id,
        p1_nick, p1_account, p1_phone,
        p2_nick, p2_account, p2_phone,
        status, created_at,
    ) = row
    return (
        f"📌 Заявка #{team_id} [{status}]\n"
        f"Создана: {created_at}\n\n"
        f"Команда: {team_name}\n"
        f"Капитан: @{cap_username or '—'} (id {cap_id})\n\n"
        f"Игрок 1: {p1_nick} | {p1_account} | {p1_phone}\n"
        f"Игрок 2: {p2_nick} | {p2_account} | {p2_phone}"
    )


async def notify_user(user_id: int, text: str):
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logger.warning(f"Не смог отправить пользователю {user_id}: {e}")


# ==================== СТАРТ / ГЛАВНОЕ МЕНЮ ====================


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Привет! Это регистрация команд на <b>{TOURNAMENT_NAME}</b> — "
        f"турнир по CS в формате 2 на 2.\n\n"
        f"Выбирай на клавиатуре внизу:",
        reply_markup=main_menu_kb(),
    )


@dp.message(F.text == "❌ Отмена", StateFilter("*"))
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    kb = admin_menu_kb() if is_admin(message.from_user.id) else main_menu_kb()
    await message.answer("Отменено.", reply_markup=kb)


# ==================== РЕГИСТРАЦИЯ КОМАНДЫ ====================


@dp.message(F.text == "📝 Регистрация команды")
async def reg_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Registration.team_name)
    await message.answer("Введи <b>название команды</b>:", reply_markup=cancel_kb())


@dp.message(Registration.team_name)
async def reg_team_name(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Название слишком короткое, введи ещё раз:")
        return
    await state.update_data(team_name=message.text.strip())
    await state.set_state(Registration.logo)
    await message.answer(
        "Пришли <b>логотип команды</b> (фото) или нажми «Пропустить»:",
        reply_markup=skip_logo_kb(),
    )


@dp.message(Registration.logo, F.photo)
async def reg_logo_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(logo_file_id=file_id)
    await state.set_state(Registration.p1_nick)
    await message.answer("👤 <b>Игрок 1</b>\nВведи его игровой ник:", reply_markup=cancel_kb())


@dp.callback_query(Registration.logo, F.data == "skip_logo")
async def reg_logo_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(logo_file_id=None)
    await state.set_state(Registration.p1_nick)
    await call.message.answer("👤 <b>Игрок 1</b>\nВведи его игровой ник:", reply_markup=cancel_kb())
    await call.answer()


@dp.message(Registration.logo)
async def reg_logo_wrong(message: Message):
    await message.answer("Пришли фото логотипа или нажми «Пропустить» кнопкой выше.")


@dp.message(Registration.p1_nick)
async def reg_p1_nick(message: Message, state: FSMContext):
    await state.update_data(p1_nick=message.text.strip())
    await state.set_state(Registration.p1_account)
    await message.answer("Ссылка на аккаунт (Steam/Faceit) игрока 1:")


@dp.message(Registration.p1_account)
async def reg_p1_account(message: Message, state: FSMContext):
    await state.update_data(p1_account=message.text.strip())
    await state.set_state(Registration.p1_phone)
    await message.answer(
        "Номер телефона игрока 1 (для связи, если Telegram недоступен). "
        "Отправь кнопкой или напиши вручную:",
        reply_markup=phone_request_kb(),
    )


@dp.message(Registration.p1_phone, F.contact)
async def reg_p1_phone_contact(message: Message, state: FSMContext):
    await state.update_data(p1_phone=message.contact.phone_number)
    await state.set_state(Registration.p2_nick)
    await message.answer("👤 <b>Игрок 2</b>\nВведи его игровой ник:", reply_markup=cancel_kb())


@dp.message(Registration.p1_phone)
async def reg_p1_phone_text(message: Message, state: FSMContext):
    await state.update_data(p1_phone=message.text.strip())
    await state.set_state(Registration.p2_nick)
    await message.answer("👤 <b>Игрок 2</b>\nВведи его игровой ник:", reply_markup=cancel_kb())


@dp.message(Registration.p2_nick)
async def reg_p2_nick(message: Message, state: FSMContext):
    await state.update_data(p2_nick=message.text.strip())
    await state.set_state(Registration.p2_account)
    await message.answer("Ссылка на аккаунт (Steam/Faceit) игрока 2:")


@dp.message(Registration.p2_account)
async def reg_p2_account(message: Message, state: FSMContext):
    await state.update_data(p2_account=message.text.strip())
    await state.set_state(Registration.p2_phone)
    await message.answer(
        "Номер телефона игрока 2 (для связи, если Telegram недоступен). "
        "Отправь кнопкой или напиши вручную:",
        reply_markup=phone_request_kb(),
    )


@dp.message(Registration.p2_phone, F.contact)
async def reg_p2_phone_contact(message: Message, state: FSMContext):
    await state.update_data(p2_phone=message.contact.phone_number)
    await show_confirm(message, state)


@dp.message(Registration.p2_phone)
async def reg_p2_phone_text(message: Message, state: FSMContext):
    await state.update_data(p2_phone=message.text.strip())
    await show_confirm(message, state)


async def show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Registration.confirm)
    text = team_card_text(data, message.from_user.username)
    if data.get("logo_file_id"):
        await message.answer_photo(data["logo_file_id"], caption=text, reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(text, reply_markup=ReplyKeyboardRemove())
    await message.answer("Всё верно?", reply_markup=confirm_kb())


@dp.callback_query(Registration.confirm, F.data == "confirm_yes")
async def confirm_yes(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = call.from_user
    team_id = save_team(data, user.id, user.username)
    await call.message.answer(
        f"✅ Заявка команды <b>{data.get('team_name')}</b> принята!\n"
        f"Номер заявки: #{team_id}\n\n"
        f"Организаторы свяжутся с вами по указанным номерам/Telegram.",
        reply_markup=main_menu_kb(),
    )
    for admin_id in authenticated_admins:
        try:
            admin_text = f"🆕 Новая заявка #{team_id}\n\n" + team_card_text(data, user.username)
            if data.get("logo_file_id"):
                await bot.send_photo(admin_id, data["logo_file_id"], caption=admin_text)
            else:
                await bot.send_message(admin_id, admin_text)
        except Exception as e:
            logger.warning(f"Не смог уведомить админа {admin_id}: {e}")
    await state.clear()
    await call.answer()


@dp.callback_query(Registration.confirm, F.data == "confirm_no")
async def confirm_no(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Регистрация отменена.", reply_markup=main_menu_kb())
    await call.answer()


# ==================== МОЙ ПРОФИЛЬ ====================


@dp.message(F.text == "👤 Мой профиль")
async def my_profile(message: Message):
    teams = get_teams_by_captain(message.from_user.id)
    if not teams:
        await message.answer("У тебя пока нет зарегистрированной команды. Нажми «📝 Регистрация команды».")
        return
    for row in teams:
        team_id = row[0]
        text = team_row_text(row)
        matches = get_matches_for_team(team_id)
        if matches:
            text += "\n\n<b>Матчи:</b>\n"
            for m in matches:
                _, t1, t2, t1n, t2n, s1, s2, winner, created = m
                text += f"{t1n} {s1}:{s2} {t2n} — победитель: {winner}\n"
        logo = row[4]
        if logo:
            await message.answer_photo(logo, caption=text)
        else:
            await message.answer(text)


# ==================== ВХОД / ВЫХОД ИЗ АДМИНКИ ====================


@dp.message(Command("admin"))
async def cmd_admin_login(message: Message):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /admin &lt;пароль&gt;")
        return
    if parts[1] != ADMIN_PASSWORD:
        await message.answer("Неверный пароль.")
        return
    authenticated_admins.add(message.from_user.id)
    add_admin_to_db(message.from_user.id)
    await message.answer("✅ Доступ в админ-панель открыт.", reply_markup=admin_menu_kb())


@dp.message(F.text == "⬅️ Выйти из админки")
async def admin_logout(message: Message, state: FSMContext):
    authenticated_admins.discard(message.from_user.id)
    remove_admin_from_db(message.from_user.id)
    await state.clear()
    await message.answer("Вышел из админ-панели.", reply_markup=main_menu_kb())


# ==================== АДМИНКА: СПИСОК КОМАНД ====================


@dp.message(F.text == "📋 Список команд")
async def admin_list_teams(message: Message):
    if not is_admin(message.from_user.id):
        return
    teams = get_all_teams()
    if not teams:
        await message.answer("Заявок пока нет.")
        return
    text = f"📋 Всего команд: {len(teams)}\n\n"
    for row in teams:
        team_id, _, cap_username, team_name = row[0], row[1], row[2], row[3]
        status = row[11]
        text += f"#{team_id} — {team_name} (@{cap_username or '—'}) [{status}]\n"
    await message.answer(text)


# ==================== АДМИНКА: НАЗНАЧИТЬ МАТЧ ====================


@dp.message(F.text == "⚔️ Назначить матч")
async def match_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    teams = get_all_teams()
    if len(teams) < 2:
        await message.answer("Для матча нужно минимум 2 зарегистрированные команды.")
        return
    await state.set_state(MatchAssign.choose_team1)
    await message.answer("Выбери <b>первую команду</b>:", reply_markup=cancel_kb())
    await message.answer("Список команд:", reply_markup=teams_choice_kb(teams, "t1"))


@dp.callback_query(MatchAssign.choose_team1, F.data.startswith("t1_"))
async def match_choose_team1(call: CallbackQuery, state: FSMContext):
    team1_id = int(call.data.split("_")[1])
    team1 = get_team(team1_id)
    await state.update_data(team1_id=team1_id, team1_name=team1[3])
    teams = get_all_teams()
    await state.set_state(MatchAssign.choose_team2)
    await call.message.answer(f"Команда 1: <b>{team1[3]}</b>\nТеперь выбери <b>вторую команду</b>:")
    await call.message.answer("Список команд:", reply_markup=teams_choice_kb(teams, "t2", exclude_id=team1_id))
    await call.answer()


@dp.callback_query(MatchAssign.choose_team2, F.data.startswith("t2_"))
async def match_choose_team2(call: CallbackQuery, state: FSMContext):
    team2_id = int(call.data.split("_")[1])
    team2 = get_team(team2_id)
    data = await state.get_data()
    await state.update_data(team2_id=team2_id, team2_name=team2[3])
    await state.set_state(MatchAssign.enter_score)
    await call.message.answer(
        f"Матч: <b>{data['team1_name']}</b> vs <b>{team2[3]}</b>\n\n"
        f"Введи счёт в формате <code>2:1</code> (первое число — счёт {data['team1_name']}):"
    )
    await call.answer()


@dp.message(MatchAssign.enter_score)
async def match_enter_score(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "")
    if ":" not in text:
        await message.answer("Формат неверный. Введи так: 2:1")
        return
    left, _, right = text.partition(":")
    if not (left.isdigit() and right.isdigit()):
        await message.answer("Формат неверный. Введи так: 2:1")
        return
    await state.update_data(score1=int(left), score2=int(right))
    data = await state.get_data()
    await state.set_state(MatchAssign.choose_winner)
    await message.answer(
        f"Счёт: {data['team1_name']} {left}:{right} {data['team2_name']}\n\nКто победил?",
        reply_markup=winner_choice_kb(data["team1_id"], data["team1_name"], data["team2_id"], data["team2_name"]),
    )


@dp.callback_query(MatchAssign.choose_winner, F.data.startswith("winner_"))
async def match_choose_winner(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    winner_value = call.data.split("_", 1)[1]
    if winner_value == "draw":
        winner_name = "Ничья"
    elif int(winner_value) == data["team1_id"]:
        winner_name = data["team1_name"]
    else:
        winner_name = data["team2_name"]

    match_id = save_match(
        data["team1_id"], data["team2_id"], data["team1_name"], data["team2_name"],
        data["score1"], data["score2"], winner_name,
    )

    result_text = (
        f"⚔️ <b>Матч #{match_id}</b>\n"
        f"{data['team1_name']} {data['score1']}:{data['score2']} {data['team2_name']}\n"
        f"Победитель: <b>{winner_name}</b>"
    )
    await call.message.answer(result_text, reply_markup=admin_menu_kb())

    team1 = get_team(data["team1_id"])
    team2 = get_team(data["team2_id"])
    if team1:
        await notify_user(team1[1], result_text)
    if team2:
        await notify_user(team2[1], result_text)

    await state.clear()
    await call.answer()


# ==================== АДМИНКА: УВЕДОМЛЕНИЕ ВСЕМ ====================


@dp.message(F.text == "📢 Уведомление всем")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(Broadcast.waiting_content)
    await message.answer(
        "Пришли текст уведомления, или фото с подписью — я разошлю это всем зарегистрированным капитанам.",
        reply_markup=cancel_kb(),
    )


@dp.message(Broadcast.waiting_content, F.photo)
async def broadcast_photo(message: Message, state: FSMContext):
    caption = message.caption or ""
    recipients = get_all_captain_ids()
    sent = 0
    for user_id in recipients:
        try:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=caption)
            sent += 1
        except Exception as e:
            logger.warning(f"Не смог отправить {user_id}: {e}")
    await state.clear()
    await message.answer(f"✅ Разослано {sent} из {len(recipients)} получателям.", reply_markup=admin_menu_kb())


@dp.message(Broadcast.waiting_content, F.text)
async def broadcast_text(message: Message, state: FSMContext):
    recipients = get_all_captain_ids()
    sent = 0
    for user_id in recipients:
        try:
            await bot.send_message(user_id, message.text)
            sent += 1
        except Exception as e:
            logger.warning(f"Не смог отправить {user_id}: {e}")
    await state.clear()
    await message.answer(f"✅ Разослано {sent} из {len(recipients)} получателям.", reply_markup=admin_menu_kb())


# ==================== ЗАПУСК ====================


async def main():
    init_db()
    load_admins_from_db()
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
