"""Тест arXiv парсера (запускать отдельно от бота)."""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from parsers import ArxivParser


async def main():
    print("=" * 60)
    print("Тест arXiv парсера")
    print("=" * 60)

    parser = ArxivParser()

    # Тестовые ключевые слова
    keywords = ["transformer", "large language model"]

    print(f"\nПоиск по ключевым словам: {keywords}")
    print("Глубина: 14 дней, лимит: 10 статей\n")

    papers = await parser.search(
        keywords=keywords,
        max_results=10,
        days_back=14,
    )

    if not papers:
        print("❌ Статьи не найдены")
        return

    print(f"✅ Найдено {len(papers)} статей:\n")

    for i, paper in enumerate(papers, 1):
        print(f"{i}. {paper.title[:70]}...")
        print(f"   Авторы: {', '.join(paper.authors[:3])}")
        print(f"   Дата: {paper.published.strftime('%Y-%m-%d')}")
        print(f"   Категории: {', '.join(paper.categories[:3])}")
        print(f"   URL: {paper.url}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
