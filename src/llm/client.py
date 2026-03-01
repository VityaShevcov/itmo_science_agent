"""LLM client for vsellm.ru (OpenAI-compatible API)."""

from dataclasses import dataclass
from openai import AsyncOpenAI

from ..config import config


@dataclass
class ScoringResult:
    """Результат оценки релевантности статьи."""
    paper_id: str
    score: float  # 0.0 - 1.0
    reason: str


@dataclass
class PaperReview:
    """Сгенерированный обзор статьи."""
    paper_id: str
    summary: str
    why_important: str
    how_helps: str
    limitations: str = ""


class LLMClient:
    """Клиент для работы с LLM через vsellm.ru."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
        )
        self.scoring_model = config.llm.scoring_model
        self.generation_model = config.llm.generation_model

    async def score_relevance(
        self,
        paper_id: str,
        paper_title: str,
        paper_abstract: str,
        user_interests: list[str],
        user_keywords: list[str],
        feedback_history: list[tuple[str, int]] | None = None,
    ) -> ScoringResult:
        """
        Оценить релевантность статьи профилю пользователя.
        Использует дешёвую модель для экономии.
        """
        feedback_section = ""
        if feedback_history:
            lines = []
            for title, fb in feedback_history:
                emoji = "\U0001f44d" if fb == 1 else "\U0001f44e"
                lines.append(f"- {emoji} {title}")
            feedback_section = (
                "\n\nПредыдущие оценки пользователя (учитывай при scoring):\n"
                + "\n".join(lines)
                + "\nОценивай выше статьи, похожие на \U0001f44d, и ниже похожие на \U0001f44e."
            )

        prompt = f"""Оцени релевантность научной статьи для исследователя.

Профиль исследователя:
- Области интересов: {', '.join(user_interests) if user_interests else 'не указаны'}
- Ключевые слова: {', '.join(user_keywords) if user_keywords else 'не указаны'}{feedback_section}

Статья:
- Название: {paper_title}
- Аннотация: {paper_abstract[:1500]}

Ответь в формате:
SCORE: [число от 0 до 100]
REASON: [краткое объяснение на русском, 1 предложение]"""

        response = await self.client.chat.completions.create(
            model=self.scoring_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )

        text = response.choices[0].message.content or ""

        # Парсим ответ
        score = 0.0
        reason = "Не удалось оценить"

        for line in text.strip().split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip()) / 100
                    score = max(0.0, min(1.0, score))
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return ScoringResult(paper_id=paper_id, score=score, reason=reason)

    async def generate_review(
        self,
        paper_id: str,
        paper_title: str,
        paper_abstract: str,
        user_interests: list[str],
        user_keywords: list[str],
        research_plan: str | None = None,
    ) -> PaperReview:
        """
        Сгенерировать персонализированный обзор статьи.
        Использует более мощную модель для качества.
        """
        research_context = ""
        if research_plan:
            research_context = f"\nПлан исследований пользователя: {research_plan}"

        prompt = f"""Ты — научный обозреватель. Напиши краткий обзор статьи на русском языке.

Профиль читателя:
- Интересы: {', '.join(user_interests) if user_interests else 'не указаны'}
- Ключевые слова: {', '.join(user_keywords) if user_keywords else 'не указаны'}{research_context}

Статья:
- Название: {paper_title}
- Аннотация: {paper_abstract}

Напиши обзор в четырёх разделах. Правила:
• Пиши грамотным, но понятным языком — без канцеляризмов, но и без разговорного сленга
• Используй безличные или авторские конструкции: "авторы предложили", "в работе представлена", "предлагается метод"
• Указывай конкретику: методы, цифры, результаты экспериментов, датасеты
• Обязательно упомяни главные выводы и что было показано/доказано
• Честно укажи ограничения работы
• НЕ используй markdown (**, ## и т.д.), пиши plain text
• Каждый раздел — 2-4 предложения

SUMMARY:
[Суть работы: что именно предложили авторы, какой метод/архитектуру разработали, какой главный результат получен. Ключевые цифры если есть.]

WHY_IMPORTANT:
[Какую проблему решает работа, чем принципиально отличается от предыдущих подходов, какой вклад в область.]

LIMITATIONS:
[Ограничения и слабые стороны: на каких данных не проверялось, какие допущения сделаны, что может не работать на практике.]

HOW_HELPS:
[Как конкретно результаты могут быть полезны читателю с учётом его интересов и исследований.]"""

        response = await self.client.chat.completions.create(
            model=self.generation_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )

        text = response.choices[0].message.content or ""

        # Парсим ответ по секциям
        sections = {"summary": "", "why_important": "", "limitations": "", "how_helps": ""}
        section_keys = {
            "SUMMARY:": "summary",
            "WHY_IMPORTANT:": "why_important",
            "LIMITATIONS:": "limitations",
            "HOW_HELPS:": "how_helps",
        }

        current_section = None
        lines_buffer = []

        for line in text.strip().split("\n"):
            line_stripped = line.strip().lstrip("#").strip().strip("*").strip()

            matched_key = None
            for key, sec_name in section_keys.items():
                if key in line_stripped:
                    matched_key = key
                    # Сохраняем предыдущую секцию
                    if current_section and lines_buffer:
                        sections[current_section] = " ".join(lines_buffer).strip()
                    current_section = sec_name
                    lines_buffer = [line_stripped.split(key, 1)[1].strip()]
                    break

            if not matched_key and current_section and line_stripped:
                lines_buffer.append(line_stripped)

        # Последняя секция
        if current_section and lines_buffer:
            sections[current_section] = " ".join(lines_buffer).strip()

        return PaperReview(
            paper_id=paper_id,
            summary=sections["summary"] or "Не удалось сгенерировать обзор.",
            why_important=sections["why_important"] or "Не удалось определить.",
            limitations=sections["limitations"] or "",
            how_helps=sections["how_helps"] or "Не удалось определить.",
        )

    async def batch_score(
        self,
        papers: list[dict],
        user_interests: list[str],
        user_keywords: list[str],
        feedback_history: list[tuple[str, int]] | None = None,
    ) -> list[ScoringResult]:
        """Оценить несколько статей."""
        results = []
        for paper in papers:
            result = await self.score_relevance(
                paper_id=paper["id"],
                paper_title=paper["title"],
                paper_abstract=paper["abstract"],
                user_interests=user_interests,
                user_keywords=user_keywords,
                feedback_history=feedback_history,
            )
            results.append(result)
        return results

    def _assign_section(self, section: str, lines: list[str], loc: dict) -> None:
        """Helper для присвоения секций."""
        pass  # Handled inline above
