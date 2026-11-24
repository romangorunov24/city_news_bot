# handlers/admin.py — админ-панель: автопубликация новостей в канал, ответы в тикетах, отклонение с причиной и бан

import html
from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from config import Config
from database import Database
from handlers.user import extract_payload, send_media_attachments
from keyboards import (
    NEWS_REJECT_REASONS,
    TICKET_REJECT_REASONS,
    admin_cancel_fsm_kb,
    admin_news_kb,
    admin_ticket_kb,
    reject_reasons_kb,
    user_reply_kb,
)

admin_router = Router()


class AdminStates(StatesGroup):
    waiting_reply_text = State()
    waiting_custom_reject_reason = State()


async def safe_notify_user(
    bot: Bot,
    feedback_chat_id: int,
    user_id: int,
    text: str,
    reply_markup=None,
) -> bool:
    """Безопасная отправка уведомления пользователю с обработкой блокировки бота."""
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except TelegramForbiddenError:
        await bot.send_message(
            chat_id=feedback_chat_id,
            text=f"⚠️ Пользователь <code>{user_id}</code> заблокировал бота — доставить уведомление не удалось.",
        )
        return False
    except TelegramBadRequest as e:
        await bot.send_message(
            chat_id=feedback_chat_id,
            text=f"⚠️ Ошибка доставки пользователю <code>{user_id}</code>: {html.escape(str(e))}",
        )
        return False
    except TelegramAPIError as e:
        await bot.send_message(
            chat_id=feedback_chat_id,
            text=f"⚠️ Сбой Telegram API при отправке пользователю <code>{user_id}</code>: {html.escape(str(e))}",
        )
        return False


async def publish_news_to_channel(
    bot: Bot,
    channel_id: int | str,
    ticket: dict,
) -> None:
    """Публикует новость (текст, одиночное медиа или альбом) в целевой канал."""
    raw_text: str = ticket.get("text", "").strip()
    media: list[dict[str, str]] = ticket.get("media", [])
    is_anonymous: bool = bool(ticket.get("is_anonymous", 1))

    post_parts = []
    if raw_text:
        post_parts.append(html.escape(raw_text))

    if not is_anonymous:
        if ticket.get("username"):
            author_str = f"@{html.escape(ticket['username'])}"
        else:
            author_str = html.escape(ticket.get("full_name") or "Подписчик")
        post_parts.append(f"<i>Предложил(а): {author_str}</i>")

    caption_text = "\n\n".join(post_parts)

    if not media:
        await bot.send_message(chat_id=channel_id, text=caption_text)
        return

    if len(media) == 1:
        item = media[0]
        if len(caption_text) <= 1024:
            if item["type"] == "photo":
                await bot.send_photo(chat_id=channel_id, photo=item["file_id"], caption=caption_text or None)
            elif item["type"] == "video":
                await bot.send_video(chat_id=channel_id, video=item["file_id"], caption=caption_text or None)
            elif item["type"] == "document":
                await bot.send_document(chat_id=channel_id, document=item["file_id"], caption=caption_text or None)
        else:
            await send_media_attachments(bot, channel_id, media)
            await bot.send_message(chat_id=channel_id, text=caption_text)
        return

    pv_items = [m for m in media if m["type"] in ("photo", "video")]
    doc_items = [m for m in media if m["type"] == "document"]

    if pv_items:
        media_group = []
        for idx, item in enumerate(pv_items):
            item_caption = caption_text if (idx == 0 and len(caption_text) <= 1024) else None
            if item["type"] == "photo":
                media_group.append(InputMediaPhoto(media=item["file_id"], caption=item_caption))
            else:
                media_group.append(InputMediaVideo(media=item["file_id"], caption=item_caption))

        if len(media_group) == 1:
            first = media_group[0]
            if isinstance(first, InputMediaPhoto):
                await bot.send_photo(chat_id=channel_id, photo=first.media, caption=first.caption)
            else:
                await bot.send_video(chat_id=channel_id, video=first.media, caption=first.caption)
        else:
            await bot.send_media_group(chat_id=channel_id, media=media_group)

        if len(caption_text) > 1024:
            await bot.send_message(chat_id=channel_id, text=caption_text)

    if doc_items:
        doc_group = []
        for idx, item in enumerate(doc_items):
            use_caption = (
                caption_text
                if (not pv_items and idx == 0 and len(caption_text) <= 1024)
                else None
            )
            doc_group.append(InputMediaDocument(media=item["file_id"], caption=use_caption))

        if len(doc_group) == 1:
            await bot.send_document(
                chat_id=channel_id, document=doc_group[0].media, caption=doc_group[0].caption
            )
        else:
            await bot.send_media_group(chat_id=channel_id, media=doc_group)


