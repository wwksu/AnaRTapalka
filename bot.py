import asyncio
import hashlib
import hmac
import json
import os
import random
import sqlite3
import time
from urllib.parse import parse_qsl

import psycopg2
from psycopg2 import pool as pg_pool
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiohttp import web

# Security and gameplay constants
MAX_CLICKS_PER_SECOND = 20
AUTOCLICK_BAN_MS = 2 * 60 * 1000
AUTH_MAX_AGE_SECONDS = 24 * 60 * 60

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "1254600026"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
PG_POOL = None


def get_db_connection():
    if DATABASE_URL:
        if PG_POOL is None:
            raise RuntimeError("PostgreSQL pool is not initialized")
        conn = PG_POOL.getconn()
        conn.autocommit = True
        return conn
    return sqlite3.connect("users.db")


def close_db_connection(conn):
    if DATABASE_URL:
        if PG_POOL is not None:
            PG_POOL.putconn(conn)
        return
    conn.close()


def _sqlite_column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def init_db():
    global PG_POOL
    if DATABASE_URL and PG_POOL is None:
        PG_POOL = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=int(os.getenv("DB_POOL_MAX", "20")),
            dsn=DATABASE_URL,
            sslmode="require",
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    if DATABASE_URL:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                coins REAL DEFAULT 0,
                energy REAL DEFAULT 1000,
                max_energy INTEGER DEFAULT 1000,
                multi_tap_level INTEGER DEFAULT 1,
                energy_level INTEGER DEFAULT 1,
                auto_tap_level INTEGER DEFAULT 0,
                skin_bought BOOLEAN DEFAULT FALSE,
                last_update BIGINT DEFAULT 0,
                username TEXT DEFAULT 'Аноним',
                first_name TEXT DEFAULT 'Игрок',
                ban_end_time BIGINT DEFAULT 0,
                tap_window_start BIGINT DEFAULT 0,
                tap_count INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_end_time BIGINT DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tap_window_start BIGINT DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tap_count INTEGER DEFAULT 0")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_coins_desc ON users (coins DESC)")
    else:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                coins REAL DEFAULT 0,
                energy REAL DEFAULT 1000,
                max_energy INTEGER DEFAULT 1000,
                multi_tap_level INTEGER DEFAULT 1,
                energy_level INTEGER DEFAULT 1,
                auto_tap_level INTEGER DEFAULT 0,
                skin_bought INTEGER DEFAULT 0,
                last_update INTEGER DEFAULT 0,
                username TEXT DEFAULT 'Аноним',
                first_name TEXT DEFAULT 'Игрок',
                ban_end_time INTEGER DEFAULT 0,
                tap_window_start INTEGER DEFAULT 0,
                tap_count INTEGER DEFAULT 0
            )
            """
        )
        if not _sqlite_column_exists(cursor, "users", "ban_end_time"):
            cursor.execute("ALTER TABLE users ADD COLUMN ban_end_time INTEGER DEFAULT 0")
        if not _sqlite_column_exists(cursor, "users", "tap_window_start"):
            cursor.execute("ALTER TABLE users ADD COLUMN tap_window_start INTEGER DEFAULT 0")
        if not _sqlite_column_exists(cursor, "users", "tap_count"):
            cursor.execute("ALTER TABLE users ADD COLUMN tap_count INTEGER DEFAULT 0")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_coins_desc ON users (coins DESC)")

    conn.commit()
    close_db_connection(conn)


def _fetch_user_row(cursor, user_id: str, for_update: bool = False):
    if DATABASE_URL:
        query = "SELECT * FROM users WHERE user_id = %s"
        if for_update:
            query += " FOR UPDATE"
    else:
        query = "SELECT * FROM users WHERE user_id = ?"
    cursor.execute(query, (user_id,))
    return cursor.fetchone()


def _insert_user(cursor, user_id: str, username: str, first_name: str):
    if DATABASE_URL:
        cursor.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_update)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, username, first_name, int(time.time() * 1000)),
        )
    else:
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_update)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, first_name, int(time.time() * 1000)),
        )


def _row_to_data(row):
    return {
        "coins": float(row[1]),
        "energy": float(row[2]),
        "max_energy": int(row[3]),
        "multi_tap_level": int(row[4]),
        "energy_level": int(row[5]),
        "auto_tap_level": int(row[6]),
        "skin_bought": bool(row[7]),
        "last_update": int(row[8]),
        "username": row[9] or "Аноним",
        "first_name": row[10] or "Игрок",
        "ban_end_time": int(row[11]) if len(row) > 11 else 0,
        "tap_window_start": int(row[12]) if len(row) > 12 else 0,
        "tap_count": int(row[13]) if len(row) > 13 else 0,
    }


def _save_user(cursor, user_id: str, data: dict):
    if DATABASE_URL:
        cursor.execute(
            """
            UPDATE users SET
                coins = %s,
                energy = %s,
                max_energy = %s,
                multi_tap_level = %s,
                energy_level = %s,
                auto_tap_level = %s,
                skin_bought = %s,
                last_update = %s,
                username = %s,
                first_name = %s,
                ban_end_time = %s,
                tap_window_start = %s,
                tap_count = %s
            WHERE user_id = %s
            """,
            (
                data["coins"],
                data["energy"],
                data["max_energy"],
                data["multi_tap_level"],
                data["energy_level"],
                data["auto_tap_level"],
                bool(data["skin_bought"]),
                data["last_update"],
                data["username"],
                data["first_name"],
                data["ban_end_time"],
                data["tap_window_start"],
                data["tap_count"],
                user_id,
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE users SET
                coins = ?,
                energy = ?,
                max_energy = ?,
                multi_tap_level = ?,
                energy_level = ?,
                auto_tap_level = ?,
                skin_bought = ?,
                last_update = ?,
                username = ?,
                first_name = ?,
                ban_end_time = ?,
                tap_window_start = ?,
                tap_count = ?
            WHERE user_id = ?
            """,
            (
                data["coins"],
                data["energy"],
                data["max_energy"],
                data["multi_tap_level"],
                data["energy_level"],
                data["auto_tap_level"],
                int(bool(data["skin_bought"])),
                data["last_update"],
                data["username"],
                data["first_name"],
                data["ban_end_time"],
                data["tap_window_start"],
                data["tap_count"],
                user_id,
            ),
        )


