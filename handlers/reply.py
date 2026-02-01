import random

from telegram import Update
from telegram.ext import ContextTypes

from services.book_service import BookService
from services.genre_service import GenreService
from services.history_service import HistoryService
from services.users_service import UsersService

from handlers.common import (
    PendingAction,
    USER_DATA_PROMPT_MSG_ID,
    _clear_pending,
    _get_chat_id,
    _get_chat_title_for_selected_chat_id,
    _get_pending,
    _is_admin_or_private_for_chat_id,
    _parse_index_and_optional_month_year,
    _parse_range,
    _validate_text,
    ui,
)


async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Универсальный обработчик для ForceReply-цепочек.
    Главные отличия от исходника:
    - не сравниваем reply_to_message.text
    - опираемся на context.user_data['pending_action']
    - дополнительно проверяем, что reply относится к нашему prompt-message-id
    """
    if not update.message or not update.message.text:
        return

    # Должно быть reply на конкретное сообщение
    if not update.message.reply_to_message:
        return

    pending = _get_pending(context)
    if not pending:
        return

    prompt_msg_id = context.user_data.get(USER_DATA_PROMPT_MSG_ID)
    if prompt_msg_id and update.message.reply_to_message.message_id != prompt_msg_id:
        return

    chat_id = _get_chat_id(update, context)
    user = update.effective_user
    text = update.message.text.strip()

    # Проверка на команду отмены
    if text == "-":
        _clear_pending(context)
        # await update.message.reply_text("Действие отменено")
        return

    try:
        # /init_users
        if pending == PendingAction.INIT_USERS:
            users_service: UsersService = context.bot_data["users_service"]
            ok, msg, users = users_service.parse_members_csv(text, max_len=50000)
            if not ok:
                await update.message.reply_text(msg)
                return

            chat_id = _get_chat_id(update, context)
            chat_title = _get_chat_title_for_selected_chat_id(update, context, chat_id)

            inserted, skipped = users_service.import_users_if_missing_by_user_id(chat_id=chat_id, users=users)
            await update.message.reply_text(
                f"Импорт в '{chat_title}' завершён.\n"
                f"Добавлено: {inserted}\n"
                f"Пропущено (уже были по user_id): {skipped}"
            )
            return

        # /random
        if pending == PendingAction.RANDOM:
            try:
                a, b = _parse_range(text)
                await update.message.reply_text(str(random.randint(a, b)))
            except Exception:
                await update.message.reply_text(ui.ERR_BAD_FORMAT)
            return

        # /delete (книга)
        if pending == PendingAction.DELETE_BOOK:
            if not text:
                await update.message.reply_text(ui.ERR_EMPTY.format(cmd="/delete"))
                return

            try:
                idx = int(text)
            except ValueError:
                await update.message.reply_text(ui.ERR_NOT_NUMBER.format(cmd="/delete"))
                return

            if idx < 1:
                await update.message.reply_text(ui.ERR_POSITIVE.format(cmd="/delete"))
                return

            # админ может удалить любую; обычный — только свою (логика в сервисе)
            is_admin = await _is_admin_or_private_for_chat_id(update, context, chat_id)

            service: BookService = context.bot_data["book_service"]
            success, msg = service.delete_book(chat_id, idx, user.id, is_admin)

            if success:
                await update.message.reply_text(f"{msg}\nНовый список:\n\n{service.list_books(chat_id)}")
            else:
                await update.message.reply_text(msg)
            return

        # /suggest
        if pending == PendingAction.SUGGEST:
            err = _validate_text(text, max_len=500, cmd="/suggest")
            if err:
                await update.message.reply_text(err)
                return

            service: BookService = context.bot_data["book_service"]
            ok = service.add_suggestion(
                chat_id=chat_id,
                user_id=user.id,
                username=user.username,
                text=text,
                source_message_id=update.message.message_id,
            )

            if ok:
                await update.message.reply_text(service.list_books(chat_id))
            else:
                await update.message.reply_text("Ошибка при сохранении предложения")
            return

        # /addgenre
        if pending == PendingAction.ADD_GENRE:
            if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
                await update.message.reply_text(ui.ERR_ADMIN_ONLY)
                return

            err = _validate_text(text, max_len=200, cmd="/addgenre")
            if err:
                await update.message.reply_text(err)
                return

            service: GenreService = context.bot_data["genre_service"]
            ok = service.add_genre(chat_id, text, update.message.message_id)
            if ok:
                await update.message.reply_text(service.list_genres(chat_id))
            else:
                await update.message.reply_text("Ошибка при сохранении жанра")
            return

        # /deletegenre
        if pending == PendingAction.DELETE_GENRE:
            if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
                await update.message.reply_text(ui.ERR_ADMIN_ONLY)
                return

            if not text:
                await update.message.reply_text(ui.ERR_EMPTY.format(cmd="/deletegenre"))
                return

            try:
                idx = int(text)
            except ValueError:
                await update.message.reply_text(ui.ERR_NOT_NUMBER.format(cmd="/deletegenre"))
                return

            if idx < 1:
                await update.message.reply_text(ui.ERR_POSITIVE.format(cmd="/deletegenre"))
                return

            service: GenreService = context.bot_data["genre_service"]
            ok, msg = service.delete_genre(chat_id, idx)
            if ok:
                await update.message.reply_text(f"{msg}\nНовый список:\n\n{service.list_genres(chat_id)}")
            else:
                await update.message.reply_text(msg)
            return

        # /activegenre
        if pending == PendingAction.ACTIVE_GENRE:
            if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
                await update.message.reply_text(ui.ERR_ADMIN_ONLY)
                return

            if not text:
                await update.message.reply_text(ui.ERR_EMPTY.format(cmd="/activegenre"))
                return

            try:
                idx = int(text)
            except ValueError:
                await update.message.reply_text(ui.ERR_NOT_NUMBER.format(cmd="/activegenre"))
                return

            if idx < 1:
                await update.message.reply_text(ui.ERR_POSITIVE.format(cmd="/activegenre"))
                return

            service: GenreService = context.bot_data["genre_service"]
            ok, msg = service.toggle_genre_active(chat_id, idx)
            if ok:
                await update.message.reply_text(f"{msg}\nНовый список:\n\n{service.list_genres(chat_id)}")
            else:
                await update.message.reply_text(msg)
            return

        # /save_book
        if pending == PendingAction.SAVE_BOOK:
            if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
                await update.message.reply_text(ui.ERR_ADMIN_ONLY)
                return

            try:
                idx, month_year = _parse_index_and_optional_month_year(text, cmd="/save_book")
            except ValueError as e:
                await update.message.reply_text(str(e))
                return

            history: HistoryService = context.bot_data["history_service"]
            _ok, msg = history.save_book_from_suggestions_index(chat_id, index=idx, month_year=month_year)
            await update.message.reply_text(msg)
            return

        # /save_genre
        if pending == PendingAction.SAVE_GENRE:
            if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
                await update.message.reply_text(ui.ERR_ADMIN_ONLY)
                return

            try:
                idx, month_year = _parse_index_and_optional_month_year(text, cmd="/save_genre")
            except ValueError as e:
                await update.message.reply_text(str(e))
                return

            history: HistoryService = context.bot_data["history_service"]
            _ok, msg = history.save_genre_from_index(chat_id, index=idx, month_year=month_year)
            await update.message.reply_text(msg)
            return

    finally:
        # очищаем состояние даже если что-то упало внутри
        _clear_pending(context)

