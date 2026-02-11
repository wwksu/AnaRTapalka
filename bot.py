import asyncio
import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# Токен бота - замени на свой (или используй переменную окружения для деплоя)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8510904775:AAEPqjsb2M3ckqzmnftrV_Ty5JcmMrAWDf4")
# URL где будет хоститься веб-приложение
WEBAPP_URL = os.getenv("WEBAPP_URL", "YOUR_WEBAPP_URL_HERE")  # например https://yourdomain.com

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Файл для хранения данных пользователей
DATA_FILE = "users_data.json"

def load_users_data():
    """Загрузка данных пользователей из JSON"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_users_data(data):
    """Сохранение данных пользователей в JSON"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id):
    """Получить данные пользователя или создать новые"""
    users = load_users_data()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        users[user_id_str] = {
            "coins": 0,
            "energy": 1000,
            "max_energy": 1000,
            "multi_tap_level": 1,
            "energy_level": 1,
            "auto_tap_level": 0,
            "skin_bought": False,
            "last_update": 0
        }
        save_users_data(users)
    
    return users[user_id_str]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🐹 Открыть Анара",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])
    
    await message.answer(
        "Добро пожаловать в Анар тап!🐹🐹🐹\n\n"
        "Тапай по ананисту и прокачивайся!",
        reply_markup=keyboard
    )

# Веб-сервер для API
routes = web.RouteTableDef()

@routes.get('/api/user/{user_id}')
async def get_user(request):
    """Получить данные пользователя"""
    user_id = request.match_info['user_id']
    data = get_user_data(user_id)
    return web.json_response(data)

@routes.post('/api/user/{user_id}')
async def update_user(request):
    """Обновить данные пользователя"""
    user_id = request.match_info['user_id']
    new_data = await request.json()
    
    users = load_users_data()
    users[str(user_id)] = new_data
    save_users_data(users)
    
    return web.json_response({"status": "ok"})

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
    # Запускаем веб-сервер
    await start_web_server()
    
    # Запускаем бота
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

