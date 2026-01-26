import asyncio

from dotenv import load_dotenv

load_dotenv()


from telegram import (
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
)

async def post_init(app: Application):
    db = Database(DB_PATH)
    app.bot_data["database"] = db
    app.bot_data["book_service"] = BookService(db)
    app.bot_data["genre_service"] = GenreService(db)

    # Команды для обычных пользователей в групповых чатах
    user_commands = [
        BotCommand("suggest", "Предложить книгу"),
        BotCommand("list", "Показать список предложений"),
        BotCommand("delete", "Удалить книгу из списка"),
        BotCommand("random", "Случайное число"),
        BotCommand("choosebook", "Выбрать случайную книгу из списка"),
        BotCommand("genres", "Показать список жанров"),
        BotCommand("pollbook", "Создать опрос с книгами"),
    ]
    await app.bot.set_my_commands(user_commands, scope=BotCommandScopeAllGroupChats())

    # Команды для администраторов в групповых чатах
    admin_commands = [
        BotCommand("suggest", "Предложить книгу"),
        BotCommand("list", "Показать список предложений"),
        BotCommand("delete", "Удалить книгу из списка"),
        BotCommand("random", "Случайное число"),
        BotCommand("choosebook", "Выбрать случайную книгу из списка"),
        BotCommand("clear", "Очистить список предложений"),
        BotCommand("genres", "Показать список жанров"),
        BotCommand("addgenre", "Добавить жанр"),
        BotCommand("deletegenre", "Удалить жанр"),
        BotCommand("activegenre", "Изменить активность жанра"),
        BotCommand("resetgenres", "Сбросить все жанры в активное состояние"),
        BotCommand("pollbook", "Создать опрос с книгами"),
        BotCommand("pollgenre", "Создать опрос с жанрами"),
        BotCommand("chats", "Показать список чатов"),
    ]
    await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeAllChatAdministrators())


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

    # Reply (ForceReply). Должен быть после команд, чтобы не перехватывать команды.
    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))

    # Обработчик событий группы (добавление/удаление бота, изменение прав)
    application.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
