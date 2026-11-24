# middlewares/album.py — middleware для склейки медиагрупп (альбомов) и фильтрации забаненных пользователей

import asyncio
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from database import Database


class AlbumMiddleware(BaseMiddleware):
    """
    Собирает сообщения с одинаковым media_group_id в единый список data['album']
    и пропускает в хендлер только один вызов вместо N отдельных сообщений.
    """

    def __init__(self, latency: float = 0.6) -> None:
        self.latency = latency
        self.album_data: dict[str, list[Message]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.media_group_id:
            return await handler(event, data)

        group_id = event.media_group_id
        if group_id in self.album_data:
            self.album_data[group_id].append(event)
            return None

        self.album_data[group_id] = [event]
        await asyncio.sleep(self.latency)

        messages = sorted(self.album_data.pop(group_id, [event]), key=lambda m: m.message_id)
        data["album"] = messages
        return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    """
    Игнорирует любые входящие апдейты от заблокированных пользователей в личных чатах.
    """

    def __init__(self, db: Database, admin_chat_id: int) -> None:
        self.db = db
        self.admin_chat_id = admin_chat_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        chat = data.get("event_chat")

        # Не блокируем действия внутри админ-чата
        if chat and chat.id == self.admin_chat_id:
            return await handler(event, data)

        if user and await self.db.is_user_banned(user.id):
            return None

        return await handler(event, data)
