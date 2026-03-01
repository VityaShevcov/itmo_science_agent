"""Repository pattern for database operations."""

import json
from dataclasses import dataclass
from datetime import datetime
from .models import Database


@dataclass
class User:
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    created_at: datetime


@dataclass
class UserProfile:
    user_id: int
    interests: list[str]
    keywords: list[str]
    research_plan: str | None


@dataclass
class UserSettings:
    user_id: int
    send_hour: int
    timezone: str
    days_depth: int
    max_papers: int
    is_active: bool
    digest_frequency: int = 1
    last_digest_at: datetime | None = None


DEFAULT_SOURCES = ["arxiv"]


class UserRepository:
    """Операции с пользователями."""

    def __init__(self, db: Database):
        self.db = db

    async def create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> int:
        """Создать пользователя и связанные записи."""
        cursor = await self.db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            RETURNING id
            """,
            (telegram_id, username, first_name),
        )
        row = await cursor.fetchone()
        user_id = row[0]

        # Создаём профиль
        await self.db.execute(
            "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)",
            (user_id,),
        )

        # Создаём настройки
        await self.db.execute(
            "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
            (user_id,),
        )

        # Добавляем источники по умолчанию
        for source in DEFAULT_SOURCES:
            await self.db.execute(
                "INSERT OR IGNORE INTO user_sources (user_id, source_name) VALUES (?, ?)",
                (user_id, source),
            )

        return user_id

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        """Получить пользователя по Telegram ID."""
        row = await self.db.fetchone(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if not row:
            return None
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            first_name=row["first_name"],
            created_at=row["created_at"],
        )

    async def get_profile(self, user_id: int) -> UserProfile | None:
        """Получить профиль пользователя."""
        row = await self.db.fetchone(
            "SELECT * FROM user_profiles WHERE user_id = ?",
            (user_id,),
        )
        if not row:
            return None
        return UserProfile(
            user_id=row["user_id"],
            interests=json.loads(row["interests"]),
            keywords=json.loads(row["keywords"]),
            research_plan=row["research_plan"],
        )

    async def update_profile(
        self,
        user_id: int,
        interests: list[str] | None = None,
        keywords: list[str] | None = None,
        research_plan: str | None = None,
    ) -> None:
        """Обновить профиль."""
        updates = []
        params = []

        if interests is not None:
            updates.append("interests = ?")
            params.append(json.dumps(interests, ensure_ascii=False))
        if keywords is not None:
            updates.append("keywords = ?")
            params.append(json.dumps(keywords, ensure_ascii=False))
        if research_plan is not None:
            updates.append("research_plan = ?")
            params.append(research_plan)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            await self.db.execute(
                f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?",
                tuple(params),
            )

    async def get_settings(self, user_id: int) -> UserSettings | None:
        """Получить настройки пользователя."""
        row = await self.db.fetchone(
            "SELECT * FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        if not row:
            return None
        keys = row.keys()
        return UserSettings(
            user_id=row["user_id"],
            send_hour=row["send_hour"],
            timezone=row["timezone"],
            days_depth=row["days_depth"],
            max_papers=row["max_papers"],
            is_active=bool(row["is_active"]),
            digest_frequency=row["digest_frequency"] if "digest_frequency" in keys else 1,
            last_digest_at=row["last_digest_at"] if "last_digest_at" in keys else None,
        )

    async def update_settings(self, user_id: int, **kwargs) -> None:
        """Обновить настройки."""
        allowed = {"send_hour", "timezone", "days_depth", "max_papers", "is_active", "digest_frequency"}
        updates = []
        params = []

        for key, value in kwargs.items():
            if key in allowed:
                updates.append(f"{key} = ?")
                params.append(value)

        if updates:
            params.append(user_id)
            await self.db.execute(
                f"UPDATE user_settings SET {', '.join(updates)} WHERE user_id = ?",
                tuple(params),
            )

    async def get_active_users(self) -> list[User]:
        """Получить всех активных пользователей для рассылки."""
        rows = await self.db.fetchall(
            """
            SELECT u.* FROM users u
            JOIN user_settings s ON u.id = s.user_id
            WHERE s.is_active = 1
            """
        )
        return [
            User(
                id=row["id"],
                telegram_id=row["telegram_id"],
                username=row["username"],
                first_name=row["first_name"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_enabled_sources(self, user_id: int) -> list[str]:
        """Получить включённые источники пользователя."""
        rows = await self.db.fetchall(
            "SELECT source_name FROM user_sources WHERE user_id = ? AND enabled = 1",
            (user_id,),
        )
        return [row["source_name"] for row in rows]

    async def get_users_for_hour(self, hour: int) -> list[User]:
        """Получить пользователей, которым нужно отправить дайджест в этот час."""
        rows = await self.db.fetchall(
            """
            SELECT u.* FROM users u
            JOIN user_settings s ON u.id = s.user_id
            WHERE s.is_active = 1
              AND s.send_hour = ?
              AND (
                s.last_digest_at IS NULL
                OR julianday('now') - julianday(s.last_digest_at) >= s.digest_frequency
              )
            """,
            (hour,),
        )
        return [
            User(
                id=row["id"],
                telegram_id=row["telegram_id"],
                username=row["username"],
                first_name=row["first_name"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def update_last_digest_at(self, user_id: int) -> None:
        """Обновить время последней рассылки."""
        await self.db.execute(
            "UPDATE user_settings SET last_digest_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )


class PaperRepository:
    """Операции с историей статей."""

    def __init__(self, db: Database):
        self.db = db

    async def is_paper_sent(self, user_id: int, paper_id: str) -> bool:
        """Проверить, была ли статья уже отправлена пользователю."""
        row = await self.db.fetchone(
            "SELECT 1 FROM sent_papers WHERE user_id = ? AND paper_id = ?",
            (user_id, paper_id),
        )
        return row is not None

    async def mark_paper_sent(
        self, user_id: int, paper_id: str, title: str,
        url: str | None = None, source: str | None = None,
    ) -> None:
        """Отметить статью как отправленную."""
        await self.db.execute(
            """
            INSERT OR IGNORE INTO sent_papers (user_id, paper_id, title, url, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, paper_id, title, url, source),
        )

    async def set_feedback(
        self, user_id: int, paper_id: str, feedback: int
    ) -> None:
        """Записать feedback (1=like, -1=dislike)."""
        await self.db.execute(
            "UPDATE sent_papers SET feedback = ? WHERE user_id = ? AND paper_id = ?",
            (feedback, user_id, paper_id),
        )

    async def get_sent_paper_ids(self, user_id: int, limit: int = 100) -> list[str]:
        """Получить ID недавно отправленных статей."""
        rows = await self.db.fetchall(
            """
            SELECT paper_id FROM sent_papers
            WHERE user_id = ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [row["paper_id"] for row in rows]

    async def get_feedback_history(
        self, user_id: int, limit: int = 15,
    ) -> list[tuple[str, int]]:
        """Получить историю фидбека: [(title, feedback)].
        feedback: 1=like, -1=dislike.
        """
        rows = await self.db.fetchall(
            """
            SELECT title, feedback FROM sent_papers
            WHERE user_id = ? AND feedback IS NOT NULL
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [(row["title"], row["feedback"]) for row in rows]

    async def get_sent_papers(
        self, user_id: int, offset: int = 0, limit: int = 5,
    ) -> list[dict]:
        """Получить отправленные статьи с пагинацией."""
        rows = await self.db.fetchall(
            """
            SELECT paper_id, title, url, source, sent_at, feedback
            FROM sent_papers
            WHERE user_id = ?
            ORDER BY sent_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        )
        return [
            {
                "paper_id": row["paper_id"],
                "title": row["title"] or "Без названия",
                "url": row["url"],
                "source": row["source"],
                "sent_at": row["sent_at"],
                "feedback": row["feedback"],
            }
            for row in rows
        ]

    async def count_sent_papers(self, user_id: int) -> int:
        """Посчитать общее количество отправленных статей."""
        row = await self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM sent_papers WHERE user_id = ?",
            (user_id,),
        )
        return row["cnt"] if row else 0