def _apply_passive_progress(data: dict, now_ms: int):
    last_update = int(data.get("last_update", 0))
    if last_update <= 0:
        data["last_update"] = now_ms
        return

    elapsed_seconds = max(0.0, (now_ms - last_update) / 1000)
    if elapsed_seconds > 0:
        data["energy"] = min(data["max_energy"], data["energy"] + elapsed_seconds)
    data["last_update"] = now_ms


def get_user_data(user_id: str, username: str | None = None, first_name: str | None = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    _insert_user(cursor, user_id, username or "Аноним", first_name or "Игрок")
    row = _fetch_user_row(cursor, user_id)
    if row is None:
        conn.commit()
        close_db_connection(conn)
        raise RuntimeError("User could not be created")

    data = _row_to_data(row)
    if username:
        data["username"] = username
    if first_name:
        data["first_name"] = first_name

    now_ms = int(time.time() * 1000)
    _apply_passive_progress(data, now_ms)

    conn.commit()
    close_db_connection(conn)
    return data


def process_user_action(user_id: str, action: str, username: str | None = None, first_name: str | None = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if DATABASE_URL:
            cursor.execute("BEGIN")
            row = _fetch_user_row(cursor, user_id, for_update=True)
        else:
            cursor.execute("BEGIN IMMEDIATE")
            row = _fetch_user_row(cursor, user_id)

        if row is None:
            _insert_user(cursor, user_id, username or "Аноним", first_name or "Игрок")
            row = _fetch_user_row(cursor, user_id, for_update=bool(DATABASE_URL))
            if row is None:
                raise RuntimeError("User creation failed")

        data = _row_to_data(row)
        if username:
            data["username"] = username
        if first_name:
            data["first_name"] = first_name

        now_ms = int(time.time() * 1000)
        _apply_passive_progress(data, now_ms)

        event = {"status": "ok"}

        if action == "tap":
            if data["ban_end_time"] > now_ms:
                event = {
                    "status": "banned",
                    "ban_end_time": data["ban_end_time"],
                }
            else:
                if now_ms - data["tap_window_start"] >= 1000:
                    data["tap_window_start"] = now_ms
                    data["tap_count"] = 1
                else:
                    data["tap_count"] += 1

                if data["tap_count"] > MAX_CLICKS_PER_SECOND:
                    data["ban_end_time"] = now_ms + AUTOCLICK_BAN_MS
                    data["tap_count"] = 0
                    event = {
                        "status": "banned",
                        "ban_end_time": data["ban_end_time"],
                    }
                elif data["energy"] < 1:
                    event = {"status": "no_energy"}
                else:
                    data["energy"] -= 1
                    is_combo = random.random() < 0.05
                    multiplier = 4 if is_combo else 1
                    coins_earned = data["multi_tap_level"] * multiplier
                    data["coins"] += coins_earned
                    event = {
                        "status": "ok",
                        "coins_earned": coins_earned,
                        "is_combo": is_combo,
                    }

        elif action == "buy_multitap":
            price = int(100 * (1.2 ** (data["multi_tap_level"] - 1)))
            if data["coins"] < price:
                event = {"status": "not_enough_coins", "required": price}
            else:
                data["coins"] -= price
                data["multi_tap_level"] += 1

        elif action == "buy_energy":
            price = int(200 * (1.2 ** (data["energy_level"] - 1)))
            if data["coins"] < price:
                event = {"status": "not_enough_coins", "required": price}
            else:
                data["coins"] -= price
                data["energy_level"] += 1
                data["max_energy"] += 500
                data["energy"] = data["max_energy"]

        elif action == "buy_autotap":
            event = {"status": "feature_disabled"}

        elif action == "buy_skin":
            if data["skin_bought"]:
                event = {"status": "already_bought"}
            elif data["coins"] < 1000:
                event = {"status": "not_enough_coins", "required": 1000}
            else:
                data["coins"] -= 1000
                data["skin_bought"] = True

        else:
            event = {"status": "invalid_action"}

        data["last_update"] = now_ms
        _save_user(cursor, user_id, data)
        conn.commit()
        return {"event": event, "data": data}
    except Exception:
        conn.rollback()
        raise
    finally:
        close_db_connection(conn)


def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, username, first_name, coins, multi_tap_level
        FROM users
        ORDER BY coins DESC
        LIMIT 100
        """
    )
    rows = cursor.fetchall()
    close_db_connection(conn)
    return [
        {
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "coins": float(row[3]),
            "multi_tap_level": int(row[4]),
        }
        for row in rows
    ]


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def verify_telegram_init_data(init_data_raw: str):
    if not init_data_raw:
        return None

    pairs = dict(parse_qsl(init_data_raw, keep_blank_values=True))
    data_hash = pairs.pop("hash", None)
    if not data_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, data_hash):
        return None

    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date <= 0:
        return None
    if time.time() - auth_date > AUTH_MAX_AGE_SECONDS:
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    if "id" not in user:
        return None

    return user


def get_verified_webapp_user(request: web.Request):
    init_data_raw = request.headers.get("X-Telegram-Init-Data", "")
    return verify_telegram_init_data(init_data_raw)


async def run_blocking(func, *args):
    return await asyncio.to_thread(func, *args)


def _build_start_keyboard():
    if WEBAPP_URL.startswith("https://"):
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🐹 Открыть Анара", web_app=WebAppInfo(url=WEBAPP_URL))]]
        )
    return None


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = _build_start_keyboard()

    admin_text = ""
    if is_admin(message.from_user.id):
        admin_text = "\n\n👑 Админ-команды:\n/admin - панель управления"

    text = "Добро пожаловать в Анар тап!\n\nТапай и прокачивайся!"
    if keyboard is None:
        text += "\n\n⚠️ WEBAPP_URL не настроен (нужен https://...)"

    await message.answer(f"{text}{admin_text}", reply_markup=keyboard)


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде")
        return

    def _admin_stats():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(coins) FROM users")
        total_coins = cursor.fetchone()[0] or 0
        cursor.execute("SELECT first_name, coins FROM users ORDER BY coins DESC LIMIT 1")
        top_user = cursor.fetchone()
        close_db_connection(conn)
        return total_users, total_coins, top_user

    total_users, total_coins, top_user = await run_blocking(_admin_stats)

    admin_text = (
        "👑 АДМИН-ПАНЕЛЬ\n\n"
        f"📊 Статистика:\n"
        f"• Всего игроков: {total_users}\n"
        f"• Всего монет: {int(float(total_coins))}\n"
        f"• Топ игрок: {top_user[0] if top_user else 'Нет'} ({int(float(top_user[1])) if top_user else 0} монет)\n\n"
        "📝 Команды:\n"
        "/users - список всех пользователей\n"
        "/give [user_id] [монеты] - выдать монеты\n"
        "/reset [user_id] - сбросить прогресс\n"
        "/ban [user_id] [минуты] - забанить пользователя\n"
        "/stats [user_id] - статистика игрока\n"
        "/broadcast [текст] - рассылка всем"
    )
    await message.answer(admin_text)


@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    def _get_users():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, first_name, coins, multi_tap_level
            FROM users
            ORDER BY coins DESC
            LIMIT 50
            """
        )
        result = cursor.fetchall()
        close_db_connection(conn)
        return result

    users = await run_blocking(_get_users)

    if not users:
        await message.answer("Пользователей пока нет")
        return

    text = "👥 Топ-50 пользователей:\n\n"
    for i, (user_id, name, coins, level) in enumerate(users, 1):
        text += f"{i}. {name} (ID: {user_id})\n   💰 {int(float(coins))} монет | 👆 Ур.{level}\n\n"
    await message.answer(text)


@dp.message(Command("give"))
async def cmd_give(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) < 3:
            await message.answer("Использование: /give [user_id] [монеты]")
            return

        user_id = args[1]
        coins = float(args[2])
        if coins <= 0:
            await message.answer("❌ Количество монет должно быть больше 0")
            return

        def _give():
            conn = get_db_connection()
            cursor = conn.cursor()
            query = "SELECT coins, first_name FROM users WHERE user_id = %s" if DATABASE_URL else "SELECT coins, first_name FROM users WHERE user_id = ?"
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            if not user:
                close_db_connection(conn)
                return None
            new_coins = float(user[0]) + coins
            update_q = "UPDATE users SET coins = %s WHERE user_id = %s" if DATABASE_URL else "UPDATE users SET coins = ? WHERE user_id = ?"
            cursor.execute(update_q, (new_coins, user_id))
            conn.commit()
            close_db_connection(conn)
            return user, new_coins

        result = await run_blocking(_give)
        if result is None:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return

        user, new_coins = result
        await message.answer(
            f"✅ Выдано {int(coins)} монет пользователю {user[1]}\n"
            f"Было: {int(float(user[0]))} -> Стало: {int(new_coins)}"
        )

        try:
            await bot.send_message(int(user_id), f"🎁 Вам начислено {int(coins)} монет от администратора!")
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ Неверный формат монет")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /reset [user_id]")
            return

        user_id = args[1]

        def _reset():
            conn = get_db_connection()
            cursor = conn.cursor()
            query = "SELECT first_name FROM users WHERE user_id = %s" if DATABASE_URL else "SELECT first_name FROM users WHERE user_id = ?"
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            if not user:
                close_db_connection(conn)
                return None

            if DATABASE_URL:
                cursor.execute(
                    """
                    UPDATE users SET
                        coins = 0,
                        energy = 1000,
                        max_energy = 1000,
                        multi_tap_level = 1,
                        energy_level = 1,
                        auto_tap_level = 0,
                        skin_bought = FALSE,
                        ban_end_time = 0,
                        tap_window_start = 0,
                        tap_count = 0,
                        last_update = %s
                    WHERE user_id = %s
                    """,
                    (int(time.time() * 1000), user_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE users SET
                        coins = 0,
                        energy = 1000,
                        max_energy = 1000,
                        multi_tap_level = 1,
                        energy_level = 1,
                        auto_tap_level = 0,
                        skin_bought = 0,
                        ban_end_time = 0,
                        tap_window_start = 0,
                        tap_count = 0,
                        last_update = ?
                    WHERE user_id = ?
                    """,
                    (int(time.time() * 1000), user_id),
                )
            conn.commit()
            close_db_connection(conn)
            return user

        user = await run_blocking(_reset)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return

        await message.answer(f"✅ Прогресс пользователя {user[0]} сброшен")
        try:
            await bot.send_message(int(user_id), "⚠️ Ваш прогресс был сброшен администратором")
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /ban [user_id] [минуты]")
            return

        user_id = args[1]
        minutes = int(args[2]) if len(args) >= 3 else 60
        if minutes <= 0:
            await message.answer("❌ Минуты должны быть больше 0")
            return

        ban_end = int(time.time() * 1000) + minutes * 60 * 1000

        def _ban():
            conn = get_db_connection()
            cursor = conn.cursor()
            query = "SELECT first_name FROM users WHERE user_id = %s" if DATABASE_URL else "SELECT first_name FROM users WHERE user_id = ?"
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            if not user:
                close_db_connection(conn)
                return None

            update_q = "UPDATE users SET ban_end_time = %s WHERE user_id = %s" if DATABASE_URL else "UPDATE users SET ban_end_time = ? WHERE user_id = ?"
            cursor.execute(update_q, (ban_end, user_id))
            conn.commit()
            close_db_connection(conn)
            return user

        user = await run_blocking(_ban)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return

        await message.answer(f"✅ Пользователь {user[0]} забанен на {minutes} мин.")

        try:
            await bot.send_message(int(user_id), f"⛔ Вы заблокированы администратором на {minutes} мин.")
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ Неверный формат минут")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /stats [user_id]")
            return

        user_id = args[1]

        def _stats():
            conn = get_db_connection()
            cursor = conn.cursor()
            query = "SELECT * FROM users WHERE user_id = %s" if DATABASE_URL else "SELECT * FROM users WHERE user_id = ?"
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            close_db_connection(conn)
            return user

        user = await run_blocking(_stats)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return

        ban_until = int(user[11]) if len(user) > 11 else 0
        now_ms = int(time.time() * 1000)
        ban_text = "Нет"
        if ban_until > now_ms:
            remain_s = (ban_until - now_ms) // 1000
            ban_text = f"Да ({remain_s} сек.)"

        stats_text = (
            "📊 Статистика игрока\n\n"
            f"👤 Имя: {user[10]}\n"
            f"🆔 ID: {user[0]}\n"
            f"💰 Монеты: {int(float(user[1]))}\n"
            f"⚡ Энергия: {int(float(user[2]))}/{user[3]}\n"
            f"👆 Мульти-тап: Ур.{user[4]}\n"
            f"🔋 Энергия+: Ур.{user[5]}\n"
            f"🎨 Золотой скин: {'Да' if user[7] else 'Нет'}\n"
            f"⛔ Бан: {ban_text}"
        )
        await message.answer(stats_text)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        text = message.text.replace("/broadcast", "", 1).strip()
        if not text:
            await message.answer("Использование: /broadcast [текст сообщения]")
            return

        def _all_users():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            rows = cursor.fetchall()
            close_db_connection(conn)
            return rows

        users = await run_blocking(_all_users)

        success = 0
        failed = 0
        status_msg = await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")

        for (user_id,) in users:
            try:
                await bot.send_message(int(user_id), f"📢 Сообщение от администратора:\n\n{text}")
                success += 1
            except Exception:
                failed += 1

        await status_msg.edit_text(f"✅ Рассылка завершена!\n\nУспешно: {success}\nОшибок: {failed}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


routes = web.RouteTableDef()


@routes.get("/api/user/{user_id}")
async def get_user(request):
    web_user = get_verified_webapp_user(request)
    if not web_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    user_id = request.match_info["user_id"]
    if str(web_user["id"]) != str(user_id):
        return web.json_response({"error": "forbidden"}, status=403)

    username = web_user.get("username") or "Аноним"
    first_name = web_user.get("first_name") or "Игрок"
    data = await run_blocking(get_user_data, str(user_id), username, first_name)
    return web.json_response(data)


@routes.post("/api/action/{user_id}")
async def user_action(request):
    web_user = get_verified_webapp_user(request)
    if not web_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    user_id = request.match_info["user_id"]
    if str(web_user["id"]) != str(user_id):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    action = str(payload.get("action", "")).strip()
    if not action:
        return web.json_response({"error": "action_required"}, status=400)

    result = await run_blocking(
        process_user_action,
        str(user_id),
        action,
        web_user.get("username") or "Аноним",
        web_user.get("first_name") or "Игрок",
    )
    return web.json_response(result)


@routes.post("/api/user/{user_id}")
async def update_user_deprecated(request):
    web_user = get_verified_webapp_user(request)
    if not web_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    user_id = request.match_info["user_id"]
    if str(web_user["id"]) != str(user_id):
        return web.json_response({"error": "forbidden"}, status=403)

    # Deprecated endpoint: sync and return canonical server state.
    data = await run_blocking(
        get_user_data,
        str(user_id),
        web_user.get("username") or "Аноним",
        web_user.get("first_name") or "Игрок",
    )
    return web.json_response({"status": "ok", "data": data})


@routes.get("/api/leaderboard")
async def get_leaderboard_route(request):
    web_user = get_verified_webapp_user(request)
    if not web_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    leaderboard = await run_blocking(get_leaderboard)
    return web.json_response(leaderboard)


@routes.get("/")
async def index(request):
    with open("index.html", "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")


@routes.get("/style.css")
async def style(request):
    with open("style.css", "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/css")


@routes.get("/script.js")
async def script(request):
    with open("script.js", "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="application/javascript")


@routes.get("/image.jpg")
async def image(request):
    with open("image.jpg", "rb") as f:
        return web.Response(body=f.read(), content_type="image/jpeg")


async def start_web_server():
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")


async def main():
    init_db()
    print("База данных инициализирована")

    await start_web_server()

    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
