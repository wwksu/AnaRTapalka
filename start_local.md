# Быстрый запуск через ngrok

## Шаг 1: Установи ngrok
Скачай с https://ngrok.com/download и распакуй

## Шаг 2: Зарегистрируйся и получи authtoken
1. Зарегистрируйся на ngrok.com (бесплатно)
2. Скопируй authtoken из дашборда
3. Выполни: `ngrok config add-authtoken ВАШ_ТОКЕН`

## Шаг 3: Запусти ngrok
```bash
ngrok http 8080
```

Получишь URL типа: `https://abc123.ngrok-free.app`

## Шаг 4: Вставь URL в bot.py
Замени `YOUR_WEBAPP_URL_HERE` на полученный URL

## Шаг 5: Запусти бота
```bash
pip install -r requirements.txt
python bot.py
```

Готово! Бот работает, можешь тестировать в Telegram.

**Минус:** ngrok URL меняется при каждом перезапуске (на бесплатном тарифе)
