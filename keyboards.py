# keyboards.py — inline-клавиатуры для пользовательских сценариев и админ-панели

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Шаблоны быстрых причин отказа по категориям
NEWS_REJECT_REASONS: dict[str, str] = {
    "0": "Уже публиковали эту новость",
    "1": "Не по теме города",
    "2": "Мало фактов или отсутствуют фото/видео",
}

TICKET_REJECT_REASONS: dict[str, str] = {
    "0": "Обращение не по теме канала / спам",
    "1": "Недостаточно информации для рассмотрения",
    "2": "Заявка не соответствует правилам канала",
}


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📰 Предложить новость", callback_data="menu:news")
    )
    builder.row(
        InlineKeyboardButton(text="💬 Задать вопрос / Жалоба", callback_data="menu:support")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Купить рекламу", callback_data="menu:ads")
    )
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def anonymity_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👤 Анонимно", callback_data="anon:yes"),
        InlineKeyboardButton(text="✍️ Указать меня", callback_data="anon:no"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def ads_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📝 Оставить заявку на рекламу", callback_data="ads:apply"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔙 В главное меню", callback_data="back:main")
    )
    return builder.as_markup()


def user_reply_kb(ticket_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="↩️ Ответить админу", callback_data=f"usr:reply:{ticket_id}"
        )
    )
    return builder.as_markup()


def admin_news_kb(ticket_id: int, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Опубликовать в канал", callback_data=f"adm:pub:{ticket_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Ответить / Уточнить", callback_data=f"adm:reply:{ticket_id}"
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"adm:rej_menu:{ticket_id}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🚫 Бан", callback_data=f"adm:ban:{user_id}:{ticket_id}"
        )
    )
    return builder.as_markup()


def admin_ticket_kb(ticket_id: int, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💬 Принять и ответить", callback_data=f"adm:reply:{ticket_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отклонить с причиной", callback_data=f"adm:rej_menu:{ticket_id}"
        ),
        InlineKeyboardButton(
            text="🔒 Закрыть тикет", callback_data=f"adm:close:{ticket_id}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🚫 Бан", callback_data=f"adm:ban:{user_id}:{ticket_id}"
        )
    )
    return builder.as_markup()


def reject_reasons_kb(ticket_id: int, category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    reasons = NEWS_REJECT_REASONS if category == "news" else TICKET_REJECT_REASONS
    for idx, label in reasons.items():
        builder.row(
            InlineKeyboardButton(
                text=label, callback_data=f"adm:rej_fast:{ticket_id}:{idx}"
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="✍️ Своя причина", callback_data=f"adm:rej_custom:{ticket_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm:back:{ticket_id}")
    )
    return builder.as_markup()


def admin_cancel_fsm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отменить действие", callback_data="adm:cancel_fsm")
    )
    return builder.as_markup()
