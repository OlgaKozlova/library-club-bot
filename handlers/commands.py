"""
Aggregator module.

`main.py` imports all handlers from `handlers/commands.py`.
Implementation is split into multiple files under `handlers/`.
This module re-exports the public handler functions to keep imports stable.
"""

from handlers.activity import (
    flush_user_activity_buffer,
    handle_any_callback_activity,
    handle_any_message_activity,
    handle_any_reaction_activity,
    start_user_activity_flush_loop,
)
from handlers.books import (
    choose_book_command,
    clear_command,
    delete_command,
    handle_books_callbacks,
    list_command,
    random_command,
    suggest_command,
)
from handlers.chats import chats_command, handle_chats_callbacks
from handlers.genres import (
    activegenre_command,
    addgenre_command,
    deletegenre_command,
    genres_command,
    resetgenres_command,
)
from handlers.history import (
    handle_history_callbacks,
    history_command,
    save_book_command,
    save_genre_command,
)
from handlers.membership import handle_my_chat_member, handle_user_membership_update
from handlers.polls import handle_poll_callbacks, pollbook_command, pollgenre_command
from handlers.reply import handle_reply
from handlers.users import (
    handle_users_callbacks,
    init_users_command,
    reset_users_command,
    users_command,
)

__all__ = [
    "suggest_command",
    "list_command",
    "clear_command",
    "delete_command",
    "random_command",
    "choose_book_command",
    "genres_command",
    "addgenre_command",
    "deletegenre_command",
    "activegenre_command",
    "resetgenres_command",
    "save_book_command",
    "save_genre_command",
    "history_command",
    "handle_history_callbacks",
    "handle_reply",
    "handle_books_callbacks",
    "pollbook_command",
    "pollgenre_command",
    "handle_poll_callbacks",
    "handle_my_chat_member",
    "chats_command",
    "handle_chats_callbacks",
    "init_users_command",
    "users_command",
    "reset_users_command",
    "handle_users_callbacks",
    "handle_user_membership_update",
    "handle_any_message_activity",
    "handle_any_callback_activity",
    "handle_any_reaction_activity",
    "flush_user_activity_buffer",
    "start_user_activity_flush_loop",
]

