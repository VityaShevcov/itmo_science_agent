"""Тест LLM клиента (проверка подключения к vsellm.ru)."""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.llm import LLMClient


async def main():
    print("=" * 60)
    print("Тест LLM клиента (vsellm.ru)")
    print("=" * 60)

    # Проверка конфига
    if not config.llm.api_key:
        print("❌ LLM_API_KEY не задан в .env")
        return

    print(f"\nBase URL: {config.llm.base_url}")
    print(f"Scoring model: {config.llm.scoring_model}")
    print(f"Generation model: {config.llm.generation_model}")

    client = LLMClient()

    # Тест scoring
    print("\n--- Тест scoring ---")
    try:
        result = await client.score_relevance(
            paper_id="test123",
            paper_title="Attention Is All You Need",
            paper_abstract="We propose a new simple network architecture, the Transformer, based solely on attention mechanisms.",
            user_interests=["machine learning", "NLP"],
            user_keywords=["transformer", "attention"],
        )
        print(f"✅ Score: {result.score:.2f}")
        print(f"   Reason: {result.reason}")
    except Exception as e:
        print(f"❌ Ошибка scoring: {e}")

    # Тест generation
    print("\n--- Тест generation ---")
    try:
        review = await client.generate_review(
            paper_id="test123",
            paper_title="Attention Is All You Need",
            paper_abstract="We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
            user_interests=["deep learning"],
            user_keywords=["transformer"],
        )
        print(f"✅ Summary: {review.summary[:100]}...")
        print(f"   Why important: {review.why_important[:100]}...")
        print(f"   How helps: {review.how_helps[:100]}...")
    except Exception as e:
        print(f"❌ Ошибка generation: {e}")


if __name__ == "__main__":
    asyncio.run(main())
