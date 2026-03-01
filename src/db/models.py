"""SQLite database setup and management."""

import aiosqlite
from pathlib import Path

SCHEMA = """
-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Профили интересов
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    interests TEXT DEFAULT '[]',
    keywords TEXT DEFAULT '[]',
    research_plan TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Источники пользователя
CREATE TABLE IF NOT EXISTS user_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    UNIQUE(user_id, source_name)
);

-- История отправленных статей
CREATE TABLE IF NOT EXISTS sent_papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    source TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    feedback INTEGER,
    UNIQUE(user_id, paper_id)
);

-- Настройки рассылки
CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    send_hour INTEGER DEFAULT 9,
    timezone TEXT DEFAULT 'Europe/Moscow',
    days_depth INTEGER DEFAULT 7,
    max_papers INTEGER DEFAULT 3,
    is_active INTEGER DEFAULT 1,
    digest_frequency INTEGER DEFAULT 1,
    last_digest_at TIMESTAMP
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_sent_papers_user_id ON sent_papers(user_id);
CREATE INDEX IF NOT EXISTS idx_sent_papers_paper_id ON sent_papers(paper_id);
"""


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Подключение к БД и создание таблиц."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA)
        await self._run_migrations()
        await self._connection.commit()

    async def _run_migrations(self) -> None:
        """Миграции для существующих БД."""
        migrations = [
            ("user_settings", "digest_frequency", "ALTER TABLE user_settings ADD COLUMN digest_frequency INTEGER DEFAULT 1"),
            ("user_settings", "last_digest_at", "ALTER TABLE user_settings ADD COLUMN last_digest_at TIMESTAMP"),
            ("sent_papers", "url", "ALTER TABLE sent_papers ADD COLUMN url TEXT"),
            ("sent_papers", "source", "ALTER TABLE sent_papers ADD COLUMN source TEXT"),
        ]
        for table, column, sql in migrations:
            try:
                await self._connection.execute(f"SELECT {column} FROM {table} LIMIT 1")
            except Exception:
                await self._connection.execute(sql)

    async def disconnect(self) -> None:
        """Закрытие соединения."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def execute(self, query: str, params: tuple = ()):
        """Execute a write query and return lastrowid and fetched rows."""
        cursor = await self.connection.execute(query, params)
        rows = await cursor.fetchall()
        lastrowid = cursor.lastrowid
        await cursor.close()
        await self.connection.commit()
        return _ExecuteResult(lastrowid=lastrowid, rows=rows)

    async def fetchone(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        async with self.connection.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with self.connection.execute(query, params) as cursor:
            return await cursor.fetchall()


class _ExecuteResult:
    """Result of an execute() call with pre-fetched rows."""
    def __init__(self, lastrowid, rows):
        self.lastrowid = lastrowid
        self.rows = rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows
