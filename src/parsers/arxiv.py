"""Парсер arXiv."""

import asyncio
import logging
from datetime import datetime, timedelta

import arxiv

from .base import BasePaperParser, Paper


logger = logging.getLogger(__name__)

# Категории DS/ML на arXiv
DEFAULT_CATEGORIES = [
    "cs.LG",   # Machine Learning
    "cs.AI",   # Artificial Intelligence
    "cs.CL",   # Computation and Language (NLP)
    "cs.CV",   # Computer Vision
    "stat.ML", # Statistics - Machine Learning
]


class ArxivParser(BasePaperParser):
    """Парсер arXiv через официальный API."""

    @property
    def source_name(self) -> str:
        return "arxiv"

    async def search(
        self,
        keywords: list[str],
        categories: list[str] | None = None,
        max_results: int = 50,
        days_back: int = 7,
    ) -> list[Paper]:
        """Поиск статей на arXiv."""

        if not keywords:
            logger.warning("No keywords provided for arXiv search")
            return []

        categories = categories or DEFAULT_CATEGORIES

        # Формируем запрос
        query = self._build_query(keywords, categories)
        logger.info(f"arXiv query: {query}")

        # arXiv API синхронный, запускаем в executor
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._fetch_papers,
            query,
            max_results,
            days_back,
        )

        logger.info(f"Found {len(results)} papers on arXiv")
        return results

    def _build_query(self, keywords: list[str], categories: list[str]) -> str:
        """Построение поискового запроса."""
        # Ключевые слова в title или abstract
        keyword_query = " OR ".join([
            f'(ti:"{kw}" OR abs:"{kw}")'
            for kw in keywords
        ])

        # Категории
        category_query = " OR ".join([
            f"cat:{cat}"
            for cat in categories
        ])

        return f"({keyword_query}) AND ({category_query})"

    def _fetch_papers(
        self,
        query: str,
        max_results: int,
        days_back: int,
    ) -> list[Paper]:
        """Синхронная загрузка статей (для executor)."""
        client = arxiv.Client()

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        try:
            for result in client.results(search):
                # Фильтр по дате
                published = result.published.replace(tzinfo=None)
                if published < cutoff_date:
                    continue

                paper = Paper(
                    id=result.entry_id.split("/")[-1],  # arxiv ID
                    title=result.title.replace("\n", " "),
                    abstract=result.summary.replace("\n", " "),
                    authors=[a.name for a in result.authors[:5]],  # первые 5 авторов
                    published=published,
                    url=result.entry_id,
                    source=self.source_name,
                    categories=[c for c in result.categories],
                )
                papers.append(paper)

        except Exception as e:
            logger.error(f"arXiv fetch error: {e}")

        return papers


async def test_arxiv():
    """Тест парсера."""
    parser = ArxivParser()
    papers = await parser.search(
        keywords=["transformer", "attention"],
        max_results=5,
        days_back=30,
    )
    for p in papers:
        print(f"- {p.title[:60]}... ({p.published.date()})")


if __name__ == "__main__":
    asyncio.run(test_arxiv())
