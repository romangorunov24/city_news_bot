# bot.py — точка входа приложения: инициализация бота, диспетчера, базы данных, middleware и роутеров

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from config import load_config
from database import Database
from handlers.admin import admin_router
from handlers.user import user_router
from middlewares.album import AlbumMiddleware, BanCheckMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    config = load_config()
    db = Database(db_path=config.db_path)
    await db.init_db()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp["db"] = db
    dp["config"] = config

    dp.update.outer_middleware(BanCheckMiddleware(db=db, admin_chat_id=config.admin_chat_id))
    dp.message.middleware(AlbumMiddleware(latency=0.7))

    dp.include_router(admin_router)
    dp.include_router(user_router)

    try:
        # Проверяем, установлен ли вебхук; если нет — не вызываем delete_webhook, чтобы не ловить Flood Control
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            try:
                await bot.delete_webhook(drop_pending_updates=True)
            except TelegramAPIError as e:
                logging.warning("Не удалось удалить вебхук (%s), запускаем polling напрямую.", e)

        logging.info("Бот городского новостного канала успешно запущен (БД: %s).", config.db_path)
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