async def mark_card_resolved(callback: CallbackQuery, status_line: str) -> None:
    """Обновляет текст карточки и убирает кнопки управления."""
    if not callback.message:
        return
    base_html = callback.message.html_text or ""
    try:
        await callback.message.edit_text(
            f"{base_html}\n\n━━━━━━━━━━━━━━\n{status_line}",
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass


# --- ПУБЛИКАЦИЯ НОВОСТИ В КАНАЛ ---

@admin_router.callback_query(F.data.startswith("adm:pub:"))
async def cb_admin_publish_news(
    callback: CallbackQuery, db: Database, bot: Bot, config: Config
) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)
    feedback_chat = callback.message.chat.id if callback.message else config.admin_chat_id

    if not ticket:
        await callback.answer("Новость не найдена в базе данных.", show_alert=True)
        return

    if ticket["status"] == "closed":
        await callback.answer("Эта новость уже была опубликована.", show_alert=True)
        return

    try:
        await publish_news_to_channel(bot=bot, channel_id=config.channel_id, ticket=ticket)
    except TelegramAPIError as e:
        await callback.answer("Ошибка публикации в канал!", show_alert=True)
        await bot.send_message(
            chat_id=feedback_chat,
            text=(
                f"❌ Не удалось опубликовать новость #{ticket_id} в канал <code>{config.channel_id}</code>.\n"
                f"Проверьте, что бот добавлен в канал администратором с правом публикации постов.\n"
                f"Детали: <code>{html.escape(str(e))}</code>"
            ),
        )
        return

    await db.update_ticket_status(ticket_id=ticket_id, status="closed")

    channel_link_hint = ""
    if isinstance(config.channel_id, str) and config.channel_id.startswith("@"):
        channel_link_hint = f"\n👉 Посмотреть пост: {html.escape(config.channel_id)}"

    await safe_notify_user(
        bot=bot,
        feedback_chat_id=feedback_chat,
        user_id=ticket["user_id"],
        text=(
            f"🎉 <b>Ваша новость #{ticket_id} опубликована в канале!</b>\n"
            f"Спасибо за участие в жизни города!{channel_link_hint}"
        ),
    )

    admin_name = html.escape(callback.from_user.full_name) if callback.from_user else "Админ"
    await mark_card_resolved(callback, f"✅ <b>Опубликовано в канал</b> ({admin_name})")
    await callback.answer("Опубликовано в канал!")


# --- ОТВЕТ / УТОЧНЕНИЕ ПО ТИКЕТУ ---

