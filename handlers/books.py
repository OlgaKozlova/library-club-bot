from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.book_service import BookService
from services.genre_service import GenreService

from handlers.common import (
    PendingAction,
    _get_chat_id,
    _get_chat_title_for_selected_chat_id,
    _is_private,
    _is_admin_or_private_for_chat_id,
    _set_pending,
    ui,
)


async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    sent = await update.message.reply_text(ui.SUGGEST_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.SUGGEST, sent.message_id)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    service: BookService = context.bot_data["book_service"]
    chat_id = _get_chat_id(update, context)
    text = service.list_books(chat_id)
    if _is_private(update):
        chat_title = _get_chat_title_for_selected_chat_id(update, context, chat_id)
        text = f"{chat_title}\n\n{text}"
    await update.message.reply_text(text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Подтвердить", callback_data="books:clear:confirm"),
            InlineKeyboardButton("Отмена", callback_data="books:clear:cancel"),
        ]]
    )

    await update.message.reply_text(
        "Вы уверены, что хотите очистить весь список предложений?",
        reply_markup=keyboard,
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    sent = await update.message.reply_text(ui.DELETE_BOOK_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.DELETE_BOOK, sent.message_id)


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    sent = await update.message.reply_text(ui.RANDOM_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.RANDOM, sent.message_id)


async def choose_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    service: BookService = context.bot_data["book_service"]

    if not service.has_books(chat_id):
        await update.message.reply_text(ui.LIST_EMPTY)
        return

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Подтвердить", callback_data="books:choose:confirm"),
            InlineKeyboardButton("Отмена", callback_data="books:choose:cancel"),
        ]]
    )

    await update.message.reply_text("Выбрать книгу из списка?", reply_markup=keyboard)


async def handle_books_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()
    chat_id = _get_chat_id(update, context)
    data = getattr(query, "data", None) or ""

    if data == "books:clear:confirm":
        if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
            await query.edit_message_text(ui.ERR_ADMIN_ONLY)
            return
        service: BookService = context.bot_data["book_service"]
        await query.edit_message_text(service.clear_books(chat_id))
        return

    if data == "books:clear:cancel":
        await query.edit_message_text("Очистка списка отменена")
        return

    if data == "books:choose:confirm":
        service: BookService = context.bot_data["book_service"]
        result = service.choose_random_book(chat_id)
        if not result:
            await query.edit_message_text(ui.LIST_EMPTY)
            return
        num, book = result
        await query.edit_message_text(f"Выбранная книга:\n\n{num}. {book}")
        return

    if data == "books:choose:cancel":
        await query.edit_message_text("Выбор книги отменен")
        return

    if data == "genres:reset:confirm":
        if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
            await query.edit_message_text(ui.ERR_ADMIN_ONLY)
            return

        service: GenreService = context.bot_data["genre_service"]
        ok, msg = service.reset_all_genres_active(chat_id)
        if ok:
            await query.edit_message_text(f"{msg}\n\n{service.list_genres(chat_id)}")
        else:
            await query.edit_message_text(msg)
        return

    if data == "genres:reset:cancel":
        await query.edit_message_text("Сброс жанров отменен")
        return

