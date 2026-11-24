# database.py — асинхронный слой работы с SQLite (aiosqlite): таблицы users и tickets + настройки демо-режима

import json
import os
from datetime import datetime, timezone
from typing import Any
import aiosqlite


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    is_banned INTEGER NOT NULL DEFAULT 0,
                    demo_mode INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Мягкая миграция на случай, если база уже была создана без колонки demo_mode
            try:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN demo_mode INTEGER NOT NULL DEFAULT 1"
                )
            except aiosqlite.OperationalError:
                pass

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    is_anonymous INTEGER NOT NULL DEFAULT 1,
                    text TEXT NOT NULL DEFAULT '',
                    media_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                """
            )
            await db.commit()

    async def upsert_user(self, user_id: int, username: str | None, full_name: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, username, full_name, is_banned, demo_mode, created_at)
                VALUES (?, ?, ?, 0, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name
                """,
                (user_id, username, full_name, now),
            )
            await db.commit()

    async def get_demo_mode(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT demo_mode FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else True

    async def set_demo_mode(self, user_id: int, enabled: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET demo_mode = ? WHERE user_id = ?",
                (int(enabled), user_id),
            )
            await db.commit()

    async def is_user_banned(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT is_banned FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else False

    async def ban_user(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_ticket(
        self,
        user_id: int,
        category: str,
        text: str = "",
        media: list[dict[str, str]] | None = None,
        is_anonymous: bool = True,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        media_json = json.dumps(media or [], ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO tickets (user_id, category, status, is_anonymous, text, media_json, created_at)
                VALUES (?, ?, 'open', ?, ?, ?, ?)
                """,
                (user_id, category, int(is_anonymous), text, media_json, now),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT t.*, u.username, u.full_name, u.is_banned
                FROM tickets t
                LEFT JOIN users u ON t.user_id = u.user_id
                WHERE t.id = ?
                """,
                (ticket_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                data["media"] = json.loads(data.get("media_json") or "[]")
                return data

    async def update_ticket_status(self, ticket_id: int, status: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (status, ticket_id),
            )
            await db.commit()
