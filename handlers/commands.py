import random
import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple, List
from datetime import datetime

import csv
import io

from telegram import (
    Update,
    ForceReply,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes
from telegram.error import BadRequest, Forbidden

from services.book_service import BookService
from services.genre_service import GenreService
from storage.database import Database
from utils import get_poll_month_year_key


# ====== user_activity batching ======

BOT_DATA_ACTIVITY_BUFFER = "activity_buffer"
BOT_DATA_ACTIVITY_LOCK = "activity_lock"
BOT_DATA_ACTIVITY_FLUSH_TASK = "activity_flush_task"


def _get_activity_lock(app) -> asyncio.Lock:
    lock = app.bot_data.get(BOT_DATA_ACTIVITY_LOCK)
    if not lock:
        lock = asyncio.Lock()
        app.bot_data[BOT_DATA_ACTIVITY_LOCK] = lock
    return lock


def _get_activity_buffer(app) -> dict[tuple[int, int], Optional[str]]:
    buf = app.bot_data.get(BOT_DATA_ACTIVITY_BUFFER)
    if not buf:
        buf = {}
        app.bot_data[BOT_DATA_ACTIVITY_BUFFER] = buf
    return buf


async def _buffer_user_activity(chat_id: int, user_id: int, username: Optional[str], context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Пишем активность в память (без записи в БД).
    В flush будем ставить last_activity_at=CURRENT_TIMESTAMP.
    """
    app = context.application
    lock = _get_activity_lock(app)
    async with lock:
        buf = _get_activity_buffer(app)
        # сохраняем последний username, если он есть
        if username:
            buf[(chat_id, user_id)] = username
        else:
            buf.setdefault((chat_id, user_id), None)


async def flush_user_activity_buffer(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Flush: пишет накопленное в SQLite пачкой."""
    app = context.application
    lock = _get_activity_lock(app)
    async with lock:
        buf = _get_activity_buffer(app)
        if not buf:
            return
        snapshot = buf
        app.bot_data[BOT_DATA_ACTIVITY_BUFFER] = {}

    rows = [(chat_id, user_id, username) for (chat_id, user_id), username in snapshot.items()]
    if not rows:
        return

    db: Database = app.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        app.bot_data["database"] = db

    db.upsert_user_activity_many(rows)


def start_user_activity_flush_loop(app, *, interval_seconds: int = 60) -> None:
    """
    Запускает бесконечный flush-цикл без JobQueue.
    """
    if app.bot_data.get(BOT_DATA_ACTIVITY_FLUSH_TASK):
        return

    async def _loop() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            # создаём минимальный контекст-объект-обёртку: нам нужен только .application
            class _Ctx:
                __slots__ = ("application",)
                def __init__(self, application): self.application = application
            await flush_user_activity_buffer(_Ctx(app))  # type: ignore[arg-type]

    # Не используем Application.create_task до running-состояния приложения,
    # иначе PTB показывает warning и не будет автоматически await'ить задачу.
    app.bot_data[BOT_DATA_ACTIVITY_FLUSH_TASK] = asyncio.create_task(_loop())


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

    await _buffer_user_activity(chat.id, user.id, getattr(user, "username", None), context)


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

    await _buffer_user_activity(chat.id, user.id, getattr(user, "username", None), context)


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

    await _buffer_user_activity(chat.id, user.id, getattr(user, "username", None), context)


# ====== UI текст/ключи (чтобы не завязываться на сравнение строк) ======

@dataclass(frozen=True)
class UI:
    SUGGEST_PROMPT: str = "Что хотите предложить?"
    DELETE_BOOK_PROMPT: str = "Какую книгу удалить? (номер из списка)"
    RANDOM_PROMPT: str = "Введите диапазон, например 2-10"
    ADD_GENRE_PROMPT: str = "Введите название жанра:"
    DELETE_GENRE_PROMPT: str = "Введите номер жанра для удаления:"
    ACTIVE_GENRE_PROMPT: str = "Какой жанр сделать (не)активным?"
    SAVE_BOOK_PROMPT: str = "Какую книгу сохранить в историю? (номер из списка или 'номер ММ-ГГГГ')"
    SAVE_GENRE_PROMPT: str = "Какой жанр сохранить в историю? (номер из списка или 'номер ММ-ГГГГ')"
    HISTORY_EMPTY: str = "История пуста"
    HISTORY_SELECT_YEAR: str = "Выберите год:"
    INIT_USERS_PROMPT: str = (
        "Пришлите CSV со строкой заголовка (как в members.*.csv).\n"
        "Можно просто вставить текст CSV сюда.\n\n"
        "Для отмены отправьте `-`."
    )
    USERS_TITLE: str = "Пользователи"
    USERS_ERR_SELECT_GROUP: str = "Выберите групповой чат через /chats (сейчас выбран ЛС)."
    USERS_ERR_NEED_ADMIN: str = "Чтобы удалять пользователей, вы должны быть админом в выбранном чате."
    RESET_USERS_CONFIRM: str = "Удалить все данные о пользователях для чата '{chat_title}'?"
    RESET_USERS_DONE: str = "Удалено записей: {count}"

    ERR_ADMIN_ONLY: str = "Эта команда доступна только администраторам"
    ERR_PRIVATE_ONLY: str = "Эта команда доступна только в ЛС"
    ERR_ACCESS_CHECK: str = "Ошибка при проверке прав доступа"
    ERR_EMPTY: str = "Пустое сообщение. Попробуйте ещё раз: {cmd}"
    ERR_TOO_LONG: str = "Слишком длинно. Сократите и отправьте снова: {cmd}"
    ERR_NOT_NUMBER: str = "Значение должно быть числом. Попробуйте ещё раз: {cmd}"
    ERR_POSITIVE: str = "Значение должно быть положительным числом. Попробуйте ещё раз: {cmd}"
    ERR_BAD_FORMAT: str = "Неверный формат"

    LIST_EMPTY: str = "Список предложений пуст"


ui = UI()

MONTHS_RU_NOMINATIVE = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


# ====== Состояния (вместо сравнения reply_to_message.text) ======

class PendingAction:
    SUGGEST = "suggest"
    DELETE_BOOK = "delete_book"
    RANDOM = "random"
    ADD_GENRE = "add_genre"
    DELETE_GENRE = "delete_genre"
    ACTIVE_GENRE = "active_genre"
    SAVE_BOOK = "save_book"
    SAVE_GENRE = "save_genre"
    INIT_USERS = "init_users"


USER_DATA_KEY = "pending_action"
USER_DATA_PROMPT_MSG_ID = "pending_prompt_message_id"
USER_DATA_SELECTED_CHAT_ID = "selected_chat_id"


# ====== Вспомогательные функции ======

def _is_private(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and getattr(chat, "type", None) == "private")


def _get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Возвращает chat_id, с которым должны работать команды.

    Правила:
    - в ЛС: используем выбранный чат из user_data['selected_chat_id'] (по умолчанию — id ЛС)
    - в группе: выбранный чат всегда равен id группы
    """
    chat = update.effective_chat
    if not chat:
        raise ValueError("No effective_chat in update")

    if _is_private(update):
        private_chat_id = chat.id
        selected_chat_id = context.user_data.get(USER_DATA_SELECTED_CHAT_ID, private_chat_id)
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id
        return selected_chat_id

    # В группах выбранный чат всегда равен id текущей группы
    context.user_data[USER_DATA_SELECTED_CHAT_ID] = chat.id
    return chat.id


def _get_chat_title_for_selected_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    selected_chat_id: int,
) -> str:
    """
    Для ЛС: возвращает название выбранного чата.
    - если выбран id ЛС -> "Приватная беседа"
    - иначе -> title группы из БД (таблица groups), если есть
    """
    private_chat = update.effective_chat
    if private_chat and selected_chat_id == private_chat.id:
        return "Приватная беседа"

    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    group = db.get_group(selected_chat_id)
    if group:
        _chat_id, title, _chat_type, _is_active, _added_at, _updated_at = group
        return title

    # Фолбэк на случай, если группы нет в БД (например, бот уже не в группе)
    return str(selected_chat_id)


async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False

    try:
        chat = update.effective_chat
        if not chat or getattr(chat, "type", None) == "private":
            return False
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def _is_admin_or_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return _is_private(update) or await _is_admin(update, context)

async def _is_admin_in_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def _is_admin_for_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> bool:
    user = update.effective_user
    if not user:
        return False
    return await _is_admin_in_chat(context, chat_id, user.id)


async def _is_admin_or_private_for_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> bool:
    """
    Проверка прав для целевого чата:
    - если команда вызвана в ЛС и целевой чат = id ЛС, то разрешаем
    - иначе требуем админство в целевом чате
    """
    if _is_private(update):
        private_chat = update.effective_chat
        if private_chat and chat_id == private_chat.id:
            return True
    return await _is_admin_for_chat_id(update, context, chat_id)


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


def _parse_index_and_optional_month_year(text: str, *, cmd: str) -> Tuple[int, str]:
    """
    Поддерживаем ввод:
    - "1" -> индекс=1, month_year = ключ текущего месяца/года (логика как в опросах)
    - "2 01-2026" -> индекс=2, month_year="1_2026"
    """
    parts = [p for p in text.strip().split() if p]
    if not parts:
        raise ValueError(ui.ERR_EMPTY.format(cmd=cmd))

    try:
        idx = int(parts[0])
    except ValueError:
        raise ValueError(ui.ERR_NOT_NUMBER.format(cmd=cmd))
    if idx < 1:
        raise ValueError(ui.ERR_POSITIVE.format(cmd=cmd))

    if len(parts) == 1:
        return idx, get_poll_month_year_key()

    if len(parts) != 2:
        raise ValueError(ui.ERR_BAD_FORMAT)

    raw = parts[1]
    # ожидаем MM-YYYY
    try:
        mm_str, yyyy_str = raw.split("-", 1)
        mm = int(mm_str)
        yyyy = int(yyyy_str)
    except Exception:
        raise ValueError(ui.ERR_BAD_FORMAT)

    if mm < 1 or mm > 12:
        raise ValueError(ui.ERR_BAD_FORMAT)
    if yyyy < 1970 or yyyy > 3000:
        raise ValueError(ui.ERR_BAD_FORMAT)

    return idx, f"{mm}_{yyyy}"


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

    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    if not db.get_genres(chat_id):
        await update.message.reply_text("Список жанров пуст")
        return

    service: GenreService = context.bot_data["genre_service"]
    text = service.list_genres(chat_id)

    prompt_text = f"{text}\n\n{ui.SAVE_GENRE_PROMPT}"
    sent = await update.message.reply_text(prompt_text, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.SAVE_GENRE, sent.message_id)


def _history_years_keyboard(years: List[int]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for y in years:
        rows.append([InlineKeyboardButton(str(y), callback_data=f"history:year:{y}")])
    return InlineKeyboardMarkup(rows)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = _get_chat_id(update, context)
    if not await _is_admin_or_private_for_chat_id(update, context, chat_id):
        await update.message.reply_text(ui.ERR_ADMIN_ONLY)
        return

    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    years = db.get_history_years(chat_id)
    if not years:
        await update.message.reply_text(ui.HISTORY_EMPTY)
        return

    await update.message.reply_text(ui.HISTORY_SELECT_YEAR, reply_markup=_history_years_keyboard(years))


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

    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    rows = db.get_history_for_year(chat_id, year)
    if not rows:
        years = db.get_history_years(chat_id)
        if not years:
            await query.edit_message_text(ui.HISTORY_EMPTY)
            return
        await query.edit_message_text(ui.HISTORY_SELECT_YEAR, reply_markup=_history_years_keyboard(years))
        return

    lines: List[str] = []
    for month, genre, book in rows:
        month_name = MONTHS_RU_NOMINATIVE.get(month, str(month))
        g = genre if genre else "—"
        b = book if book else "—"
        lines.append(f"{month_name} - {g} - {b}")

    await query.edit_message_text("\n".join(lines))


async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not _is_private(update):
        await update.message.reply_text(ui.ERR_PRIVATE_ONLY)
        return

    private_chat_id = update.effective_chat.id
    if USER_DATA_SELECTED_CHAT_ID not in context.user_data:
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = private_chat_id

    # Получаем базу данных из bot_data
    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    # Показываем только активные группы (is_active=1)
    groups = db.get_all_groups(active_only=True)

    selected_chat_id = context.user_data.get(USER_DATA_SELECTED_CHAT_ID)
    active_group_ids = {chat_id for chat_id, *_ in groups} if groups else set()
    if selected_chat_id != private_chat_id and selected_chat_id not in active_group_ids:
        # Если ранее был выбран неактивный/недоступный чат — сбрасываем на приватную беседу
        selected_chat_id = private_chat_id
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id
    check = "✅ "

    keyboard: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            f"{check}Приватная беседа" if selected_chat_id == private_chat_id else "Приватная беседа",
            callback_data="chats:select:private",
        )]
    ]

    if groups:
        for chat_id, title, chat_type, _is_active, _added_at, _updated_at in groups:
            type_text = "супергруппа" if chat_type == "supergroup" else "группа"
            label = f"{title} ({type_text})"
            if selected_chat_id == chat_id:
                label = f"{check}{label}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"chats:select:{chat_id}")])

    await update.message.reply_text("Список чатов:", reply_markup=InlineKeyboardMarkup(keyboard))


async def init_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not _is_private(update):
        await update.message.reply_text(ui.ERR_PRIVATE_ONLY)
        return

    sent = await update.message.reply_text(ui.INIT_USERS_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.INIT_USERS, sent.message_id)


def _users_filters_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Все", callback_data="users:filter:all"),
            InlineKeyboardButton("Неактивные месяц", callback_data="users:filter:1"),
        ], [
            InlineKeyboardButton("Неактивные 3 месяца", callback_data="users:filter:3"),
            InlineKeyboardButton("Неактивные полгода", callback_data="users:filter:6"),
        ]]
    )


def _users_list_keyboard(users: List[Tuple[int, Optional[str], Optional[str]]]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for user_id, username, last_activity_at in users:
        label = username or f"id:{user_id}"
        if last_activity_at:
            try:
                # SQLite обычно возвращает "YYYY-MM-DD HH:MM:SS"
                dt = datetime.strptime(last_activity_at, "%Y-%m-%d %H:%M:%S")
                ts = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                ts = last_activity_at
        else:
            ts = "—"
        label = f"{label} - {ts}"
        rows.append([InlineKeyboardButton(label, callback_data=f"users:user:{user_id}")])
    # кнопка "назад к фильтрам"
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="users:back")])
    return InlineKeyboardMarkup(rows)


def _users_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Да", callback_data=f"users:confirm:{user_id}"),
            InlineKeyboardButton("Нет", callback_data="users:cancel"),
        ]]
    )


def _reset_users_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Да", callback_data="users:reset:confirm"),
            InlineKeyboardButton("Нет", callback_data="users:reset:cancel"),
        ]]
    )


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not _is_private(update):
        await update.message.reply_text(ui.ERR_PRIVATE_ONLY)
        return

    chat_id = _get_chat_id(update, context)
    private_chat_id = update.effective_chat.id
    if chat_id == private_chat_id:
        await update.message.reply_text(ui.USERS_ERR_SELECT_GROUP)
        return

    title = _get_chat_title_for_selected_chat_id(update, context, chat_id)
    await update.message.reply_text(f"{ui.USERS_TITLE}: {title}", reply_markup=_users_filters_keyboard())


async def reset_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not _is_private(update):
        await update.message.reply_text(ui.ERR_PRIVATE_ONLY)
        return

    chat_id = _get_chat_id(update, context)
    private_chat_id = update.effective_chat.id
    if chat_id == private_chat_id:
        await update.message.reply_text(ui.USERS_ERR_SELECT_GROUP)
        return

    chat_title = _get_chat_title_for_selected_chat_id(update, context, chat_id)
    await update.message.reply_text(
        ui.RESET_USERS_CONFIRM.format(chat_title=chat_title),
        reply_markup=_reset_users_confirm_keyboard(),
    )


async def handle_users_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    if not _is_private(update):
        await query.edit_message_text(ui.ERR_PRIVATE_ONLY)
        return

    data = getattr(query, "data", None) or ""
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != "users":
        return

    chat_id = _get_chat_id(update, context)
    private_chat_id = update.effective_chat.id
    if chat_id == private_chat_id:
        await query.edit_message_text(ui.USERS_ERR_SELECT_GROUP)
        return

    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    title = _get_chat_title_for_selected_chat_id(update, context, chat_id)

    # users:back -> фильтры
    if data == "users:back":
        await query.edit_message_text(f"{ui.USERS_TITLE}: {title}", reply_markup=_users_filters_keyboard())
        return

    # users:cancel -> отмена подтверждения
    if data == "users:cancel":
        await query.edit_message_text(f"{ui.USERS_TITLE}: {title}", reply_markup=_users_filters_keyboard())
        return

    # users:reset:confirm|cancel
    if data in ("users:reset:confirm", "users:reset:cancel"):
        if data == "users:reset:cancel":
            await query.edit_message_text(f"{ui.USERS_TITLE}: {title}", reply_markup=_users_filters_keyboard())
            return

        deleted = db.clear_user_activity(chat_id)
        await query.edit_message_text(ui.RESET_USERS_DONE.format(count=deleted), reply_markup=_users_filters_keyboard())
        return

    # users:filter:<all|months>
    if len(parts) == 3 and parts[1] == "filter":
        raw = parts[2]
        inactive_months: Optional[int]
        if raw == "all":
            inactive_months = None
            subtitle = "Все"
        else:
            try:
                inactive_months = int(raw)
            except ValueError:
                return
            subtitle = f"Неактивные {inactive_months} мес."

        users = db.get_users_for_chat(chat_id, inactive_months=inactive_months)
        if not users:
            await query.edit_message_text(f"{ui.USERS_TITLE}: {title}\n\n{subtitle}\n\nПусто.", reply_markup=_users_filters_keyboard())
            return

        await query.edit_message_text(
            f"{ui.USERS_TITLE}: {title}\n\n{subtitle}\n\nВыберите пользователя:",
            reply_markup=_users_list_keyboard(users),
        )
        return

    # users:user:<user_id> -> confirm
    if len(parts) == 3 and parts[1] == "user":
        try:
            user_id = int(parts[2])
        except ValueError:
            return

        # найдём username для красивого текста (если нет — покажем id)
        users = db.get_users_for_chat(chat_id, inactive_months=None)
        username = None
        for uid, uname, _last in users:
            if uid == user_id:
                username = uname
                break

        label = username or f"id:{user_id}"
        await query.edit_message_text(f"Удалить {label} из чата '{title}'?", reply_markup=_users_confirm_keyboard(user_id))
        return

    # users:confirm:<user_id> -> kick
    if len(parts) == 3 and parts[1] == "confirm":
        try:
            user_id = int(parts[2])
        except ValueError:
            return

        # Требуем, чтобы вызывающий был админом в целевом чате
        if not await _is_admin_for_chat_id(update, context, chat_id):
            await query.edit_message_text(ui.USERS_ERR_NEED_ADMIN, reply_markup=_users_filters_keyboard())
            return

        try:
            # "удалить из чата" = kick: ban + unban
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        except Forbidden:
            await query.edit_message_text("У бота нет прав удалять участников в этом чате.", reply_markup=_users_filters_keyboard())
            return
        except BadRequest as e:
            await query.edit_message_text(f"Не удалось удалить пользователя: {e.message}", reply_markup=_users_filters_keyboard())
            return

        # Успешно кикнули — удаляем из таблицы user_activity для этого чата
        db.delete_user_activity(chat_id, user_id)

        await query.edit_message_text("Пользователь удалён.", reply_markup=_users_filters_keyboard())
        return

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

    # Перерисовываем список с галочкой
    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    # Показываем только активные группы (is_active=1)
    groups = db.get_all_groups(active_only=True)
    active_group_ids = {chat_id for chat_id, *_ in groups} if groups else set()
    if selected_chat_id != private_chat_id and selected_chat_id not in active_group_ids:
        selected_chat_id = private_chat_id
        context.user_data[USER_DATA_SELECTED_CHAT_ID] = selected_chat_id
    check = "✅ "
    keyboard: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            f"{check}Приватная беседа" if selected_chat_id == private_chat_id else "Приватная беседа",
            callback_data="chats:select:private",
        )]
    ]
    if groups:
        for chat_id, title, chat_type, _is_active, _added_at, _updated_at in groups:
            type_text = "супергруппа" if chat_type == "supergroup" else "группа"
            label = f"{title} ({type_text})"
            if selected_chat_id == chat_id:
                label = f"{check}{label}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"chats:select:{chat_id}")])

    await query.edit_message_text("Список чатов:", reply_markup=InlineKeyboardMarkup(keyboard))


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
            # Базовая защита от слишком длинного текста
            if len(text) > 50000:
                await update.message.reply_text(ui.ERR_TOO_LONG.format(cmd="/init_users"))
                return

            # Нормализуем ввод: убираем пустые строки по краям
            normalized = text.strip()
            buf = io.StringIO(normalized)
            reader = csv.DictReader(buf)
            if not reader.fieldnames or "user_id" not in reader.fieldnames:
                await update.message.reply_text("Не вижу колонку `user_id` в CSV.")
                return

            users: List[Tuple[int, Optional[str]]] = []
            for row in reader:
                raw_user_id = (row.get("user_id") or "").strip()
                if not raw_user_id:
                    continue
                try:
                    user_id_int = int(raw_user_id)
                except ValueError:
                    continue

                # Не добавляем ботов (в members.csv is_bot обычно 0/1)
                raw_is_bot = (row.get("is_bot") or "").strip().lower()
                if raw_is_bot in ("1", "true", "yes", "y"):
                    continue

                username = (row.get("username") or "").strip() or None
                users.append((user_id_int, username))

            if not users:
                await update.message.reply_text("В CSV не найдено ни одной строки с корректным `user_id`.")
                return

            chat_id = _get_chat_id(update, context)
            chat_title = _get_chat_title_for_selected_chat_id(update, context, chat_id)

            db: Database = context.bot_data.get("database")
            if not db:
                from config import DB_PATH
                db = Database(DB_PATH)
                context.bot_data["database"] = db

            inserted, skipped = db.insert_user_activity_if_missing_by_user_id(chat_id=chat_id, users=users)
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

            db: Database = context.bot_data.get("database")
            if not db:
                from config import DB_PATH
                db = Database(DB_PATH)
                context.bot_data["database"] = db

            book = db.get_suggestion_by_index(chat_id, idx)
            if not book:
                await update.message.reply_text(f"Книга с номером {idx} не найдена")
                return

            _suggestion_id, _user_id, _username, book_text, _source_message_id, _created_at = book
            db.upsert_history_book(chat_id=chat_id, month_year=month_year, book=book_text)
            await update.message.reply_text(f"Сохранил книгу в историю за {month_year}: {book_text}")
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

            db: Database = context.bot_data.get("database")
            if not db:
                from config import DB_PATH
                db = Database(DB_PATH)
                context.bot_data["database"] = db

            genre = db.get_genre_by_index(chat_id, idx)
            if not genre:
                await update.message.reply_text(f"Жанр с номером {idx} не найден")
                return

            _genre_id, genre_title, _created_at, _source_message_id, _position, _used = genre
            db.upsert_history_genre(chat_id=chat_id, month_year=month_year, genre=genre_title)
            await update.message.reply_text(f"Сохранил жанр в историю за {month_year}: {genre_title}")
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
    chat_id = _get_chat_id(update, context)
    data = getattr(query, 'data', None) or ""

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
        text=(
            f"Книга {month_name}: вариантов больше 12, поэтому голосуем лайками 👍.\n"
        ),
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


async def handle_user_membership_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обновляет user_activity при входе/выходе пользователей в чате.
    Работает по сервисным сообщениям Telegram: new_chat_members / left_chat_member.
    """
    if not update.message:
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    chat_id = chat.id

    db: Database = context.bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        context.bot_data["database"] = db

    # Добавили новых участников
    if update.message.new_chat_members:
        for member in update.message.new_chat_members:
            # ботов не учитываем
            if getattr(member, "is_bot", False):
                continue
            db.upsert_user_activity(
                chat_id=chat_id,
                user_id=member.id,
                username=getattr(member, "username", None),
            )

    # Кто-то вышел/его удалили
    if update.message.left_chat_member:
        left = update.message.left_chat_member
        db.delete_user_activity(chat_id=chat_id, user_id=left.id)
