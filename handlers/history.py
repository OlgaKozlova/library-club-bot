from telegram import ForceReply, Update
from telegram.ext import ContextTypes

from services.book_service import BookService
from services.genre_service import GenreService
from services.history_service import HistoryService

from handlers.common import (
    PendingAction,
    _get_chat_id,
    _is_admin_or_private_for_chat_id,
    _set_pending,
    get_db,
    ui,
)


async def save_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    service: BookService = context.bot_data["book_service"]
    if not service.has_books(chat_id):
        await update.message.reply_text(ui.LIST_EMPTY)
        return

    prompt_text = f"{service.list_books(chat_id)}\n\n{ui.SAVE_BOOK_PROMPT}"
    sent = await update.message.reply_text(prompt_text, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.SAVE_BOOK, sent.message_id)


async def save_genre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    db = get_db(context)
    if not db.get_genres(chat_id):
        await update.message.reply_text("Список жанров пуст")
        return

    service: GenreService = context.bot_data["genre_service"]
    text = service.list_genres(chat_id)

    prompt_text = f"{text}\n\n{ui.SAVE_GENRE_PROMPT}"
    sent = await update.message.reply_text(prompt_text, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.SAVE_GENRE, sent.message_id)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    service: HistoryService = context.bot_data["history_service"]
    years = service.get_years(chat_id)
    if not years:
        await update.message.reply_text(ui.HISTORY_EMPTY)
        return

    await update.message.reply_text(ui.HISTORY_SELECT_YEAR, reply_markup=service.years_keyboard(years))


async def handle_history_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await query.edit_message_text(ui.ERR_ADMIN_ONLY)
        return

    data = getattr(query, "data", None) or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "history" or parts[1] != "year":
        return

    try:
        year = int(parts[2])
    except ValueError:
        return

    service: HistoryService = context.bot_data["history_service"]
    text = service.get_year_text(chat_id, year)
    if not text:
        years = service.get_years(chat_id)
        if not years:
            await query.edit_message_text(ui.HISTORY_EMPTY)
            return
        await query.edit_message_text(ui.HISTORY_SELECT_YEAR, reply_markup=service.years_keyboard(years))
        return

    await query.edit_message_text(text)

