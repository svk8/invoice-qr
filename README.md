# Счёт → QR для оплаты

Автоматическая замена QR-кода на счетах.

## Быстрый старт (локально)

```bash
pip install -r requirements.txt
python app.py
```

Открыть http://localhost:5000

## Деплой на неделю+ (бесплатно / дёшево)

### Вариант 1. Render.com (рекомендуется, бесплатный tier)

1. Зарегистрируйся на https://render.com
2. New → Web Service
3. Подключи GitHub-репозиторий с этой папкой (или загрузи вручную)
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`
   - Instance type: Free
5. Deploy → получишь постоянный URL вида `https://xxx.onrender.com`

Бесплатный план «засыпает» после 15 мин бездействия, но просыпается за 30–50 сек.

### Вариант 2. Railway.app

1. https://railway.app
2. New Project → Deploy from GitHub / Upload
3. Добавь переменную PORT=5000 (если нужно)
4. Deploy

### Вариант 3. Fly.io

```bash
fly launch
fly deploy
```

### Вариант 4. Дешёвый VPS (от 150–300 ₽/мес)

Timeweb, Selectel, FirstVDS, Hetzner CX22 и т.п.  
Просто клонируешь проект, ставишь зависимости, запускаешь через systemd или screen.

## Docker

```bash
docker build -t invoice-qr .
docker run -p 5000:5000 invoice-qr
```

## Telegram-бот

```bash
export BOT_TOKEN="токен_от_BotFather"
python bot.py
```
