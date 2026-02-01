from telegram import Update
from telegram.ext import ContextTypes

from services.chats_service import ChatsService

from handlers.common import (
    USER_DATA_SELECTED_CHAT_ID,
    _is_private,
    ui,
)


async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not _is_private(update):
        await update.message.reply_text(ui.ERR_PRIVATE_ONLY)
        return

    private_chat_id = update.effective_chat.id
    if USER_DATA_SELECTED_CHAT_ID not in context.user_data:
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = private_chat_id

    chats: ChatsService = context.bot_data["chats_service"]
    groups = chats.get_active_groups()
    selected_chat_id = chats.normalize_selected_chat_id(
        private_chat_id=private_chat_id,
        selected_chat_id=context.user_data.get(USER_DATA_SELECTED_CHAT_ID),
        active_groups=groups,
    )
    context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id
    keyboard = chats.build_keyboard(
        private_chat_id=private_chat_id,
        selected_chat_id=selected_chat_id,
        active_groups=groups,
    )
    await update.message.reply_text("Список чатов:", reply_markup=keyboard)


async def handle_chats_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    # На всякий случай — выбор чатов делаем только из ЛС
    if not _is_private(update):
        await query.edit_message_text(ui.ERR_PRIVATE_ONLY)
        return

    private_chat_id = update.effective_chat.id

    data = getattr(query, "data", None) or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "chats" or parts[1] != "select":
        return

    raw = parts[2]
    if raw == "private":
        selected_chat_id = private_chat_id
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id
    else:
        try:
            selected_chat_id = int(raw)
        except ValueError:
            return
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id

    chats: ChatsService = context.bot_data["chats_service"]
    groups = chats.get_active_groups()
    selected_chat_id = chats.normalize_selected_chat_id(
        private_chat_id=private_chat_id,
        selected_chat_id=selected_chat_id,
        active_groups=groups,
    )
    context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id
    keyboard = chats.build_keyboard(
        private_chat_id=private_chat_id,
        selected_chat_id=selected_chat_id,
        active_groups=groups,
    )
    await query.edit_message_text("Список чатов:", reply_markup=keyboard)

