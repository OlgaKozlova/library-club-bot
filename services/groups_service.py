from storage.database import Database


class GroupsService:
    def __init__(self, db: Database):
        self.db = db

    def apply_bot_membership_update(
        self,
        *,
        chat_id: int,
        chat_title: str,
        chat_type: str,
        new_status: str,
    ) -> None:
        """
        Синхронизирует таблицу groups по статусу бота в чате.

        chat_type ожидается: "group" | "supergroup"
        new_status ожидается как Telegram ChatMember.status
        """
        if new_status in ("member", "administrator"):
            self.db.add_or_update_group(chat_id, chat_title, chat_type, is_active=1)
            return

        if new_status in ("left", "kicked"):
            self.db.remove_group(chat_id)
            return

