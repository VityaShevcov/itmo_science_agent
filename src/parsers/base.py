"""Базовый класс для парсеров источников."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Paper:
    """Научная статья."""
    id: str
    title: str
    abstract: str
    authors: list[str]
    published: datetime
    url: str
    source: str
    categories: list[str] = None
    upvotes: int = 0
    citation_count: int = 0
    influential_citations: int = 0
    max_author_h_index: int = 0
    institutions: list[str] = None

    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if self.institutions is None:
            self.institutions = []

    @property
    def days_old(self) -> float:
        """Возраст статьи в днях (минимум 1)."""
        delta = datetime.now() - self.published
        return max(1.0, delta.total_seconds() / 86400)

    @property
    def authority_score(self) -> float:
        """Объективная метрика авторитетности статьи (0-1).

        Цитирования и upvotes нормируются по возрасту:
        5 цитирований за 2 дня (2.5/день) >> 5 цитирований за 30 дней (0.17/день).
        h-index — свойство автора, от возраста не зависит.
        """
        age = self.days_old
        score = 0.0

        # h-index автора: 20% веса. h=50+ = максимум
        score += min(0.20, self.max_author_h_index / 50 * 0.20)

        # Скорость набора upvotes: 40% веса. 3+/день = максимум
        upvote_velocity = self.upvotes / age
        score += min(0.40, upvote_velocity / 3 * 0.40)

        # Скорость цитирования: 30% веса. 1+/день = максимум
        citation_velocity = self.citation_count / age
        score += min(0.30, citation_velocity / 1 * 0.30)

        # Influential citations (скорость): 10% веса. 0.5/день = максимум
        influential_velocity = self.influential_citations / age
        score += min(0.10, influential_velocity / 0.5 * 0.10)

        return min(1.0, score)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "published": self.published.isoformat(),
            "url": self.url,
            "source": self.source,
            "categories": self.categories,
        }


class BasePaperParser(ABC):
    """Абстрактный парсер источника статей."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Имя источника."""
        pass

    @abstractmethod
    async def search(
        self,
        keywords: list[str],
        categories: list[str] | None = None,
        max_results: int = 50,
        days_back: int = 7,
    ) -> list[Paper]:
        """
        Поиск статей.

        Args:
            keywords: Ключевые слова для поиска
            categories: Категории/разделы (специфичны для источника)
            max_results: Максимум результатов
            days_back: Глубина поиска в днях

        Returns:
            Список найденных статей
        """
        pass
