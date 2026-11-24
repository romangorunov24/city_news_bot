# Telegram-бот для городского новостного канала

Асинхронный бот на **Python 3.11+** и **aiogram 3.x** для приёма новостей от подписчиков («предложка» со склейкой альбомов), обработки обращений в поддержку и приёма заявок на рекламу.

## Быстрый запуск на Railway через GitHub

1. Загрузите все файлы из этой папки в корень репозитория на **GitHub**.
2. В **Railway** нажмите **New Project → Deploy from GitHub repo** и выберите этот репозиторий.
3. Откройте вкладку **Variables** в настройках сервиса Railway и добавьте 3 обязательные переменные:
   - `BOT_TOKEN` — токен бота от `@BotFather`.
   - `ADMIN_CHAT_ID` — числовой ID закрытой админ-группы или вашего личного Telegram-аккаунта.
   - `CHANNEL_ID` — числовой ID тестового/целевого канала (начинается с `-100...`) или его `@username`.
4. **Важно:** добавьте бота администратором в канал `CHANNEL_ID` с правом публикации сообщений (и в админ-чат `ADMIN_CHAT_ID`, если это группа).
5. Railway автоматически соберёт проект и запустит бота командой `python bot.py`.

## Локальный запуск

```bash
python -m venv venv
source venv/bin/activate      # Linux / macOS
venv\Scripts\activate         # Windows
pip install -r requirements.txt
cp .env.example .env
python bot.py
```
