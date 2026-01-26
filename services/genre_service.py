from typing import List, Optional, Tuple
from storage.database import Database
from utils import get_poll_month_name


class GenreService:
    def __init__(self, db: Database):
        self.db = db

    def add_genre(self, chat_id: int, title: str, source_message_id: int) -> bool:
        """Добавляет жанр. Возвращает успех операции"""
        return self.db.add_genre(chat_id, title, source_message_id)

    def list_genres(self, chat_id: int) -> str:
        """Возвращает список жанров в виде строки"""
        genres = self.db.get_genres(chat_id)
        if not genres:
            return "Список жанров пуст"
        
        lines = []
        for idx, (genre_id, title, created_at, source_message_id, position, used) in enumerate(genres, 1):
            # Зеленая галочка если used = 0 (active), белый круг если used = 1 (неактивен)
            indicator = "🟢" if used == 0 else "⚪"
            lines.append(f"{idx}. {title} {indicator}")
        
        return "\n".join(lines)

    def delete_genre(self, chat_id: int, index: int) -> Tuple[bool, str]:
        """
        Удаляет жанр по номеру в списке.
        Возвращает (успех, сообщение).
        """
        genre = self.db.get_genre_by_index(chat_id, index)
        if not genre:
            return False, f"Жанр с номером {index} не найден"
        
        genre_id, title, created_at, source_message_id, position, used = genre
        
        # Удаляем жанр
        success = self.db.delete_genre(chat_id, genre_id)
        if not success:
            return False, "Ошибка при удалении жанра"
        
        return True, "Удалил жанр"

    def get_genres_for_poll(self, chat_id: int) -> Tuple[List[str], str]:
        """
        Получает список названий жанров с used=0 (active) для опроса и название месяца.
        Возвращает кортеж (список_названий_жанров, название_месяца).
        """
        genres = self.db.get_genres(chat_id)
        # Фильтруем только активные жанры (used=0) и извлекаем названия
        genre_titles = [title for _, title, _, _, _, used in genres if used == 0]
        
        # Получаем название месяца
        month_name = get_poll_month_name()
        
        return (genre_titles, month_name)

    def toggle_genre_active(self, chat_id: int, index: int) -> Tuple[bool, str]:
        """
        Переключает флаг активности жанра по номеру в списке.
        Возвращает (успех, сообщение).
        """
        genre = self.db.get_genre_by_index(chat_id, index)
        if not genre:
            return False, f"Жанр с номером {index} не найден"
        
        genre_id, title, created_at, source_message_id, position, used = genre
        
        success, new_active = self.db.toggle_genre_active(chat_id, genre_id)
        if not success:
            return False, "Ошибка при изменении активности жанра"
        
        status = "активным" if new_active else "неактивным"
        return True, f"Жанр '{title}' теперь {status}"

    def reset_all_genres_active(self, chat_id: int) -> Tuple[bool, str]:
        """
        Устанавливает все жанры в активное состояние.
        Возвращает (успех, сообщение).
        """
        count = self.db.reset_all_genres_active(chat_id)
        if count == 0:
            return False, "Нет жанров для обновления"
        return True, f"Все жанры ({count}) переведены в активное состояние"
