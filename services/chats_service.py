from typing import List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from storage.database import Database


GroupRow = Tuple[int, str, str, int, str, str]


class ChatsService:
    def __init__(self, db: Database):
        self.db = db

    def get_active_groups(self) -> List[GroupRow]:
        # (chat_id, title, type, is_active, added_at, updated_at)
        return self.db.get_all_groups(active_only=True)

    def normalize_selected_chat_id(
        self,
        *,
        private_chat_id: int,
        selected_chat_id: Optional[int],
        active_groups: List[GroupRow],
    ) -> int:
        """
        Если selected_chat_id не задан — по умолчанию ЛС.
        Если выбран неактивный/недоступный групповой чат — сбрасываем на ЛС.
        """
        if selected_chat_id is None:
            return private_chat_id

        active_group_ids = {chat_id for chat_id, *_ in active_groups} if active_groups else set()
        if selected_chat_id != private_chat_id and selected_chat_id not in active_group_ids:
            return private_chat_id

        return selected_chat_id

    def build_keyboard(
        self,
        *,
        private_chat_id: int,
        selected_chat_id: int,
        active_groups: List[GroupRow],
    ) -> InlineKeyboardMarkup:
        check = "✅ "
        keyboard: List[List[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    f"{check}Приватная беседа" if selected_chat_id == private_chat_id else "Приватная беседа",
                    callback_data="chats:select:private",
                )
            ]
        ]

        for chat_id, title, chat_type, _is_active, _added_at, _updated_at in active_groups:
            type_text = "супергруппа" if chat_type == "supergroup" else "группа"
            label = f"{title} ({type_text})"
            if selected_chat_id == chat_id:
                label = f"{check}{label}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"chats:select:{chat_id}")])

        return InlineKeyboardMarkup(keyboard)

