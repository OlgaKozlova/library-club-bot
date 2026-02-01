from telegram import Update
from telegram.ext import ContextTypes

from services.groups_service import GroupsService
from handlers.common import get_db


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

    groups: GroupsService = context.bot_data["groups_service"]
    groups.apply_bot_membership_update(
        chat_id=chat_id,
        chat_title=chat_title,
        chat_type=chat_type,
        new_status=new_status,
    )


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

    db = get_db(context)

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

