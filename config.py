import os
from pathlib import Path

BOT_TOKEN = os.environ["BOT_TOKEN"]  # пусть падает, если не задан
TZ = os.environ.get("TZ", "Europe/Moscow")
VISIT_ASK_HOUR = int(os.environ.get("VISIT_ASK_HOUR", 20))

# путь к БД
DB_PATH = os.environ.get(
    "DB_PATH",
    str(Path(__file__).resolve().parent / "data" / "bot.sqlite3")
)