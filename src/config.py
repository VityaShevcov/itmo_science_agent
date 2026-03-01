"""Конфигурация приложения."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# BASE_DIR = корень проекта (itmo_science_agent/)
BASE_DIR = Path(__file__).parent.parent

# Загружаем .env из корня проекта
load_dotenv(BASE_DIR / ".env")


@dataclass
class BotConfig:
    token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))


@dataclass
class LLMConfig:
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))

    # Модели для разных задач (экономия бюджета)
    scoring_model: str = field(default_factory=lambda: os.getenv("LLM_SCORING_MODEL", "gpt-4o-mini"))
    generation_model: str = field(default_factory=lambda: os.getenv("LLM_GENERATION_MODEL", "qwen/qwen3.5-397b-a17b"))


@dataclass
class DatabaseConfig:
    path: Path = field(default_factory=lambda: BASE_DIR / "data" / "science_agent.db")


@dataclass
class SchedulerConfig:
    default_send_hour: int = 9
    default_timezone: str = "Europe/Moscow"
    default_days_depth: int = 7
    default_max_papers: int = 3


@dataclass
class Config:
    bot: BotConfig = field(default_factory=BotConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    def validate(self) -> list[str]:
        """Проверка обязательных параметров."""
        errors = []
        if not self.bot.token:
            errors.append("TELEGRAM_BOT_TOKEN не задан")
        if not self.llm.api_key:
            errors.append("LLM_API_KEY не задан")
        return errors


config = Config()
