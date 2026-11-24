# handlers/user.py — пользовательские сценарии: предложка новостей (с альбомами), вопросы/жалобы, реклама, тикеты и демо-песочница

import html
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
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
from keyboards import (
    admin_news_kb,
    admin_ticket_kb,
    ads_menu_kb,
    anonymity_kb,
    cancel_kb,
    main_menu_kb,
)

user_router = Router()


class UserStates(StatesGroup):
    waiting_news_content = State()
    waiting_news_anon = State()
    waiting_support_content = State()
    waiting_ads_content = State()
    waiting_ticket_reply = State()


def build_welcome_text(demo_mode: bool) -> str:
    demo_hint = (
        "\n\n🧪 <i>Сейчас включён <b>Демо-режим админа</b>: после отправки новости или вопроса "
        "вы сразу получите карточку с кнопками управления, чтобы протестировать работу бота со стороны владельца канала.</i>"
        if demo_mode
        else ""
    )
    return (
        "👋 <b>Добро пожаловать в бот редакции городского канала!</b>\n\n"
        "Здесь вы можете:\n"
        "• <b>Предложить новость</b> (фото, видео, события города — анонимно или с подписью)\n"
        "• <b>Задать вопрос или отправить жалобу</b> администрации\n"
        "• <b>Разместить рекламу</b> в нашем канале\n\n"
        f"Выберите нужный раздел ниже 👇{demo_hint}"
    )


ADS_PRICE_TEXT = (
    "📢 <b>Реклама в городском Telegram-канале</b>\n\n"
    "📊 <b>Актуальные показатели:</b>\n"
    "• Средний охват поста: <b>4 500 – 7 000 просмотров</b>\n"
    "• Живая городская аудитория (вовлечённость ~32%)\n\n"
    "💳 <b>Прайс-лист на размещение:</b>\n"
    "• Формат <b>1/24</b> (1 час в топе, 24 часа в ленте) — <b>1 500 ₽</b>\n"
    "• Формат <b>2/48</b> (2 часа в топе, 48 часов в ленте) — <b>2 400 ₽</b>\n"
    "• Пост + <b>закреп на 24 часа</b> — <b>3 200 ₽</b>\n\n"
    "Готовы забронировать дату? Нажмите кнопку ниже 👇"
)


def extract_payload(messages: list[Message]) -> tuple[str, list[dict[str, str]]]:
    """Извлекает общий текст и список всех вложений из одного сообщения или медиагруппы."""
    text = ""
    media: list[dict[str, str]] = []

    for msg in messages:
        if not text:
            raw_text = msg.caption or msg.text or ""
            if raw_text.strip():
                text = raw_text.strip()

        if msg.photo:
            media.append({"type": "photo", "file_id": msg.photo[-1].file_id})
        elif msg.video:
            media.append({"type": "video", "file_id": msg.video.file_id})
        elif msg.document:
            media.append({"type": "document", "file_id": msg.document.file_id})

    return text, media


async def send_media_attachments(
    bot: Bot, chat_id: int | str, media: list[dict[str, str]]
) -> None:
    """Отправляет вложения в чат (альбомом или поодиночке), безопасно обрабатывая типы файлов."""
    if not media:
        return

    if len(media) == 1:
        item = media[0]
        if item["type"] == "photo":
            await bot.send_photo(chat_id=chat_id, photo=item["file_id"])
        elif item["type"] == "video":
            await bot.send_video(chat_id=chat_id, video=item["file_id"])
        elif item["type"] == "document":
            await bot.send_document(chat_id=chat_id, document=item["file_id"])
        return

    pv_group = []
    doc_group = []
    for item in media:
        if item["type"] == "photo":
            pv_group.append(InputMediaPhoto(media=item["file_id"]))
        elif item["type"] == "video":
            pv_group.append(InputMediaVideo(media=item["file_id"]))
        elif item["type"] == "document":
            doc_group.append(InputMediaDocument(media=item["file_id"]))

    if len(pv_group) == 1:
        single = pv_group[0]
        if isinstance(single, InputMediaPhoto):
            await bot.send_photo(chat_id=chat_id, photo=single.media)
        else:
            await bot.send_video(chat_id=chat_id, video=single.media)
    elif len(pv_group) > 1:
        await bot.send_media_group(chat_id=chat_id, media=pv_group)

    if len(doc_group) == 1:
        await bot.send_document(chat_id=chat_id, document=doc_group[0].media)
    elif len(doc_group) > 1:
        await bot.send_media_group(chat_id=chat_id, media=doc_group)


async def dispatch_ticket_to_admin(
    bot: Bot,
    config: Config,
    db: Database,
    ticket_id: int,
    user_id: int,
    full_name: str,
    username: str | None,
    category: str,
    text: str,
    media: list[dict[str, str]],
    is_anonymous: bool = True,
) -> None:
    """Отправляет карточку тикета в ADMIN_CHAT_ID или в личку тестирующему админу (если включён демо-режим)."""
    safe_name = html.escape(full_name)
    user_tag = f"@{html.escape(username)}" if username else "без username"

    if category == "news":
        anon_label = "Анонимно" if is_anonymous else "С подписью автора"
        header = f"📰 <b>Предложка #{ticket_id} | {anon_label}</b>"
        kb = admin_news_kb(ticket_id=ticket_id, user_id=user_id)
    elif category == "ads":
        header = f"📢 <b>Заявка на рекламу #{ticket_id}</b>"
        kb = admin_ticket_kb(ticket_id=ticket_id, user_id=user_id)
    else:
        header = f"🎫 <b>Тикет #{ticket_id} | Вопрос / Жалоба</b>"
        kb = admin_ticket_kb(ticket_id=ticket_id, user_id=user_id)

    safe_text = html.escape(text) if text else "<i>(без текстового описания, только медиа)</i>"

    card = (
        f"{header}\n\n"
        f"👤 <b>Отправитель:</b> {safe_name} ({user_tag})\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📎 <b>Вложений:</b> {len(media)}\n\n"
        f"📝 <b>Сообщение:</b>\n{safe_text}"
    )

    is_demo = await db.get_demo_mode(user_id)

    try:
        # Если тестирует потенциальный заказчик с включённым демо-режимом — показываем админ-карточку прямо ему
        if is_demo and user_id != config.admin_chat_id:
            await bot.send_message(
                chat_id=user_id,
                text="👀 <b>[ДЕМО-ПЕСОЧНИЦА] Так это обращение прилетает в закрытый чат админа:</b>",
            )
            if media:
                await send_media_attachments(bot, user_id, media)
            await bot.send_message(
                chat_id=user_id,
                text=card,
                reply_markup=kb,
            )
            # А владельцу бота отправляем короткое уведомление о тесте
            await bot.send_message(
                chat_id=config.admin_chat_id,
                text=(
                    f"🔔 <b>Новый тест в демо-боте!</b>\n"
                    f"👤 {safe_name} ({user_tag}) | ID: <code>{user_id}</code>\n"
                    f"📂 Категория: <b>{category}</b> (тикет #{ticket_id})"
                ),
            )
        else:
            if media:
                await send_media_attachments(bot, config.admin_chat_id, media)
            await bot.send_message(
                chat_id=config.admin_chat_id,
                text=card,
                reply_markup=kb,
            )
    except TelegramAPIError as e:
        print(f"[ERROR] Не удалось отправить карточку #{ticket_id}: {e}")


@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    demo_mode = True
    if message.from_user:
        await db.upsert_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        demo_mode = await db.get_demo_mode(message.from_user.id)

    await message.answer(
        build_welcome_text(demo_mode), reply_markup=main_menu_kb(demo_mode)
    )


@user_router.callback_query(F.data == "demo:toggle")
async def cb_toggle_demo(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user:
        return

    current = await db.get_demo_mode(callback.from_user.id)
    new_state = not current
    await db.set_demo_mode(callback.from_user.id, new_state)

    if callback.message:
        await callback.message.edit_text(
            build_welcome_text(new_state),
            reply_markup=main_menu_kb(new_state),
        )

    alert_text = (
        "Режим админа ВКЛ: карточки модерации с кнопками будут приходить прямо вам для теста."
        if new_state
        else "Режим админа ВЫКЛ: вы тестируете бота глазами обычного подписчика."
    )
    await callback.answer(alert_text, show_alert=True)


@user_router.callback_query(F.data == "back:main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    demo_mode = (
        await db.get_demo_mode(callback.from_user.id) if callback.from_user else True
    )
    if callback.message:
        await callback.message.edit_text(
            build_welcome_text(demo_mode), reply_markup=main_menu_kb(demo_mode)
        )
    await callback.answer()


@user_router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    demo_mode = (
        await db.get_demo_mode(callback.from_user.id) if callback.from_user else True
    )
    if callback.message:
        await callback.message.edit_text(
            "❌ Действие отменено.\n\n" + build_welcome_text(demo_mode),
            reply_markup=main_menu_kb(demo_mode),
        )
    await callback.answer("Отменено")


# --- 1. ВЕТКА: ПРЕДЛОЖИТЬ НОВОСТЬ ---

@user_router.callback_query(F.data == "menu:news")
async def cb_menu_news(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_news_content)
    if callback.message:
        await callback.message.edit_text(
            "📰 <b>Предложить новость</b>\n\n"
            "Отправьте текст новости, фото или видео (можно сразу альбомом из нескольких файлов).\n"
            "Опишите, что произошло и где именно:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@user_router.message(UserStates.waiting_news_content)
async def process_news_content(
    message: Message,
    state: FSMContext,
    album: list[Message] | None = None,
) -> None:
    messages = album if album else [message]
    text, media = extract_payload(messages)

    if not text and not media:
        await message.answer(
            "⚠️ Пожалуйста, отправьте текст, фото или видео новости.",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(news_text=text, news_media=media)
    await state.set_state(UserStates.waiting_news_anon)

    username_hint = (
        f"(@{html.escape(message.from_user.username)})"
        if message.from_user and message.from_user.username
        else "(по имени профиля)"
    )
    await message.answer(
        f"Как опубликовать новость в канале?\n"
        f"• <b>Анонимно</b> — редакция скроет ваши данные\n"
        f"• <b>Указать меня</b> {username_hint} — добавим подпись автора в конце поста",
        reply_markup=anonymity_kb(),
    )


@user_router.callback_query(UserStates.waiting_news_anon, F.data.startswith("anon:"))
async def process_news_anon(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    bot: Bot,
    config: Config,
) -> None:
    if not callback.from_user:
        return

    is_anonymous = callback.data == "anon:yes"
    data = await state.get_data()
    text: str = data.get("news_text", "")
    media: list[dict[str, str]] = data.get("news_media", [])

    await db.upsert_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    ticket_id = await db.create_ticket(
        user_id=callback.from_user.id,
        category="news",
        text=text,
        media=media,
        is_anonymous=is_anonymous,
    )
    demo_mode = await db.get_demo_mode(callback.from_user.id)

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            f"✅ <b>Новость #{ticket_id} отправлена редакции на проверку!</b>\n\n"
            "Мы уведомим вас, как только она будет опубликована или если потребуются уточнения.",
            reply_markup=main_menu_kb(demo_mode),
        )
    await callback.answer("Новость отправлена!")

    await dispatch_ticket_to_admin(
        bot=bot,
        config=config,
        db=db,
        ticket_id=ticket_id,
        user_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
        category="news",
        text=text,
        media=media,
        is_anonymous=is_anonymous,
    )


# --- 2. ВЕТКА: ЗАДАТЬ ВОПРОС / ЖАЛОБА ---

@user_router.callback_query(F.data == "menu:support")
async def cb_menu_support(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_support_content)
    if callback.message:
        await callback.message.edit_text(
            "💬 <b>Задать вопрос / Жалоба</b>\n\n"
            "Опишите ваш вопрос или проблему одним сообщением. "
            "При необходимости прикрепите фото или документ:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@user_router.message(UserStates.waiting_support_content)
async def process_support_content(
    message: Message,
    state: FSMContext,
    db: Database,
    bot: Bot,
    config: Config,
    album: list[Message] | None = None,
) -> None:
    if not message.from_user:
        return

    messages = album if album else [message]
    text, media = extract_payload(messages)

    if not text and not media:
        await message.answer(
            "⚠️ Пожалуйста, опишите ваш вопрос текстом или прикрепите файл.",
            reply_markup=cancel_kb(),
        )
        return

    await db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    ticket_id = await db.create_ticket(
        user_id=message.from_user.id,
        category="support",
        text=text,
        media=media,
        is_anonymous=False,
    )
    demo_mode = await db.get_demo_mode(message.from_user.id)

    await state.clear()
    await message.answer(
        f"✅ <b>Ваше обращение #{ticket_id} принято!</b>\n\n"
        "Администратор рассмотрит его в ближайшее время и ответит вам прямо в этот бот.",
        reply_markup=main_menu_kb(demo_mode),
    )

    await dispatch_ticket_to_admin(
        bot=bot,
        config=config,
        db=db,
        ticket_id=ticket_id,
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
        category="support",
        text=text,
        media=media,
        is_anonymous=False,
    )


# --- 3. ВЕТКА: КУПИТЬ РЕКЛАМУ ---

@user_router.callback_query(F.data == "menu:ads")
async def cb_menu_ads(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text(ADS_PRICE_TEXT, reply_markup=ads_menu_kb())
    await callback.answer()


@user_router.callback_query(F.data == "ads:apply")
async def cb_ads_apply(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_ads_content)
    if callback.message:
        await callback.message.edit_text(
            "📝 <b>Заявка на рекламу</b>\n\n"
            "Напишите одним сообщением:\n"
            "1. Что планируете рекламировать (ссылка / описание)\n"
            "2. Желаемый формат (1/24, 2/48, закреп) и дату выхода:",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@user_router.message(UserStates.waiting_ads_content)
async def process_ads_content(
    message: Message,
    state: FSMContext,
    db: Database,
    bot: Bot,
    config: Config,
    album: list[Message] | None = None,
) -> None:
    if not message.from_user:
        return

    messages = album if album else [message]
    text, media = extract_payload(messages)

    if not text and not media:
        await message.answer(
            "⚠️ Напишите, что вы хотите прорекламировать и на какую дату.",
            reply_markup=cancel_kb(),
        )
        return

    await db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    ticket_id = await db.create_ticket(
        user_id=message.from_user.id,
        category="ads",
        text=text,
        media=media,
        is_anonymous=False,
    )
    demo_mode = await db.get_demo_mode(message.from_user.id)

    await state.clear()
    await message.answer(
        f"✅ <b>Заявка на рекламу #{ticket_id} создана!</b>\n\n"
        "Менеджер канала скоро свяжется с вами здесь для согласования поста и оплаты.",
        reply_markup=main_menu_kb(demo_mode),
    )

    await dispatch_ticket_to_admin(
        bot=bot,
        config=config,
        db=db,
        ticket_id=ticket_id,
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
        category="ads",
        text=text,
        media=media,
        is_anonymous=False,
    )


# --- 4. ПРОДОЛЖЕНИЕ ДИАЛОГА ПО ОТКРЫТОМУ ТИКЕТУ ---

@user_router.callback_query(F.data.startswith("usr:reply:"))
async def cb_user_reply_ticket(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    ticket_id = int(callback.data.split(":")[2])
    ticket = await db.get_ticket(ticket_id)

    if not ticket:
        await callback.answer("Обращение не найдено.", show_alert=True)
        return

    if ticket["status"] in ("closed", "rejected"):
        await callback.answer(
            "Этот тикет уже закрыт. Создайте новое обращение через /start.",
            show_alert=True,
        )
        return

    await state.set_state(UserStates.waiting_ticket_reply)
    await state.update_data(reply_ticket_id=ticket_id)
    if callback.message:
        await callback.message.answer(
            f"✍️ Введите ваш ответ по обращению <b>#{ticket_id}</b> (можно прикрепить фото или файл):",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@user_router.message(UserStates.waiting_ticket_reply)
async def process_user_ticket_reply(
    message: Message,
    state: FSMContext,
    db: Database,
    bot: Bot,
    config: Config,
    album: list[Message] | None = None,
) -> None:
    if not message.from_user:
        return

    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    if not ticket_id:
        await state.clear()
        return

    ticket = await db.get_ticket(ticket_id)
    demo_mode = await db.get_demo_mode(message.from_user.id)

    if not ticket or ticket["status"] in ("closed", "rejected"):
        await state.clear()
        await message.answer(
            "ℹ️ Это обращение уже закрыто. Нажмите /start для нового запроса.",
            reply_markup=main_menu_kb(demo_mode),
        )
        return

    messages = album if album else [message]
    text, media = extract_payload(messages)

    if not text and not media:
        await message.answer(
            "⚠️ Отправьте текстовое сообщение или файл.", reply_markup=cancel_kb()
        )
        return

    await state.clear()
    await message.answer(f"✅ Ваше сообщение добавлено в обращение <b>#{ticket_id}</b>.")

    safe_name = html.escape(message.from_user.full_name)
    user_tag = (
        f"@{html.escape(message.from_user.username)}"
        if message.from_user.username
        else "без username"
    )
    safe_text = html.escape(text) if text else "<i>(вложение без текста)</i>"

    kb = (
        admin_news_kb(ticket_id, message.from_user.id)
        if ticket["category"] == "news"
        else admin_ticket_kb(ticket_id, message.from_user.id)
    )

    followup_card = (
        f"📩 <b>Новый ответ от пользователя по обращению #{ticket_id}</b>\n"
        f"👤 {safe_name} ({user_tag}) | ID: <code>{message.from_user.id}</code>\n\n"
        f"{safe_text}"
    )

    target_chat = (
        message.from_user.id
        if (demo_mode and message.from_user.id != config.admin_chat_id)
        else config.admin_chat_id
    )

    try:
        if media:
            await send_media_attachments(bot, target_chat, media)
        await bot.send_message(
            chat_id=target_chat,
            text=followup_card,
            reply_markup=kb,
        )
    except TelegramAPIError as e:
        print(f"[ERROR] Не удалось переслать ответ по тикету #{ticket_id}: {e}")
