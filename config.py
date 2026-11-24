# config.py — загрузка и валидация конфигурации бота из переменных окружения (.env или Railway Variables)

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _clean_env(name: str) -> str:
    return os.getenv(name, "").strip().strip('"').strip("'")


def _normalize_channel_id(raw: str) -> int | str:
    cleaned = raw.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if cleaned.lower().startswith(prefix):
            slug = cleaned[len(prefix):].strip("/")
            if slug and not slug.startswith("+"):
                return f"@{slug}"
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    return cleaned


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_chat_id: int
    channel_id: int | str
    db_path: str


def load_config() -> Config:
    bot_token = _clean_env("BOT_TOKEN")
    if not bot_token:
        raise ValueError("Не задан BOT_TOKEN в переменных окружения")

    admin_chat_raw = _clean_env("ADMIN_CHAT_ID")
    if not admin_chat_raw:
        raise ValueError("Не задан ADMIN_CHAT_ID в переменных окружения")
    try:
        admin_chat_id = int(admin_chat_raw)
    except ValueError as exc:
        raise ValueError(
            f"ADMIN_CHAT_ID должен быть числом (например, 123456789 или -1001234567890), получено: {admin_chat_raw!r}"
        ) from exc

    channel_raw = _clean_env("CHANNEL_ID")
    if not channel_raw:
        raise ValueError("Не задан CHANNEL_ID в переменных окружения")
    channel_id = _normalize_channel_id(channel_raw)

    db_path = _clean_env("DB_PATH")
    if not db_path:
        # Если на Railway примонтирован Volume в /data — автоматически сохраняем базу туда
        if os.path.isdir("/data") and os.access("/data", os.W_OK):
            db_path = "/data/city_bot.db"
        else:
            db_path = "city_bot.db"

    return Config(
        bot_token=bot_token,
        admin_chat_id=admin_chat_id,
        channel_id=channel_id,
        db_path=db_path,
    )