@admin_router.callback_query(F.data.startswith("adm:reply:"))
async def cb_admin_start_reply(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)

    if not ticket:
        await callback.answer("Обращение не найдено.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_reply_text)
    await state.update_data(target_ticket_id=ticket_id)

    if callback.message:
        prompt_msg = await callback.message.answer(
            f"💬 Введите ответ пользователю по обращению <b>#{ticket_id}</b>\n"
            "(можно отправить текст, фото или файл):",
            reply_markup=admin_cancel_fsm_kb(),
        )
        await state.update_data(prompt_message_id=prompt_msg.message_id)
    await callback.answer()


@admin_router.message(AdminStates.waiting_reply_text)
async def process_admin_reply_text(
    message: Message,
    state: FSMContext,
    db: Database,
    bot: Bot,
    album: list[Message] | None = None,
) -> None:
    data = await state.get_data()
    ticket_id = data.get("target_ticket_id")
    if not ticket_id:
        await state.clear()
        return

    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await state.clear()
        await message.answer("⚠️ Тикет не найден в базе.")
        return

    messages = album if album else [message]
    text, media = extract_payload(messages)

    if not text and not media:
        await message.answer("⚠️ Введите текст ответа или прикрепите файл.")
        return

    await state.clear()
    await db.update_ticket_status(ticket_id=ticket_id, status="answered")

    safe_reply = html.escape(text) if text else "<i>(администратор отправил вложение)</i>"
    user_notice = (
        f"💬 <b>Ответ по обращению #{ticket_id}:</b>\n\n"
        f"{safe_reply}"
    )

    try:
        if media:
            await send_media_attachments(bot, ticket["user_id"], media)
    except TelegramAPIError:
        pass

    delivered = await safe_notify_user(
        bot=bot,
        feedback_chat_id=message.chat.id,
        user_id=ticket["user_id"],
        text=user_notice,
        reply_markup=user_reply_kb(ticket_id),
    )

    if delivered:
        await message.answer(f"✅ Ответ по обращению <b>#{ticket_id}</b> отправлен пользователю.")


# --- ОТКЛОНЕНИЕ С ПРИЧИНОЙ ---

@admin_router.callback_query(F.data.startswith("adm:rej_menu:"))
async def cb_admin_reject_menu(callback: CallbackQuery, db: Database) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Тикет не найден.", show_alert=True)
        return

    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=reject_reasons_kb(ticket_id=ticket_id, category=ticket["category"])
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:back:"))
async def cb_admin_back_kb(callback: CallbackQuery, db: Database) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Тикет не найден.", show_alert=True)
        return

    kb = (
        admin_news_kb(ticket_id, ticket["user_id"])
        if ticket["category"] == "news"
        else admin_ticket_kb(ticket_id, ticket["user_id"])
    )
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:rej_fast:"))
async def cb_admin_reject_fast(
    callback: CallbackQuery, db: Database, bot: Bot, config: Config
) -> None:
    parts = callback.data.split(":")
    ticket_id = int(parts[2])
    reason_idx = parts[3]
    feedback_chat = callback.message.chat.id if callback.message else config.admin_chat_id

    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Тикет не найден.", show_alert=True)
        return

    reasons_map = (
        NEWS_REJECT_REASONS if ticket["category"] == "news" else TICKET_REJECT_REASONS
    )
    reason = reasons_map.get(reason_idx, "Отклонено администратором")

    await db.update_ticket_status(ticket_id=ticket_id, status="rejected")
    await safe_notify_user(
        bot=bot,
        feedback_chat_id=feedback_chat,
        user_id=ticket["user_id"],
        text=(
            f"❌ <b>Ваше обращение #{ticket_id} отклонено.</b>\n"
            f"<b>Причина:</b> {html.escape(reason)}"
        ),
    )

    admin_name = html.escape(callback.from_user.full_name) if callback.from_user else "Админ"
    await mark_card_resolved(
        callback, f"❌ <b>Отклонено</b> ({admin_name})\nПричина: {html.escape(reason)}"
    )
    await callback.answer("Отклонено")


@admin_router.callback_query(F.data.startswith("adm:rej_custom:"))
async def cb_admin_reject_custom(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Тикет не найден.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_custom_reject_reason)
    await state.update_data(
        reject_ticket_id=ticket_id,
        card_chat_id=callback.message.chat.id if callback.message else None,
        card_message_id=callback.message.message_id if callback.message else None,
        card_html=callback.message.html_text if callback.message else "",
    )

    if callback.message:
        await callback.message.answer(
            f"✍️ Введите причину отказа для обращения <b>#{ticket_id}</b>:",
            reply_markup=admin_cancel_fsm_kb(),
        )
    await callback.answer()


@admin_router.message(AdminStates.waiting_custom_reject_reason)
async def process_admin_custom_reject(
    message: Message,
    state: FSMContext,
    db: Database,
    bot: Bot,
) -> None:
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("⚠️ Введите текстовую причину отказа.")
        return

    data = await state.get_data()
    ticket_id = data.get("reject_ticket_id")
    card_chat_id = data.get("card_chat_id") or message.chat.id
    card_message_id = data.get("card_message_id")
    card_html = data.get("card_html", "")
    await state.clear()

    if not ticket_id:
        return

    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await message.answer("⚠️ Тикет не найден.")
        return

    await db.update_ticket_status(ticket_id=ticket_id, status="rejected")
    await safe_notify_user(
        bot=bot,
        feedback_chat_id=message.chat.id,
        user_id=ticket["user_id"],
        text=(
            f"❌ <b>Ваше обращение #{ticket_id} отклонено.</b>\n"
            f"<b>Причина:</b> {html.escape(reason)}"
        ),
    )

    admin_name = html.escape(message.from_user.full_name) if message.from_user else "Админ"
    if card_message_id and card_html:
        try:
            await bot.edit_message_text(
                chat_id=card_chat_id,
                message_id=card_message_id,
                text=(
                    f"{card_html}\n\n━━━━━━━━━━━━━━\n"
                    f"❌ <b>Отклонено</b> ({admin_name})\nПричина: {html.escape(reason)}"
                ),
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass

    await message.answer(f"✅ Обращение <b>#{ticket_id}</b> отклонено с указанной причиной.")


# --- ЗАКРЫТИЕ ТИКЕТА И БАН ПОЛЬЗОВАТЕЛЯ ---

@admin_router.callback_query(F.data.startswith("adm:close:"))
async def cb_admin_close_ticket(
    callback: CallbackQuery, db: Database, bot: Bot, config: Config
) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)
    feedback_chat = callback.message.chat.id if callback.message else config.admin_chat_id

    if not ticket:
        await callback.answer("Тикет не найден.", show_alert=True)
        return

    await db.update_ticket_status(ticket_id=ticket_id, status="closed")
    await safe_notify_user(
        bot=bot,
        feedback_chat_id=feedback_chat,
        user_id=ticket["user_id"],
        text=f"🔒 <b>Обращение #{ticket_id} закрыто администратором.</b>\nЕсли появятся новые вопросы, используйте /start.",
    )

    admin_name = html.escape(callback.from_user.full_name) if callback.from_user else "Админ"
    await mark_card_resolved(callback, f"🔒 <b>Тикет закрыт</b> ({admin_name})")
    await callback.answer("Тикет закрыт")


@admin_router.callback_query(F.data.startswith("adm:ban:"))
async def cb_admin_ban_user(
    callback: CallbackQuery, db: Database, config: Config
) -> None:
    parts = callback.data.split(":")
    target_user_id = int(parts[2])
    ticket_id = int(parts[3])

    is_demo_sandbox = (
        callback.message is not None and callback.message.chat.id != config.admin_chat_id
    ) or (callback.from_user is not None and target_user_id == callback.from_user.id)

    await db.update_ticket_status(ticket_id=ticket_id, status="rejected")
    admin_name = html.escape(callback.from_user.full_name) if callback.from_user else "Админ"

    if is_demo_sandbox:
        await mark_card_resolved(
            callback,
            f"🚫 <b>[ДЕМО] Пользователь</b> <code>{target_user_id}</code> <b>заблокирован</b>\n"
            "<i>(В демо-режиме ваш аккаунт не блокируется, чтобы вы могли продолжить тест)</i>",
        )
        await callback.answer(
            "В боевом режиме этот подписчик был бы заблокирован навсегда!", show_alert=True
        )
        return

    await db.ban_user(target_user_id)
    await mark_card_resolved(
        callback,
        f"🚫 <b>Пользователь</b> <code>{target_user_id}</code> <b>заблокирован</b> ({admin_name})",
    )
    await callback.answer("Пользователь забанен", show_alert=True)


@admin_router.callback_query(F.data == "adm:cancel_fsm")
async def cb_admin_cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer("Отменено")
