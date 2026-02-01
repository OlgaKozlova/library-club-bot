from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from storage.database import Database


UserRow = Tuple[int, Optional[str], Optional[str]]  # (user_id, username, last_activity_at)


class UsersService:
    def __init__(self, db: Database):
        self.db = db

    # ----- keyboards -----

    def filters_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Все", callback_data="users:filter:all"),
                    InlineKeyboardButton("Неактивные месяц", callback_data="users:filter:1"),
                ],
                [
                    InlineKeyboardButton("Неактивные 3 месяца", callback_data="users:filter:3"),
                    InlineKeyboardButton("Неактивные полгода", callback_data="users:filter:6"),
                ],
            ]
        )

    def list_keyboard(self, users: List[UserRow]) -> InlineKeyboardMarkup:
        rows: List[List[InlineKeyboardButton]] = []
        for user_id, username, last_activity_at in users:
            label = username or f"id:{user_id}"
            ts = self._format_last_activity(last_activity_at)
            label = f"{label} - {ts}"
            rows.append([InlineKeyboardButton(label, callback_data=f"users:user:{user_id}")])
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="users:back")])
        return InlineKeyboardMarkup(rows)

    def confirm_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Да", callback_data=f"users:confirm:{user_id}"),
                    InlineKeyboardButton("Нет", callback_data="users:cancel"),
                ]
            ]
        )

    def reset_confirm_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Да", callback_data="users:reset:confirm"),
                    InlineKeyboardButton("Нет", callback_data="users:reset:cancel"),
                ]
            ]
        )

    # ----- data operations -----

    def get_users_for_chat(self, chat_id: int, *, inactive_months: Optional[int]) -> List[UserRow]:
        return self.db.get_users_for_chat(chat_id, inactive_months=inactive_months)

    def clear_users_for_chat(self, chat_id: int) -> int:
        return self.db.clear_user_activity(chat_id)

    def delete_user_for_chat(self, chat_id: int, user_id: int) -> bool:
        return self.db.delete_user_activity(chat_id, user_id)

    def find_username_for_chat(self, chat_id: int, user_id: int) -> Optional[str]:
        users = self.db.get_users_for_chat(chat_id, inactive_months=None)
        for uid, uname, _last in users:
            if uid == user_id:
                return uname
        return None

    # ----- CSV import (/init_users) -----

    def parse_members_csv(self, text: str, *, max_len: int = 50000) -> Tuple[bool, str, List[Tuple[int, Optional[str]]]]:
        """
        Парсит CSV из сообщения.

        Возвращает (ok, message, users) где users = [(user_id, username)].
        При ok=False message содержит ошибку.
        """
        if len(text) > max_len:
            return False, "Слишком длинно. Сократите и отправьте снова: /init_users", []

        normalized = text.strip()
        buf = io.StringIO(normalized)
        reader = csv.DictReader(buf)
        if not reader.fieldnames or "user_id" not in reader.fieldnames:
            return False, "Не вижу колонку `user_id` в CSV.", []

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
            return False, "В CSV не найдено ни одной строки с корректным `user_id`.", []

        return True, "OK", users

    def import_users_if_missing_by_user_id(
        self,
        *,
        chat_id: int,
        users: List[Tuple[int, Optional[str]]],
    ) -> Tuple[int, int]:
        return self.db.insert_user_activity_if_missing_by_user_id(chat_id=chat_id, users=users)

    # ----- helpers -----

    @staticmethod
    def subtitle_for_inactive_months(inactive_months: Optional[int]) -> str:
        if inactive_months is None:
            return "Все"
        return f"Неактивные {inactive_months} мес."

    @staticmethod
    def label_for_user(user_id: int, username: Optional[str]) -> str:
        return username or f"id:{user_id}"

    @staticmethod
    def _format_last_activity(last_activity_at: Optional[str]) -> str:
        if not last_activity_at:
            return "—"
        try:
            dt = datetime.strptime(last_activity_at, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return last_activity_at

