from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.genre_service import GenreService

from handlers.common import (
    PendingAction,
    _get_chat_id,
    _get_chat_title_for_selected_chat_id,
    _is_admin_or_private_for_chat_id,
    _is_private,
    _set_pending,
    ui,
)


async def genres_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    service: GenreService = context.bot_data["genre_service"]
    text = service.list_genres(chat_id)
    if _is_private(update):
        chat_title = _get_chat_title_for_selected_chat_id(update, context, chat_id)
        text = f"{chat_title}\n\n{text}"
    await update.message.reply_text(text)


async def addgenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    sent = await update.message.reply_text(ui.ADD_GENRE_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.ADD_GENRE, sent.message_id)


async def deletegenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    sent = await update.message.reply_text(ui.DELETE_GENRE_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.DELETE_GENRE, sent.message_id)


async def activegenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    sent = await update.message.reply_text(ui.ACTIVE_GENRE_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.ACTIVE_GENRE, sent.message_id)

async def resetgenres_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    # подтверждение обрабатывается в handle_books_callbacks (genres:reset:*)
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Да", callback_data="genres:reset:confirm"),
            InlineKeyboardButton("Нет", callback_data="genres:reset:cancel"),
        ]]
    )

    await update.message.reply_text(
        "Вы уверены, что хотите перевести все жанры в активное состояние?",
        reply_markup=keyboard,
    )

