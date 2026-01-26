import random
from dataclasses import dataclass
from typing import Optional, Tuple, List

from telegram import (
    Update,
    ForceReply,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes

from services.book_service import BookService
from services.genre_service import GenreService
from storage.database import Database


# ====== UI текст/ключи (чтобы не завязываться на сравнение строк) ======

@dataclass(frozen=True)
class UI:
    SUGGEST_PROMPT: str = "Что хотите предложить?"
    DELETE_BOOK_PROMPT: str = "Какую книгу удалить? (номер из списка)"
    RANDOM_PROMPT: str = "Введите диапазон, например 2-10"
    ADD_GENRE_PROMPT: str = "Введите название жанра:"
    DELETE_GENRE_PROMPT: str = "Введите номер жанра для удаления:"
    ACTIVE_GENRE_PROMPT: str = "Какой жанр сделать (не)активным?"

    ERR_ADMIN_ONLY: str = "Эта команда доступна только администраторам"
    ERR_ACCESS_CHECK: str = "Ошибка при проверке прав доступа"
    ERR_EMPTY: str = "Пустое сообщение. Попробуйте ещё раз: {cmd}"
    ERR_TOO_LONG: str = "Слишком длинно. Сократите и отправьте снова: {cmd}"
    ERR_NOT_NUMBER: str = "Значение должно быть числом. Попробуйте ещё раз: {cmd}"
    ERR_POSITIVE: str = "Значение должно быть положительным числом. Попробуйте ещё раз: {cmd}"
    ERR_BAD_FORMAT: str = "Неверный формат"

    LIST_EMPTY: str = "Список предложений пуст"


ui = UI()


# ====== Состояния (вместо сравнения reply_to_message.text) ======

class PendingAction:
    SUGGEST = "suggest"
    DELETE_BOOK = "delete_book"
    RANDOM = "random"
    ADD_GENRE = "add_genre"
    DELETE_GENRE = "delete_genre"
    ACTIVE_GENRE = "active_genre"


USER_DATA_KEY = "pending_action"
USER_DATA_PROMPT_MSG_ID = "pending_prompt_message_id"


# ====== Вспомогательные функции ======

async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(chat_id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def _set_pending(context: ContextTypes.DEFAULT_TYPE, action: str, prompt_message_id: int) -> None:
    context.user_data[USER_DATA_KEY] = action
    context.user_data[USER_DATA_PROMPT_MSG_ID] = prompt_message_id


def _clear_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(USER_DATA_KEY, None)
    context.user_data.pop(USER_DATA_PROMPT_MSG_ID, None)


def _get_pending(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    return context.user_data.get(USER_DATA_KEY)


def _parse_range(text: str) -> Tuple[int, int]:
    # поддерживаем: "2-10", "2 - 10", "2- 10", "2 -10"
    parts = text.replace(" ", "").split("-")
    if len(parts) != 2:
        raise ValueError("bad format")
    a = int(parts[0])
    b = int(parts[1])
    if a > b:
        a, b = b, a
    return a, b


def _validate_text(text: str, *, max_len: int, cmd: str) -> Optional[str]:
    if not text.strip():
        return ui.ERR_EMPTY.format(cmd=cmd)
    if len(text) > max_len:
        return ui.ERR_TOO_LONG.format(cmd=cmd)
    return None


# ====== Команды ======

async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    sent = await update.message.reply_text(ui.SUGGEST_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.SUGGEST, sent.message_id)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    service: BookService = context.bot_data["book_service"]
    await update.message.reply_text(service.list_books(chat_id))


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not await _is_admin(update, context):
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


async def genres_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    service: GenreService = context.bot_data["genre_service"]
    await update.message.reply_text(service.list_genres(chat_id))


async def addgenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not await _is_admin(update, context):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    sent = await update.message.reply_text(ui.ADD_GENRE_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.ADD_GENRE, sent.message_id)


async def deletegenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not await _is_admin(update, context):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    sent = await update.message.reply_text(ui.DELETE_GENRE_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.DELETE_GENRE, sent.message_id)


async def activegenre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not await _is_admin(update, context):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    sent = await update.message.reply_text(ui.ACTIVE_GENRE_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.ACTIVE_GENRE, sent.message_id)


async def resetgenres_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not await _is_admin(update, context):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

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


async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not await _is_admin(update, context):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    # Получаем базу данных из bot_data
    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    # Получаем все группы (включая неактивные)
    groups = db.get_all_groups(active_only=False)
    
    if not groups:
        await update.message.reply_text("Список чатов пуст")
        return

    lines = []
    for chat_id, title, chat_type, is_active, added_at, updated_at in groups:
        status_emoji = "🟢" if is_active else "🔴"
        type_text = "супергруппа" if chat_type == "supergroup" else "группа"
        lines.append(f"{status_emoji} {title} ({type_text}, ID: {chat_id})")
    
    result = "Список чатов:\n\n" + "\n".join(lines)
    await update.message.reply_text(result)


async def choose_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
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


# ====== Единый обработчик reply (ForceReply) ======

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

    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.strip()

    # Проверка на команду отмены
    if text == "-":
        _clear_pending(context)
       # await update.message.reply_text("Действие отменено")
        return

    try:
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
            is_admin = await _is_admin(update, context)

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
            if not await _is_admin(update, context):
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
            if not await _is_admin(update, context):
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
            if not await _is_admin(update, context):
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

    finally:
        # очищаем состояние даже если что-то упало внутри
        _clear_pending(context)


# ====== Callback-и (InlineKeyboard) ======

async def handle_books_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()
    chat_id = update.effective_chat.id
    data = getattr(query, 'data', None) or ""

    if data == "books:clear:confirm":
        if not await _is_admin(update, context):
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
        if not await _is_admin(update, context):
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


async def pollbook_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    service: BookService = context.bot_data["book_service"]

    book_titles, month_name = service.get_books_for_poll(chat_id)
    if not book_titles:
        await update.message.reply_text(ui.LIST_EMPTY)
        return

    if len(book_titles) > 12:
        await update.message.reply_text(
            f"Слишком много книг в списке ({len(book_titles)}). Максимум 12 вариантов для опроса."
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
    chat_id = update.effective_chat.id
    data = getattr(query, 'data', None) or ""

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
            await query.edit_message_text(
                f"Слишком много книг в списке ({len(book_titles)}). Максимум 12 вариантов для опроса."
            )
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
        if not await _is_admin(update, context):
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

    if not await _is_admin(update, context):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    chat_id = update.effective_chat.id
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


# ====== Обработчик событий группы ======

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает изменения статуса бота в чате (добавление, удаление, изменение прав).
    """
    if not update.my_chat_member:
        return
    
    chat_member = update.my_chat_member
    chat = chat_member.chat
    new_status = chat_member.new_chat_member.status
    
    # Обрабатываем только групповые чаты
    if chat.type not in ("group", "supergroup"):
        return
    
    chat_id = chat.id
    chat_title = chat.title or "Unknown"
    chat_type = "supergroup" if chat.type == "supergroup" else "group"
    
    # Получаем базу данных из bot_data
    db: Database = context.bot_data.get("database")
    if not db:
        # Если database не в bot_data, создаем новый экземпляр
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db
    
    # Статусы бота в чате:
    # - "member" - обычный участник
    # - "administrator" - администратор
    # - "left" - покинул чат
    # - "kicked" - удален из чата
    
    if new_status in ("member", "administrator"):
        # Бот добавлен в группу или назначен администратором
        is_active = 1
        db.add_or_update_group(chat_id, chat_title, chat_type, is_active)
    elif new_status in ("left", "kicked"):
        # Бот удален из группы
        db.remove_group(chat_id)
