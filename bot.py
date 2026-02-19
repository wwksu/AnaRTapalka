import asyncio
import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# Токен бота - замени на свой (или используй переменную окружения для деплоя)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8510904775:AAEPqjsb2M3ckqzmnftrV_Ty5JcmMrAWDf4")
# URL где будет хоститься веб-приложение
WEBAPP_URL = os.getenv("WEBAPP_URL", "YOUR_WEBAPP_URL_HERE")  # например https://yourdomain.com
# PostgreSQL URL (Render предоставит автоматически)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ID администратора
ADMIN_ID = 1254600026

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_db_connection():
    """Получить подключение к базе данных"""
    if DATABASE_URL:
        # PostgreSQL на Render
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        # Локально используем SQLite (для разработки)
        import sqlite3
        return sqlite3.connect("users.db")

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        # PostgreSQL
        cursor.execute('''
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
                ban_end_time BIGINT DEFAULT 0
            )
        ''')
        # Добавляем колонку ban_end_time если её нет
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN ban_end_time BIGINT DEFAULT 0')
            conn.commit()
            print("Добавлена колонка ban_end_time в PostgreSQL")
        except:
            pass  # Колонка уже существует
    else:
        # SQLite
        cursor.execute('''
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
                ban_end_time INTEGER DEFAULT 0
            )
        ''')
        # Добавляем колонку ban_end_time если её нет
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN ban_end_time INTEGER DEFAULT 0')
            conn.commit()
            print("Добавлена колонка ban_end_time в SQLite")
        except:
            pass  # Колонка уже существует
    
    conn.commit()
    conn.close()
    print("База данных инициализирована")

