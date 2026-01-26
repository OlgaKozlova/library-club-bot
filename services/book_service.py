from typing import List, Optional, Tuple
from storage.database import Database
from utils import get_poll_month_name


class BookService:
    def __init__(self, db: Database):
        self.db = db

    def add_suggestion(self, chat_id: int, user_id: int, username: Optional[str], 
                      text: str, source_message_id: int) -> bool:
        """Добавляет предложение книги. Возвращает успех операции"""
        return self.db.add_suggestion(chat_id, user_id, username, text, source_message_id)

    def list_books(self, chat_id: int) -> str:
        suggestions = self.db.get_suggestions(chat_id)
        if not suggestions:
            return "Список предложений пуст"
        
        lines = []
        for idx, (suggestion_id, user_id, username, text, source_message_id, created_at) in enumerate(suggestions, 1):
            user_str = f"@{username}" if username else f"ID:{user_id}"
            lines.append(f"{idx}. {text} (от {user_str})")
        
        return "\n".join(lines)

    def has_books(self, chat_id: int) -> bool:
        """Проверяет, есть ли книги в списке для данного чата"""
        return self.db.count_suggestions(chat_id) > 0

    def clear_books(self, chat_id: int) -> str:
        count = self.db.clear_suggestions(chat_id)
        return f"Удалено предложений: {count}"

    def delete_book(self, chat_id: int, index: int, user_id: int, is_admin: bool) -> Tuple[bool, str]:
        """
        Удаляет книгу по номеру в списке.
        Возвращает (успех, сообщение).
        Удалять может только автор книги или администратор.
        """
        suggestion = self.db.get_suggestion_by_index(chat_id, index)
        if not suggestion:
            return False, f"Книга с номером {index} не найдена"
        
        suggestion_id, author_user_id, username, text, source_message_id, created_at = suggestion
        
        # Проверяем права: автор или администратор
        if author_user_id != user_id and not is_admin:
            author_str = f"@{username}" if username else f"ID:{author_user_id}"
            return False, f"Вы можете удалять только свои книги. Эта книга предложена пользователем {author_str}"
        
        # Удаляем книгу
        success = self.db.delete_suggestion(chat_id, suggestion_id)
        if not success:
            return False, "Ошибка при удалении книги"
        
        return True, "Удалил книгу"

    def choose_random_book(self, chat_id: int) -> Optional[Tuple[int, str]]:
        """
        Выбирает случайную книгу из списка.
        Возвращает кортеж (номер_в_списке, строка_с_информацией) или None, если список пуст.
        """
        import random
        suggestions = self.db.get_suggestions(chat_id)
        if not suggestions:
            return None
        
        # Выбираем случайную книгу и её индекс
        random_index = random.randint(0, len(suggestions) - 1)
        suggestion_id, user_id, username, text, source_message_id, created_at = suggestions[random_index]
        user_str = f"@{username}" if username else f"ID:{user_id}"
        
        # Номер в списке (начиная с 1)
        book_number = random_index + 1
        book_string = f"{text} (от {user_str})"
        
        return (book_number, book_string)

    def get_books_for_poll(self, chat_id: int) -> Tuple[List[str], str]:
        """
        Получает список названий книг для опроса и название месяца.
        Возвращает кортеж (список_названий_книг, название_месяца).
        """
        suggestions = self.db.get_suggestions(chat_id)
        # Извлекаем только названия книг (text), без username
        book_titles = [text for _, _, _, text, _, _ in suggestions]
        
        # Получаем название месяца
        month_name = get_poll_month_name()
        
        return (book_titles, month_name)

    def save_poll(self, chat_id: int, poll_id: str, question: str, options: List[str], 
                  message_id: Optional[int] = None) -> bool:
        """Сохраняет опрос в базу данных. Возвращает True при успехе"""
        return self.db.add_poll(chat_id, poll_id, question, options, message_id)

    def list_polls(self, chat_id: int, status: Optional[str] = None) -> str:
        """
        Получает список опросов для чата.
        Если status указан, фильтрует по статусу ('active' или 'closed').
        """
        import json
        polls = self.db.get_polls(chat_id, status)
        if not polls:
            status_text = f" со статусом '{status}'" if status else ""
            return f"Список опросов{status_text} пуст"
        
        lines = []
        for idx, (poll_db_id, chat_id, poll_id, question, options_json, message_id, status, created_at, closed_at) in enumerate(polls, 1):
            options = json.loads(options_json)
            options_text = ", ".join(options[:3])
            if len(options) > 3:
                options_text += f" и ещё {len(options) - 3}"
            status_emoji = "🟢" if status == "active" else "🔴"
            lines.append(f"{idx}. {status_emoji} {question} ({len(options)} вариантов) - {status}")
        
        return "\n".join(lines)

    def get_active_polls(self, chat_id: int) -> List[Tuple[str, str, List[str], Optional[int]]]:
        """
        Получает список активных опросов.
        Возвращает список кортежей (poll_id, question, options, message_id).
        """
        import json
        polls = self.db.get_polls(chat_id, status="active")
        result = []
        for _, _, poll_id, question, options_json, message_id, _, _, _ in polls:
            options = json.loads(options_json)
            result.append((poll_id, question, options, message_id))
        return result

    def close_poll(self, chat_id: int, poll_id: str) -> Tuple[bool, str]:
        """
        Закрывает опрос.
        Возвращает (успех, сообщение).
        """
        success = self.db.close_poll(chat_id, poll_id)
        if success:
            return True, "Опрос закрыт"
        else:
            return False, "Опрос не найден или уже закрыт"
