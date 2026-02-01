from telegram import Update
from telegram.ext import ContextTypes

from services.user_activity_service import (
    buffer_user_activity,
    flush_user_activity_buffer,
    start_user_activity_flush_loop,
)


async def handle_any_message_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отмечает last_activity_at для любого сообщения пользователя в группе/супергруппе.
    Не отвечает в чат — только буферизует.
    """
    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup") or not user:
        return
    if getattr(user, "is_bot", False):
        return

    await buffer_user_activity(chat.id, user.id, getattr(user, "username", None), context)


async def handle_any_callback_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмечает активность по кликам на inline-кнопки (в группах)."""
    query = update.callback_query
    if not query:
        return

    msg = getattr(query, "message", None)
    chat = getattr(msg, "chat", None) if msg else None
    user = getattr(query, "from_user", None)
    if not chat or chat.type not in ("group", "supergroup") or not user:
        return
    if getattr(user, "is_bot", False):
        return

    await buffer_user_activity(chat.id, user.id, getattr(user, "username", None), context)


async def handle_any_reaction_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмечает активность по реакциям (лайкам) на сообщения в группах."""
    mr = getattr(update, "message_reaction", None)
    if not mr:
        return

    chat = getattr(mr, "chat", None)
    user = getattr(mr, "user", None)
    if not chat or chat.type not in ("group", "supergroup") or not user:
        return
    if getattr(user, "is_bot", False):
        return

    await buffer_user_activity(chat.id, user.id, getattr(user, "username", None), context)

