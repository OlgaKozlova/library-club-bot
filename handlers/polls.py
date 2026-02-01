import asyncio
from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.book_service import BookService
from services.genre_service import GenreService

from handlers.common import _get_chat_id, _is_admin_or_private_for_chat_id, ui


async def _send_books_like_vote(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    month_name: str,
    book_titles: List[str],
) -> None:
    """
    Фолбэк вместо стандартного Poll, когда вариантов > 12.
    Отправляет каждую книгу отдельным сообщением, чтобы пользователи голосовали реакциями 👍.
    """
    await context.bot.send_message(
        chat_id=chat_id,
        text=(f"Книга {month_name}: вариантов больше 12, поэтому голосуем лайками 👍.\n"),
    )
    for i, title in enumerate(book_titles, 1):
        await context.bot.send_message(chat_id=chat_id, text=f"{i}. {title}")
        # маленькая пауза, чтобы снизить риск флуда в чате
        await asyncio.sleep(0.05)


async def pollbook_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    service: BookService = context.bot_data["book_service"]

    book_titles, month_name = service.get_books_for_poll(chat_id)
    if not book_titles:
        await update.message.reply_text(ui.LIST_EMPTY)
        return

    if len(book_titles) > 12:
        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Подтвердить", callback_data="poll:book:confirm"),
                InlineKeyboardButton("Отмена", callback_data="poll:book:cancel"),
            ]]
        )

        question_preview = f"Книга {month_name} (лайки 👍)"
        await update.message.reply_text(
            f"В списке {len(book_titles)} книг — это больше 12, поэтому классический опрос создать нельзя.\n"
            f"Сделать голосование лайками (каждая книга отдельным сообщением)?\n\n"
            f"Создать '{question_preview}'?",
            reply_markup=keyboard,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Подтвердить", callback_data="poll:book:confirm"),
            InlineKeyboardButton("Отмена", callback_data="poll:book:cancel"),
        ]]
    )

    question_preview = f"Книга {month_name}"
    await update.message.reply_text(f"Создать опрос '{question_preview}'?", reply_markup=keyboard)


async def handle_poll_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()
    chat_id = _get_chat_id(update, context)
    data = getattr(query, "data", None) or ""

    # poll book
    if data in ("poll:book:confirm", "poll:book:cancel"):
        if data == "poll:book:cancel":
            await query.edit_message_text("Создание опроса отменено")
            return

        service: BookService = context.bot_data["book_service"]
        book_titles, month_name = service.get_books_for_poll(chat_id)
        if not book_titles:
            await query.edit_message_text(ui.LIST_EMPTY)
            return
        if len(book_titles) > 12:
            await query.delete_message()
            await _send_books_like_vote(chat_id=chat_id, context=context, month_name=month_name, book_titles=book_titles)
            return

        question = f"Книга {month_name}?"
        await query.delete_message()
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question,
            options=book_titles,
            is_anonymous=False,
            allows_multiple_answers=True,
        )

        if poll_message.poll:
            service.save_poll(
                chat_id=chat_id,
                poll_id=poll_message.poll.id,
                question=question,
                options=book_titles,
                message_id=poll_message.message_id,
            )
        return

    # poll genre
    if data in ("poll:genre:confirm", "poll:genre:cancel"):
        if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
            await query.edit_message_text(ui.ERR_ADMIN_ONLY)
            return

        if data == "poll:genre:cancel":
            await query.edit_message_text("Создание опроса отменено")
            return

        genre_service: GenreService = context.bot_data["genre_service"]
        genre_titles, month_name = genre_service.get_genres_for_poll(chat_id)
        if not genre_titles:
            await query.edit_message_text("Нет жанров с used=0")
            return
        if len(genre_titles) > 12:
            await query.edit_message_text(
                f"Слишком много жанров в списке ({len(genre_titles)}). Максимум 12 вариантов для опроса."
            )
            return

        question = f"Жанр {month_name}?"
        await query.delete_message()
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question,
            options=genre_titles,
            is_anonymous=False,
            allows_multiple_answers=False,
        )

        if poll_message.poll:
            # если ты специально сохраняешь все опросы в book_service — оставляю как было
            book_service: BookService = context.bot_data["book_service"]
            book_service.save_poll(
                chat_id=chat_id,
                poll_id=poll_message.poll.id,
                question=question,
                options=genre_titles,
                message_id=poll_message.message_id,
            )
        return


async def pollgenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    service: GenreService = context.bot_data["genre_service"]

    genre_titles, month_name = service.get_genres_for_poll(chat_id)
    if not genre_titles:
        await update.message.reply_text("Нет жанров с used=0")
        return

    if len(genre_titles) > 12:
        await update.message.reply_text(
            f"Слишком много жанров в списке ({len(genre_titles)}). Максимум 12 вариантов для опроса."
        )
        return

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Подтвердить", callback_data="poll:genre:confirm"),
            InlineKeyboardButton("Отмена", callback_data="poll:genre:cancel"),
        ]]
    )

    question_preview = f"Жанр {month_name}"
    await update.message.reply_text(f"Создать опрос '{question_preview}'?", reply_markup=keyboard)