def get_user_data(user_id, username=None, first_name=None):
    """Получить данные пользователя или создать новые"""
    import time
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM users WHERE user_id = %s' if DATABASE_URL else 'SELECT * FROM users WHERE user_id = ?', (str(user_id),))
    row = cursor.fetchone()

    if row is None:
        # Создаём нового пользователя
        if DATABASE_URL:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name)
                VALUES (%s, %s, %s)
            ''', (str(user_id), username or 'Аноним', first_name or 'Игрок'))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
            ''', (str(user_id), username or 'Аноним', first_name or 'Игрок'))
        conn.commit()

        # Получаем созданного пользователя
        cursor.execute('SELECT * FROM users WHERE user_id = %s' if DATABASE_URL else 'SELECT * FROM users WHERE user_id = ?', (str(user_id),))
        row = cursor.fetchone()
    else:
        # Обновляем имя если изменилось
        if username or first_name:
            if DATABASE_URL:
                cursor.execute('''
                    UPDATE users SET username = %s, first_name = %s
                    WHERE user_id = %s
                ''', (username or row[9], first_name or row[10], str(user_id)))
            else:
                cursor.execute('''
                    UPDATE users SET username = ?, first_name = ?
                    WHERE user_id = ?
                ''', (username or row[9], first_name or row[10], str(user_id)))
            conn.commit()
            cursor.execute('SELECT * FROM users WHERE user_id = %s' if DATABASE_URL else 'SELECT * FROM users WHERE user_id = ?', (str(user_id),))
            row = cursor.fetchone()

    # Преобразуем в словарь
    if DATABASE_URL:
        # PostgreSQL возвращает кортеж
        data = {
            "coins": float(row[1]),
            "energy": float(row[2]),
            "max_energy": int(row[3]),
            "multi_tap_level": int(row[4]),
            "energy_level": int(row[5]),
            "auto_tap_level": int(row[6]),
            "skin_bought": bool(row[7]),
            "last_update": int(row[8]),
            "username": row[9],
            "first_name": row[10],
            "ban_end_time": int(row[11]) if len(row) > 11 else 0
        }
    else:
        # SQLite
        data = {
            "coins": row[1],
            "energy": row[2],
            "max_energy": row[3],
            "multi_tap_level": row[4],
            "energy_level": row[5],
            "auto_tap_level": row[6],
            "skin_bought": bool(row[7]),
            "last_update": row[8],
            "username": row[9],
            "first_name": row[10],
            "ban_end_time": row[11] if len(row) > 11 else 0
        }

    conn.close()

    # Рассчитываем восстановление энергии и монет за время отсутствия
    current_time = int(time.time() * 1000)  # в миллисекундах
    last_update = data.get('last_update', 0)
    
    if last_update > 0:
        elapsed_seconds = (current_time - last_update) / 1000
        
        # Восстановление энергии (1 в секунду)
        if elapsed_seconds > 0:
            data['energy'] = min(data['energy'] + elapsed_seconds, data['max_energy'])
        
        # Авто-тап (пассивный доход)
        auto_tap_level = data.get('auto_tap_level', 0)
        if auto_tap_level > 0:
            data['coins'] += auto_tap_level * elapsed_seconds

    # Обновляем last_update и сохраняем (напрямую через SQL, чтобы избежать рекурсии)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        cursor.execute('''
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
                ban_end_time = %s
            WHERE user_id = %s
        ''', (
            data.get('coins', 0),
            data.get('energy', 1000),
            data.get('max_energy', 1000),
            data.get('multi_tap_level', 1),
            data.get('energy_level', 1),
            data.get('auto_tap_level', 0),
            data.get('skin_bought', False),
            current_time,
            data.get('username', 'Аноним'),
            data.get('first_name', 'Игрок'),
            data.get('ban_end_time', 0),
            str(user_id)
        ))
    else:
        cursor.execute('''
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
                ban_end_time = ?
            WHERE user_id = ?
        ''', (
            data.get('coins', 0),
            data.get('energy', 1000),
            data.get('max_energy', 1000),
            data.get('multi_tap_level', 1),
            data.get('energy_level', 1),
            data.get('auto_tap_level', 0),
            int(data.get('skin_bought', False)),
            current_time,
            data.get('username', 'Аноним'),
            data.get('first_name', 'Игрок'),
            data.get('ban_end_time', 0),
            str(user_id)
        ))
    
    conn.commit()
    conn.close()
    
    return data

def save_user_data(user_id, data):
    """Сохранить данные пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        cursor.execute('''
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
                ban_end_time = %s
            WHERE user_id = %s
        ''', (
            data.get('coins', 0),
            data.get('energy', 1000),
            data.get('max_energy', 1000),
            data.get('multi_tap_level', 1),
            data.get('energy_level', 1),
            data.get('auto_tap_level', 0),
            data.get('skin_bought', False),
            data.get('last_update', 0),
            data.get('username', 'Аноним'),
            data.get('first_name', 'Игрок'),
            data.get('ban_end_time', 0),
            str(user_id)
        ))
    else:
        cursor.execute('''
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
                ban_end_time = ?
            WHERE user_id = ?
        ''', (
            data.get('coins', 0),
            data.get('energy', 1000),
            data.get('max_energy', 1000),
            data.get('multi_tap_level', 1),
            data.get('energy_level', 1),
            data.get('auto_tap_level', 0),
            int(data.get('skin_bought', False)),
            data.get('last_update', 0),
            data.get('username', 'Аноним'),
            data.get('first_name', 'Игрок'),
            data.get('ban_end_time', 0),
            str(user_id)
        ))
    
    conn.commit()
    conn.close()

def get_leaderboard():
    """Получить топ игроков"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, first_name, coins, multi_tap_level
        FROM users
        ORDER BY coins DESC
        LIMIT 100
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "coins": float(row[3]),
            "multi_tap_level": int(row[4])
        }
        for row in rows
    ]

def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь админом"""
    return user_id == ADMIN_ID

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🐹 Открыть Анара",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])
    
    admin_text = ""
    if is_admin(message.from_user.id):
        admin_text = "\n\n👑 Админ-команды:\n/admin - панель управления"
    
    await message.answer(
        "Добро пожаловать в Анар тап!🐹🐹🐹\n\n"
        f"Тапай по ананисту и прокачивайся!{admin_text}",
        reply_markup=keyboard
    )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Статистика
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(coins) FROM users')
    total_coins = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT first_name, coins FROM users ORDER BY coins DESC LIMIT 1')
    top_user = cursor.fetchone()
    
    conn.close()
    
    admin_text = (
        "👑 АДМИН-ПАНЕЛЬ\n\n"
        f"📊 Статистика:\n"
        f"• Всего игроков: {total_users}\n"
        f"• Всего монет: {int(float(total_coins))}\n"
        f"• Топ игрок: {top_user[0] if top_user else 'Нет'} ({int(float(top_user[1])) if top_user else 0} монет)\n\n"
        f"📝 Команды:\n"
        f"/users - список всех пользователей\n"
        f"/give [user_id] [монеты] - выдать монеты\n"
        f"/reset [user_id] - сбросить прогресс\n"
        f"/ban [user_id] - забанить пользователя\n"
        f"/stats [user_id] - статистика игрока\n"
        f"/broadcast [текст] - рассылка всем"
    )
    
    await message.answer(admin_text)

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    """Список пользователей"""
    if not is_admin(message.from_user.id):
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, first_name, coins, multi_tap_level
        FROM users
        ORDER BY coins DESC
        LIMIT 50
    ''')
    
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        await message.answer("Пользователей пока нет")
        return
    
    text = "👥 Топ-50 пользователей:\n\n"
    for i, (user_id, name, coins, level) in enumerate(users, 1):
        text += f"{i}. {name} (ID: {user_id})\n   💰 {int(float(coins))} монет | 👆 Ур.{level}\n\n"
    
    await message.answer(text)

