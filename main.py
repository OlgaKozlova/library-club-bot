import asyncio

from dotenv import load_dotenv

load_dotenv()


from telegram import (
    BotCommandScopeAllPrivateChats,
    Update,
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
)

from config import BOT_TOKEN, DB_PATH
from storage.database import Database
from services.book_service import BookService
from services.genre_service import GenreService

from handlers.commands import (
    suggest_command,
    list_command,
    clear_command,
    delete_command,
    random_command,
    choose_book_command,
    genres_command,
    addgenre_command,
    deletegenre_command,
    activegenre_command,
    resetgenres_command,
    handle_reply,
    handle_books_callbacks,
    pollbook_command,
    pollgenre_command,
    handle_poll_callbacks,
    handle_my_chat_member,
    chats_command,
    handle_chats_callbacks,
)

async def post_init(app: Application):
    db = Database(DB_PATH)
    app.bot_data["database"] = db
    app.bot_data["book_service"] = BookService(db)
    app.bot_data["genre_service"] = GenreService(db)

    bot_suggest_command = BotCommand("suggest", "Предложить книгу")
    bot_list_command = BotCommand("list", "Показать список предложений")
    bot_delete_command = BotCommand("delete", "Удалить книгу из списка")
    bot_random_command = BotCommand("random", "Случайное число")
    bot_choosebook_command = BotCommand("choosebook", "Выбрать случайную книгу из списка")
    bot_genres_command = BotCommand("genres", "Показать список жанров")
    bot_pollbook_command = BotCommand("pollbook", "Создать опрос с книгами")
    bot_pollgenre_command = BotCommand("pollgenre", "Создать опрос с жанрами")
    bot_chats_command = BotCommand("chats", "Показать список чатов")
    bot_clear_command = BotCommand("clear", "Очистить список предложений")
    bot_addgenre_command = BotCommand("addgenre", "Добавить жанр")
    bot_deletegenre_command = BotCommand("deletegenre", "Удалить жанр")
    bot_activegenre_command = BotCommand("activegenre", "Изменить активность жанра")
    bot_resetgenres_command = BotCommand("resetgenres", "Сбросить все жанры в активное состояние")

    # Команды для обычных пользователей в групповых чатах
    user_commands = [
        bot_suggest_command,
        bot_list_command,
        bot_delete_command,
        bot_choosebook_command,
        bot_genres_command,
        bot_pollbook_command
    ]
    await app.bot.set_my_commands(user_commands, scope=BotCommandScopeAllGroupChats())

    # Команды для администраторов в групповых чатах
    admin_commands = [
        bot_suggest_command,
        bot_list_command,
        bot_delete_command,
        bot_random_command,
        bot_choosebook_command,
        bot_clear_command,
        bot_genres_command,
        bot_addgenre_command,
        bot_deletegenre_command,
        bot_activegenre_command,
        bot_resetgenres_command,
        bot_pollbook_command,
        bot_pollgenre_command,
    ]

    await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeAllChatAdministrators())

    # Команды для всех пользователей в личных чатах
    private_commands = [
        bot_suggest_command,
        bot_list_command,
        bot_delete_command,
        bot_clear_command,
        bot_genres_command,
        bot_addgenre_command,
        bot_deletegenre_command,
        bot_activegenre_command,
        bot_resetgenres_command,
        bot_chats_command,
    ]
    await app.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())


def main():
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Команды
    application.add_handler(CommandHandler("suggest", suggest_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("choosebook", choose_book_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("genres", genres_command))
    application.add_handler(CommandHandler("addgenre", addgenre_command))
    application.add_handler(CommandHandler("deletegenre", deletegenre_command))
    application.add_handler(CommandHandler("activegenre", activegenre_command))
    application.add_handler(CommandHandler("resetgenres", resetgenres_command))
    application.add_handler(CommandHandler("pollbook", pollbook_command))
    application.add_handler(CommandHandler("pollgenre", pollgenre_command))
    application.add_handler(CommandHandler("chats", chats_command))

    # Callback-и кнопок (InlineKeyboard)
    application.add_handler(CallbackQueryHandler(handle_books_callbacks, pattern=r"^(books:|suggest:|genres:)"))
    application.add_handler(CallbackQueryHandler(handle_poll_callbacks, pattern=r"^poll:"))
    application.add_handler(CallbackQueryHandler(handle_chats_callbacks, pattern=r"^chats:"))

    # Reply (ForceReply). Должен быть после команд, чтобы не перехватывать команды.
    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))

    # Обработчик событий группы (добавление/удаление бота, изменение прав)
    application.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
