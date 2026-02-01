from dataclasses import dataclass
from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from storage.database import Database
from utils import get_poll_month_year_key


# ====== Database access (single point) ======

def _get_db_from_bot_data(bot_data) -> Database:
    """
    Возвращает Database из bot_data, создавая при отсутствии.

    Важно: импортируем DB_PATH лениво, чтобы импорт этого модуля не падал,
    если BOT_TOKEN не задан (config.py читает его при импорте).
    """
    db: Database = bot_data.get("database")
    if not db:
        from config import DB_PATH

        db = Database(DB_PATH)
        bot_data["database"] = db
    return db


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return _get_db_from_bot_data(context.bot_data)


def get_db_from_app(app) -> Database:
    return _get_db_from_bot_data(app.bot_data)


# ====== UI текст/ключи ======


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


# ====== Состояния (ForceReply) ======


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

    db = get_db(context)
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


async def _is_admin_in_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def _is_admin_for_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
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