@dp.message(Command("give"))
async def cmd_give(message: types.Message):
    """Выдать монеты пользователю"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.answer("Использование: /give [user_id] [монеты]")
            return
        
        user_id = args[1]
        coins = float(args[2])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT coins, first_name FROM users WHERE user_id = %s' if DATABASE_URL else 'SELECT coins, first_name FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            conn.close()
            return
        
        new_coins = float(user[0]) + coins
        cursor.execute('UPDATE users SET coins = %s WHERE user_id = %s' if DATABASE_URL else 'UPDATE users SET coins = ? WHERE user_id = ?', (new_coins, user_id))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Выдано {int(coins)} монет пользователю {user[1]}\n"
            f"Было: {int(float(user[0]))} → Стало: {int(new_coins)}"
        )
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                int(user_id),
                f"🎁 Вам начислено {int(coins)} монет от администратора!"
            )
        except:
            pass
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    """Сбросить прогресс пользователя"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /reset [user_id]")
            return
        
        user_id = args[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT first_name FROM users WHERE user_id = %s' if DATABASE_URL else 'SELECT first_name FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            conn.close()
            return
        
        if DATABASE_URL:
            cursor.execute('''
                UPDATE users SET
                    coins = 0,
                    energy = 1000,
                    max_energy = 1000,
                    multi_tap_level = 1,
                    energy_level = 1,
                    auto_tap_level = 0,
                    skin_bought = FALSE
                WHERE user_id = %s
            ''', (user_id,))
        else:
            cursor.execute('''
                UPDATE users SET
                    coins = 0,
                    energy = 1000,
                    max_energy = 1000,
                    multi_tap_level = 1,
                    energy_level = 1,
                    auto_tap_level = 0,
                    skin_bought = 0
                WHERE user_id = ?
            ''', (user_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ Прогресс пользователя {user[0]} сброшен")
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                int(user_id),
                "⚠️ Ваш прогресс был сброшен администратором"
            )
        except:
            pass
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика пользователя"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /stats [user_id]")
            return
        
        user_id = args[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = %s' if DATABASE_URL else 'SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        
        stats_text = (
            f"📊 Статистика игрока\n\n"
            f"👤 Имя: {user[10]}\n"
            f"🆔 ID: {user[0]}\n"
            f"💰 Монеты: {int(float(user[1]))}\n"
            f"⚡ Энергия: {int(float(user[2]))}/{user[3]}\n"
            f"👆 Мульти-тап: Ур.{user[4]}\n"
            f"🔋 Энергия+: Ур.{user[5]}\n"
            f"🤖 Авто-тап: Ур.{user[6]}\n"
            f"🎨 Золотой скин: {'Да' if user[7] else 'Нет'}"
        )
        
        await message.answer(stats_text)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    """Рассылка всем пользователям"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        text = message.text.replace("/broadcast", "", 1).strip()
        if not text:
            await message.answer("Использование: /broadcast [текст сообщения]")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()
        
        success = 0
        failed = 0
        
        status_msg = await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")
        
        for (user_id,) in users:
            try:
                await bot.send_message(int(user_id), f"📢 Сообщение от администратора:\n\n{text}")
                success += 1
            except:
                failed += 1
        
        await status_msg.edit_text(
            f"✅ Рассылка завершена!\n\n"
            f"Успешно: {success}\n"
            f"Ошибок: {failed}"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# Веб-сервер для API
routes = web.RouteTableDef()

@routes.get('/api/user/{user_id}')
async def get_user(request):
    """Получить данные пользователя"""
    user_id = request.match_info['user_id']
    username = request.query.get('username')
    first_name = request.query.get('first_name')
    data = get_user_data(user_id, username, first_name)
    return web.json_response(data)

@routes.post('/api/user/{user_id}')
async def update_user(request):
    """Обновить данные пользователя"""
    user_id = request.match_info['user_id']
    new_data = await request.json()
    
    save_user_data(user_id, new_data)
    
    return web.json_response({"status": "ok"})

@routes.get('/api/leaderboard')
async def get_leaderboard_route(request):
    """Получить топ игроков"""
    leaderboard = get_leaderboard()
    return web.json_response(leaderboard)

@routes.get('/')
async def index(request):
    """Отдать главную страницу"""
    with open('index.html', 'r', encoding='utf-8') as f:
        return web.Response(text=f.read(), content_type='text/html')

@routes.get('/style.css')
async def style(request):
    """Отдать CSS"""
    with open('style.css', 'r', encoding='utf-8') as f:
        return web.Response(text=f.read(), content_type='text/css')

@routes.get('/script.js')
async def script(request):
    """Отдать JS"""
    with open('script.js', 'r', encoding='utf-8') as f:
        return web.Response(text=f.read(), content_type='application/javascript')

@routes.get('/image.jpg')
async def image(request):
    """Отдать картинку хомяка"""
    with open('image.jpg', 'rb') as f:
        return web.Response(body=f.read(), content_type='image/jpeg')

async def start_web_server():
    """Запуск веб-сервера"""
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Веб-сервер запущен на порту 8080")

async def main():
    """Главная функция"""
    # Инициализируем базу данных
    init_db()
    print("База данных инициализирована")
    
    # Запускаем веб-сервер
    await start_web_server()
    
    # Запускаем бота
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
