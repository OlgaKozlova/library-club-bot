from typing import Optional

from telegram import ForceReply, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from services.users_service import UsersService

from handlers.common import (
    PendingAction,
    _get_chat_id,
    _get_chat_title_for_selected_chat_id,
    _is_admin_for_chat_id,
    _is_private,
    _set_pending,
    ui,
)


async def init_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not _is_private(update):
        await update.message.reply_text(ui.ERR_PRIVATE_ONLY)
        return

    sent = await update.message.reply_text(ui.INIT_USERS_PROMPT, reply_markup=ForceReply(selective=True))
    _set_pending(context, PendingAction.INIT_USERS, sent.message_id, update.effective_user.id)


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
    users_service: UsersService = context.bot_data["users_service"]
    await update.message.reply_text(f"{ui.USERS_TITLE}: {title}", reply_markup=users_service.filters_keyboard())


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
    users_service: UsersService = context.bot_data["users_service"]
    await update.message.reply_text(
        ui.RESET_USERS_CONFIRM.format(chat_title=chat_title),
        reply_markup=users_service.reset_confirm_keyboard(),
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

    users_service: UsersService = context.bot_data["users_service"]
    title = _get_chat_title_for_selected_chat_id(update, context, chat_id)

    # users:back -> фильтры
    if data == "users:back":
        await query.edit_message_text(f"{ui.USERS_TITLE}: {title}", reply_markup=users_service.filters_keyboard())
        return

    # users:cancel -> отмена подтверждения
    if data == "users:cancel":
        await query.edit_message_text(f"{ui.USERS_TITLE}: {title}", reply_markup=users_service.filters_keyboard())
        return

    # users:reset:confirm|cancel
    if data in ("users:reset:confirm", "users:reset:cancel"):
        if data == "users:reset:cancel":
            await query.edit_message_text(f"{ui.USERS_TITLE}: {title}", reply_markup=users_service.filters_keyboard())
            return

        deleted = users_service.clear_users_for_chat(chat_id)
        await query.edit_message_text(ui.RESET_USERS_DONE.format(count=deleted), reply_markup=users_service.filters_keyboard())
        return

    # users:filter:<all|months>
    if len(parts) == 3 and parts[1] == "filter":
        raw = parts[2]
        inactive_months: Optional[int]
        if raw == "all":
            inactive_months = None
            subtitle = users_service.subtitle_for_inactive_months(inactive_months)
        else:
            try:
                inactive_months = int(raw)
            except ValueError:
                return
            subtitle = users_service.subtitle_for_inactive_months(inactive_months)

        users = users_service.get_users_for_chat(chat_id, inactive_months=inactive_months)
        if not users:
            await query.edit_message_text(
                f"{ui.USERS_TITLE}: {title}\n\n{subtitle}\n\nПусто.",
                reply_markup=users_service.filters_keyboard(),
            )
            return

        await query.edit_message_text(
            f"{ui.USERS_TITLE}: {title}\n\n{subtitle}\n\nВыберите пользователя:",
            reply_markup=users_service.list_keyboard(users),
        )
        return

    # users:user:<user_id> -> confirm
    if len(parts) == 3 and parts[1] == "user":
        try:
            user_id = int(parts[2])
        except ValueError:
            return

        username = users_service.find_username_for_chat(chat_id, user_id)
        label = users_service.label_for_user(user_id, username)
        await query.edit_message_text(
            f"Удалить {label} из чата '{title}'?",
            reply_markup=users_service.confirm_keyboard(user_id),
        )
        return

    # users:confirm:<user_id> -> kick
    if len(parts) == 3 and parts[1] == "confirm":
        try:
            user_id = int(parts[2])
        except ValueError:
            return

        # Требуем, чтобы вызывающий был админом в целевом чате
        if not await _is_admin_for_chat_id(update, context, chat_id):
            await query.edit_message_text(ui.USERS_ERR_NEED_ADMIN, reply_markup=users_service.filters_keyboard())
            return

        try:
            # "удалить из чата" = kick: ban + unban
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        except Forbidden:
            await query.edit_message_text("У бота нет прав удалять участников в этом чате.", reply_markup=users_service.filters_keyboard())
            return
        except BadRequest as e:
            await query.edit_message_text(f"Не удалось удалить пользователя: {e.message}", reply_markup=users_service.filters_keyboard())
            return

        users_service.delete_user_for_chat(chat_id, user_id)

        await query.edit_message_text("Пользователь удалён.", reply_markup=users_service.filters_keyboard())
        return

