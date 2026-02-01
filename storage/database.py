import sqlite3
from typing import List, Optional, Tuple


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    text TEXT NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS genres (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source_message_id INTEGER NOT NULL,
                    position INTEGER DEFAULT 0,
                    used INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS polls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    poll_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    options TEXT NOT NULL,
                    message_id INTEGER,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    chat_id     INTEGER PRIMARY KEY,
                    title       TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    chat_id           INTEGER NOT NULL,
                    user_id           INTEGER NOT NULL,
                    username          TEXT,
                    first_seen_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity_at  DATETIME,

                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    chat_id     INTEGER NOT NULL,
                    month_year  TEXT NOT NULL,
                    book        TEXT,
                    genre       TEXT,

                    PRIMARY KEY (chat_id, month_year)
                )
            """)
            # Миграция: добавляем поля position и used, если их еще нет
            try:
                conn.execute("ALTER TABLE genres ADD COLUMN position INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Поле уже существует
            try:
                conn.execute("ALTER TABLE genres ADD COLUMN used INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Поле уже существует
            # Устанавливаем position для существующих записей, если они еще не установлены
            # Для каждого чата устанавливаем position последовательно на основе created_at
            cursor = conn.execute("""
                SELECT DISTINCT chat_id FROM genres
            """)
            for (chat_id,) in cursor.fetchall():
                cursor2 = conn.execute("""
                    SELECT id FROM genres 
                    WHERE chat_id = ? 
                    ORDER BY created_at ASC, id ASC
                """, (chat_id,))
                for pos, (genre_id,) in enumerate(cursor2.fetchall(), 1):
                    conn.execute("""
                        UPDATE genres 
                        SET position = ? 
                        WHERE id = ? AND (position = 0 OR position IS NULL)
                    """, (pos, genre_id))
            conn.commit()

    def upsert_history_book(self, chat_id: int, month_year: str, book: str) -> None:
        """
        Создаёт/обновляет запись истории за месяц.
        Обновляет только поле book, не затирая genre.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO history (chat_id, month_year, book, genre)
                VALUES (?, ?, ?, '')
                ON CONFLICT(chat_id, month_year) DO UPDATE SET
                    book = excluded.book
                """,
                (chat_id, month_year, book),
            )
            conn.commit()

    def upsert_history_genre(self, chat_id: int, month_year: str, genre: str) -> None:
        """
        Создаёт/обновляет запись истории за месяц.
        Обновляет только поле genre, не затирая book.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO history (chat_id, month_year, book, genre)
                VALUES (?, ?, '', ?)
                ON CONFLICT(chat_id, month_year) DO UPDATE SET
                    genre = excluded.genre
                """,
                (chat_id, month_year, genre),
            )
            conn.commit()

    def get_history_years(self, chat_id: int) -> List[int]:
        """
        Возвращает список лет, за которые есть записи в history для чата.
        year извлекается из month_year формата "12_2026".
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT month_year, book, genre
                FROM history
                WHERE chat_id = ?
                """,
                (chat_id,),
            )
            years: set[int] = set()
            for r in cursor.fetchall():
                month_year = (r["month_year"] or "").strip()
                if not month_year:
                    continue
                # Считаем запись "существующей", только если есть хоть что-то сохранённое
                book = (r["book"] or "").strip()
                genre = (r["genre"] or "").strip()
                if not book and not genre:
                    continue
                try:
                    _m, y = month_year.split("_", 1)
                    years.add(int(y))
                except Exception:
                    continue
            return sorted(years)

    def get_history_for_year(self, chat_id: int, year: int) -> List[Tuple[int, str, str]]:
        """
        Возвращает записи истории за конкретный год.
        Формат результата: [(month, genre, book), ...] отсортировано по month.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT month_year, book, genre
                FROM history
                WHERE chat_id = ?
                """,
                (chat_id,),
            )
            rows: List[Tuple[int, str, str]] = []
            for r in cursor.fetchall():
                month_year = (r["month_year"] or "").strip()
                if not month_year:
                    continue
                try:
                    m_str, y_str = month_year.split("_", 1)
                    m = int(m_str)
                    y = int(y_str)
                except Exception:
                    continue
                if y != year:
                    continue
                book = (r["book"] or "").strip()
                genre = (r["genre"] or "").strip()
                # показываем только те месяцы, где есть хоть что-то
                if not book and not genre:
                    continue
                rows.append((m, genre, book))
            rows.sort(key=lambda t: t[0])
            return rows

    def insert_user_activity_if_missing_by_user_id(
        self,
        chat_id: int,
        users: List[Tuple[int, Optional[str]]],
    ) -> Tuple[int, int]:
        """
        Добавляет пользователей в user_activity только если такого user_id ещё нет в таблице.

        Важно: проверка делается по user_id (глобально), как требуется для /init_users.
        Возвращает (inserted_count, skipped_count).
        """
        if not users:
            return 0, 0

        # Убираем дубликаты из входа (берём первый username, который встретился)
        unique_by_id: dict[int, Optional[str]] = {}
        for user_id, username in users:
            if user_id not in unique_by_id:
                unique_by_id[user_id] = username

        user_ids = list(unique_by_id.keys())
        if not user_ids:
            return 0, 0

        with sqlite3.connect(self.db_path) as conn:
            placeholders = ",".join(["?"] * len(user_ids))
            cursor = conn.execute(
                f"SELECT DISTINCT user_id FROM user_activity WHERE user_id IN ({placeholders})",
                user_ids,
            )
            existing_user_ids = {row[0] for row in cursor.fetchall()}

            to_insert = [
                (chat_id, user_id, unique_by_id[user_id])
                for user_id in user_ids
                if user_id not in existing_user_ids
            ]

            if not to_insert:
                return 0, len(user_ids)

            conn.executemany(
                """
                INSERT INTO user_activity (chat_id, user_id, username, first_seen_at, last_activity_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                to_insert,
            )
            conn.commit()

            inserted = len(to_insert)
            skipped = len(user_ids) - inserted
            return inserted, skipped

    def get_users_for_chat(
        self,
        chat_id: int,
        *,
        inactive_months: Optional[int] = None,
    ) -> List[Tuple[int, Optional[str], Optional[str]]]:
        """
        Возвращает список пользователей для чата: (user_id, username, last_activity_at).

        Если inactive_months задан, возвращает тех, у кого last_activity_at (или first_seen_at)
        старше чем now - inactive_months months.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if inactive_months is None:
                cursor = conn.execute(
                    """
                    SELECT user_id, username, last_activity_at
                    FROM user_activity
                    WHERE chat_id = ?
                    ORDER BY COALESCE(username, '') COLLATE NOCASE ASC, user_id ASC
                    """,
                    (chat_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT user_id, username, last_activity_at
                    FROM user_activity
                    WHERE chat_id = ?
                      AND datetime(COALESCE(last_activity_at, first_seen_at))
                          < datetime('now', ?)
                    ORDER BY COALESCE(username, '') COLLATE NOCASE ASC, user_id ASC
                    """,
                    (chat_id, f"-{inactive_months} months"),
                )
            return [(int(r["user_id"]), r["username"], r["last_activity_at"]) for r in cursor.fetchall()]

    def delete_user_activity(self, chat_id: int, user_id: int) -> bool:
        """Удаляет пользователя из user_activity для конкретного чата."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_activity
                WHERE chat_id = ? AND user_id = ?
                """,
                (chat_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_user_activity(self, chat_id: int) -> int:
        """Удаляет все записи user_activity для чата. Возвращает количество удалённых строк."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_activity
                WHERE chat_id = ?
                """,
                (chat_id,),
            )
            conn.commit()
            return cursor.rowcount

    def upsert_user_activity(self, chat_id: int, user_id: int, username: Optional[str]) -> None:
        """
        Добавляет/обновляет пользователя в user_activity для конкретного чата.
        - first_seen_at: фиксируется при первом появлении
        - last_activity_at: ставится в CURRENT_TIMESTAMP
        - username: обновляется, если передан
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_activity (chat_id, user_id, username, first_seen_at, last_activity_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, user_activity.username),
                    last_activity_at = CURRENT_TIMESTAMP
                """,
                (chat_id, user_id, username),
            )
            conn.commit()

    def upsert_user_activity_many(self, rows: List[Tuple[int, int, Optional[str]]]) -> int:
        """
        Пачечный апдейт last_activity_at для user_activity.

        rows: список (chat_id, user_id, username)
        Возвращает количество обработанных строк (len(rows)).
        """
        if not rows:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO user_activity (chat_id, user_id, username, first_seen_at, last_activity_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, user_activity.username),
                    last_activity_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def add_suggestion(self, chat_id: int, user_id: int, username: Optional[str], 
                      text: str, source_message_id: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO suggestions (chat_id, user_id, username, text, source_message_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (chat_id, user_id, username, text, source_message_id))
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def get_suggestions(self, chat_id: int) -> List[Tuple[int, int, Optional[str], str, int, str]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT id, user_id, username, text, source_message_id, created_at
                FROM suggestions
                WHERE chat_id = ?
                ORDER BY created_at ASC
            """, (chat_id,))
            return [tuple(row) for row in cursor.fetchall()]
    
    def count_suggestions(self, chat_id: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM suggestions
                WHERE chat_id = ?
            """, (chat_id,))
            return cursor.fetchone()[0]

    def clear_suggestions(self, chat_id: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM suggestions
                WHERE chat_id = ?
            """, (chat_id,))
            conn.commit()
            return cursor.rowcount

    def get_suggestion_by_index(self, chat_id: int, index: int) -> Optional[Tuple[int, int, Optional[str], str, int, str]]:
        """Получает предложение по номеру в списке (начиная с 1)"""
        suggestions = self.get_suggestions(chat_id)
        if 1 <= index <= len(suggestions):
            return suggestions[index - 1]
        return None

    def delete_suggestion(self, chat_id: int, suggestion_id: int) -> bool:
        """Удаляет предложение по ID. Возвращает True если удалено, False если не найдено"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM suggestions
                WHERE chat_id = ? AND id = ?
            """, (chat_id, suggestion_id))
            conn.commit()
            return cursor.rowcount > 0

    def add_genre(self, chat_id: int, title: str, source_message_id: int) -> bool:
        """Добавляет жанр. Возвращает True при успехе, False при ошибке"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Вычисляем следующий position для данного чата
                cursor = conn.execute("""
                    SELECT COALESCE(MAX(position), 0) + 1
                    FROM genres
                    WHERE chat_id = ?
                """, (chat_id,))
                next_position = cursor.fetchone()[0]
                
                conn.execute("""
                    INSERT INTO genres (chat_id, title, source_message_id, position, used)
                    VALUES (?, ?, ?, ?, 0)
                """, (chat_id, title, source_message_id, next_position))
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def get_genres(self, chat_id: int) -> List[Tuple[int, str, str, int, int, int]]:
        """Получает все жанры для чата. Возвращает список кортежей (id, title, created_at, source_message_id, position, used)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT id, title, created_at, source_message_id, position, used
                FROM genres
                WHERE chat_id = ?
                ORDER BY position ASC
            """, (chat_id,))
            return [tuple(row) for row in cursor.fetchall()]

    def get_genre_by_index(self, chat_id: int, index: int) -> Optional[Tuple[int, str, str, int, int, int]]:
        """Получает жанр по номеру в списке (начиная с 1)"""
        genres = self.get_genres(chat_id)
        if 1 <= index <= len(genres):
            return genres[index - 1]
        return None

    def delete_genre(self, chat_id: int, genre_id: int) -> bool:
        """Удаляет жанр по ID. Возвращает True если удалено, False если не найдено"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM genres
                WHERE chat_id = ? AND id = ?
            """, (chat_id, genre_id))
            conn.commit()
            return cursor.rowcount > 0

    def add_poll(self, chat_id: int, poll_id: str, question: str, options: List[str], 
                 message_id: Optional[int] = None) -> bool:
        """Добавляет опрос в базу данных. Возвращает True при успехе, False при ошибке"""
        import json
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO polls (chat_id, poll_id, question, options, message_id, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                """, (chat_id, poll_id, question, json.dumps(options, ensure_ascii=False), message_id))
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def get_polls(self, chat_id: int, status: Optional[str] = None) -> List[Tuple[int, int, str, str, str, Optional[int], str, str, Optional[str]]]:
        """
        Получает опросы для чата.
        Возвращает список кортежей (id, chat_id, poll_id, question, options, message_id, status, created_at, closed_at).
        Если status указан, фильтрует по статусу.
        """
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                cursor = conn.execute("""
                    SELECT id, chat_id, poll_id, question, options, message_id, status, created_at, closed_at
                    FROM polls
                    WHERE chat_id = ? AND status = ?
                    ORDER BY created_at DESC
                """, (chat_id, status))
            else:
                cursor = conn.execute("""
                    SELECT id, chat_id, poll_id, question, options, message_id, status, created_at, closed_at
                    FROM polls
                    WHERE chat_id = ?
                    ORDER BY created_at DESC
                """, (chat_id,))
            return [tuple(row) for row in cursor.fetchall()]

    def get_poll_by_poll_id(self, chat_id: int, poll_id: str) -> Optional[Tuple[int, int, str, str, str, Optional[int], str, str, Optional[str]]]:
        """Получает опрос по poll_id. Возвращает кортеж или None"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT id, chat_id, poll_id, question, options, message_id, status, created_at, closed_at
                FROM polls
                WHERE chat_id = ? AND poll_id = ?
            """, (chat_id, poll_id))
            row = cursor.fetchone()
            return tuple(row) if row else None

    def close_poll(self, chat_id: int, poll_id: str) -> bool:
        """Закрывает опрос. Возвращает True если обновлено, False если не найдено"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE polls
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP
                WHERE chat_id = ? AND poll_id = ? AND status = 'active'
            """, (chat_id, poll_id))
            conn.commit()
            return cursor.rowcount > 0

    def toggle_genre_active(self, chat_id: int, genre_id: int) -> Tuple[bool, Optional[bool]]:
        """
        Переключает флаг активности жанра через used (active = !used).
        Возвращает (успех, новое_значение_активности) или (False, None) если жанр не найден.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Получаем текущее значение used
            cursor = conn.execute("""
                SELECT used FROM genres
                WHERE chat_id = ? AND id = ?
            """, (chat_id, genre_id))
            row = cursor.fetchone()
            if not row:
                return False, None
            
            current_used = row[0]
            new_used = 1 if current_used == 0 else 0
            new_active = new_used == 0  # active = !used
            
            # Обновляем значение used
            cursor = conn.execute("""
                UPDATE genres
                SET used = ?
                WHERE chat_id = ? AND id = ?
            """, (new_used, chat_id, genre_id))
            conn.commit()
            
            return cursor.rowcount > 0, new_active

    def reset_all_genres_active(self, chat_id: int) -> int:
        """
        Устанавливает used=0 (active=1) для всех жанров в чате.
        Возвращает количество обновленных записей.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE genres
                SET used = 0
                WHERE chat_id = ?
            """, (chat_id,))
            conn.commit()
            return cursor.rowcount

    def add_or_update_group(self, chat_id: int, title: str, chat_type: str, is_active: int = 1) -> bool:
        """
        Добавляет или обновляет информацию о группе.
        Возвращает True при успехе, False при ошибке.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Проверяем, существует ли уже запись
                cursor = conn.execute("""
                    SELECT chat_id FROM groups WHERE chat_id = ?
                """, (chat_id,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Обновляем существующую запись
                    conn.execute("""
                        UPDATE groups
                        SET title = ?, type = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE chat_id = ?
                    """, (title, chat_type, is_active, chat_id))
                else:
                    # Создаем новую запись
                    conn.execute("""
                        INSERT INTO groups (chat_id, title, type, is_active, added_at, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (chat_id, title, chat_type, is_active))
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def remove_group(self, chat_id: int) -> bool:
        """
        Удаляет группу из базы данных (устанавливает is_active=0).
        Возвращает True если обновлено, False если не найдено.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE groups
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (chat_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_group(self, chat_id: int) -> Optional[Tuple[int, str, str, int, str, str]]:
        """
        Получает информацию о группе.
        Возвращает кортеж (chat_id, title, type, is_active, added_at, updated_at) или None.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT chat_id, title, type, is_active, added_at, updated_at
                FROM groups
                WHERE chat_id = ?
            """, (chat_id,))
            row = cursor.fetchone()
            return tuple(row) if row else None

    def get_all_groups(self, active_only: bool = False) -> List[Tuple[int, str, str, int, str, str]]:
        """
        Получает список всех групп.
        Если active_only=True, возвращает только активные группы (is_active=1).
        Возвращает список кортежей (chat_id, title, type, is_active, added_at, updated_at).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if active_only:
                cursor = conn.execute("""
                    SELECT chat_id, title, type, is_active, added_at, updated_at
                    FROM groups
                    WHERE is_active = 1
                    ORDER BY added_at DESC
                """)
            else:
                cursor = conn.execute("""
                    SELECT chat_id, title, type, is_active, added_at, updated_at
                    FROM groups
                    ORDER BY added_at DESC
                """)
            return [tuple(row) for row in cursor.fetchall()]
