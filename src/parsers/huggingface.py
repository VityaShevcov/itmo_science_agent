"""Парсер HuggingFace Daily Papers через API."""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

from .base import BasePaperParser, Paper


logger = logging.getLogger(__name__)

HF_API_URL = "https://huggingface.co/api/daily_papers"


class HuggingFacePapersParser(BasePaperParser):
    """Парсер трендовых ML-статей с HuggingFace Daily Papers."""

    @property
    def source_name(self) -> str:
        return "huggingface_papers"

    async def search(
        self,
        keywords: list[str],
        categories: list[str] | None = None,
        max_results: int = 50,
        days_back: int = 7,
    ) -> list[Paper]:
        """Загрузка статей из HuggingFace Daily Papers API."""

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._fetch_papers,
            max_results,
            days_back,
        )

        logger.info(f"Found {len(results)} papers from HuggingFace Daily Papers")
        return results

    def _fetch_papers(self, max_results: int, days_back: int) -> list[Paper]:
        """Синхронная загрузка через HuggingFace API."""
        try:
            req = Request(
                f"{HF_API_URL}?limit={max_results}",
                headers={"User-Agent": "ScienceAgent/1.0"},
            )
            data = urlopen(req, timeout=15).read()
            entries = json.loads(data)
        except (URLError, json.JSONDecodeError) as e:
            logger.error(f"HuggingFace API error: {e}")
            return []

        papers = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        for entry in entries:
            try:
                paper = self._parse_entry(entry, cutoff_date)
                if paper:
                    papers.append(paper)
            except Exception as e:
                logger.warning(f"Error parsing HF entry: {e}")
                continue

        return papers

    def _parse_entry(self, entry: dict, cutoff_date: datetime) -> Paper | None:
        """Парсинг одной записи API."""
        paper_data = entry.get("paper", {})

        # Дата публикации на HF Daily
        published_str = entry.get("publishedAt", "")
        if published_str:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            published = datetime.now()

        if published < cutoff_date:
            return None

        title = entry.get("title", "").replace("\n", " ").strip()
        if not title:
            return None

        abstract = entry.get("summary", "") or paper_data.get("summary", "")
        paper_id = paper_data.get("id", "")
        upvotes = paper_data.get("upvotes", 0)

        # Авторы
        authors = []
        for a in paper_data.get("authors", [])[:5]:
            name = a.get("name", "")
            if name:
                authors.append(name)

        url = f"https://huggingface.co/papers/{paper_id}" if paper_id else ""

        return Paper(
            id=f"hf_{paper_id}" if paper_id else f"hf_{title[:20]}",
            title=title,
            abstract=abstract,
            authors=authors,
            published=published,
            url=url,
            source=self.source_name,
            categories=["ML", "AI"],
            upvotes=upvotes,
        )


async def test_huggingface():
    """Тест парсера."""
    parser = HuggingFacePapersParser()
    papers = await parser.search(
        keywords=["transformer"],
        max_results=10,
        days_back=14,
    )
    for p in papers:
        print(f"- [upvotes={p.upvotes:3d}] {p.title[:60]}... ({p.published.date()})")
    print(f"\nTotal: {len(papers)} papers")


if __name__ == "__main__":
    asyncio.run(test_huggingface())
