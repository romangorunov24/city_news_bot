# config.py — загрузка и валидация конфигурации бота из переменных окружения (.env или Railway Variables)

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_chat_id: int
    channel_id: int | str
    db_path: str


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("Не задан BOT_TOKEN в переменных окружения")

    admin_chat_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not admin_chat_raw:
        raise ValueError("Не задан ADMIN_CHAT_ID в переменных окружения")
    admin_chat_id = int(admin_chat_raw)

    channel_raw = os.getenv("CHANNEL_ID", "").strip()
    if not channel_raw:
        raise ValueError("Не задан CHANNEL_ID в переменных окружения")
    # Поддерживаем как числовой ID (-100...), так и @username канала
    channel_id: int | str = int(channel_raw) if channel_raw.lstrip("-").isdigit() else channel_raw

    db_path = os.getenv("DB_PATH", "city_bot.db").strip()

    return Config(
        bot_token=bot_token,
        admin_chat_id=admin_chat_id,
        channel_id=channel_id,
        db_path=db_path,
    )
