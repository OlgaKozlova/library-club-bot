import asyncio
from typing import Optional

from telegram.ext import ContextTypes

from storage.database import Database


BOT_DATA_ACTIVITY_BUFFER = "activity_buffer"
BOT_DATA_ACTIVITY_LOCK = "activity_lock"
BOT_DATA_ACTIVITY_FLUSH_TASK = "activity_flush_task"


def _get_db_from_bot_data(bot_data) -> Database:
    """
    Возвращает Database из bot_data, создавая при отсутствии.

    Импортируем DB_PATH лениво, чтобы импорт модуля не падал,
    если переменные окружения (например BOT_TOKEN) ещё не подгружены.
    """
    db: Database = bot_data.get("database")
    if not db:
        from config import DB_PATH
        db = Database(DB_PATH)
        bot_data["database"] = db
    return db


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


async def buffer_user_activity(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
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

    db = _get_db_from_bot_data(app.bot_data)
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

                def __init__(self, application):
                    self.application = application

            await flush_user_activity_buffer(_Ctx(app))  # type: ignore[arg-type]

    # Не используем Application.create_task до running-состояния приложения,
    # иначе PTB показывает warning и не будет автоматически await'ить задачу.
    app.bot_data[BOT_DATA_ACTIVITY_FLUSH_TASK] = asyncio.create_task(_loop())

