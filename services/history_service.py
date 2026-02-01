from typing import List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from storage.database import Database


MONTHS_RU_NOMINATIVE = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


class HistoryService:
    def __init__(self, db: Database):
        self.db = db

    def years_keyboard(self, years: List[int]) -> InlineKeyboardMarkup:
        rows: List[List[InlineKeyboardButton]] = []
        for y in years:
            rows.append([InlineKeyboardButton(str(y), callback_data=f"history:year:{y}")])
        return InlineKeyboardMarkup(rows)

    def get_years(self, chat_id: int) -> List[int]:
        return self.db.get_history_years(chat_id)

    def get_year_text(self, chat_id: int, year: int) -> Optional[str]:
        """
        Возвращает готовый текст истории за год или None, если за год нет строк.
        """
        rows = self.db.get_history_for_year(chat_id, year)
        if not rows:
            return None

        lines: List[str] = []
        for month, genre, book in rows:
            month_name = MONTHS_RU_NOMINATIVE.get(month, str(month))
            g = genre if genre else "—"
            b = book if book else "—"
            lines.append(f"{month_name} - {g} - {b}")
        return "\n".join(lines)

    def save_book_from_suggestions_index(
        self,
        chat_id: int,
        *,
        index: int,
        month_year: str,
    ) -> Tuple[bool, str]:
        book = self.db.get_suggestion_by_index(chat_id, index)
        if not book:
            return False, f"Книга с номером {index} не найдена"

        _suggestion_id, _user_id, _username, book_text, _source_message_id, _created_at = book
        self.db.upsert_history_book(chat_id=chat_id, month_year=month_year, book=book_text)
        return True, f"Сохранил книгу в историю за {month_year}: {book_text}"

    def save_genre_from_index(
        self,
        chat_id: int,
        *,
        index: int,
        month_year: str,
    ) -> Tuple[bool, str]:
        genre = self.db.get_genre_by_index(chat_id, index)
        if not genre:
            return False, f"Жанр с номером {index} не найден"

        _genre_id, genre_title, _created_at, _source_message_id, _position, _used = genre
        self.db.upsert_history_genre(chat_id=chat_id, month_year=month_year, genre=genre_title)
        return True, f"Сохранил жанр в историю за {month_year}: {genre_title}"

