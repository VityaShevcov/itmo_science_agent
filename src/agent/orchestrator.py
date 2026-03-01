"""Оркестратор поиска и ранжирования статей."""

import logging
from dataclasses import dataclass

from ..parsers import ArxivParser, HuggingFacePapersParser, Paper, enrich_papers
from ..llm import LLMClient, ScoringResult, PaperReview
from ..db import UserRepository, PaperRepository, UserProfile, UserSettings


logger = logging.getLogger(__name__)



@dataclass
class RecommendedPaper:
    """Рекомендованная статья с обзором."""
    paper: Paper
    score: float
    review: PaperReview


class PaperAgent:
    """
    Агент для поиска и рекомендации научных статей.

    Workflow:
    1. Получить профиль пользователя
    2. Загрузить статьи из источников
    3. Отфильтровать уже отправленные
    4. Оценить релевантность (LLM scoring)
    5. Выбрать топ-N
    6. Сгенерировать обзоры (LLM generation)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        user_repo: UserRepository,
        paper_repo: PaperRepository,
    ):
        self.llm = llm_client
        self.user_repo = user_repo
        self.paper_repo = paper_repo

        # Парсеры источников
        self.parsers = {
            "arxiv": ArxivParser(),
            "huggingface_papers": HuggingFacePapersParser(),
        }

    async def get_recommendations(
        self,
        user_id: int,
        max_papers: int = 3,
        on_status=None,
    ) -> list[RecommendedPaper]:
        """
        Получить рекомендации для пользователя.

        Args:
            user_id: ID пользователя в БД
            max_papers: Максимум статей для рекомендации
            on_status: async callback(text) для отправки статусов пользователю

        Returns:
            Список рекомендованных статей с обзорами
        """
        async def status(text):
            if on_status:
                await on_status(text)

        # 1. Загружаем профиль и настройки
        profile = await self.user_repo.get_profile(user_id)
        settings = await self.user_repo.get_settings(user_id)
        sources = await self.user_repo.get_enabled_sources(user_id)

        if not profile or not profile.keywords:
            logger.warning(f"User {user_id} has no keywords")
            return []

        days_depth = settings.days_depth if settings else 7

        # 2. Собираем статьи из источников
        await status("🔍 Собираю статьи из источников...")
        all_papers = await self._fetch_papers(
            sources=sources,
            keywords=profile.keywords,
            days_back=days_depth,
        )

        if not all_papers:
            logger.info(f"No papers found for user {user_id}")
            return []

        logger.info(f"Fetched {len(all_papers)} papers for user {user_id}")

        # 2.5. Обогащаем данными из Semantic Scholar и OpenAlex
        await status("📡 Проверяю цитируемость и авторов...")
        await enrich_papers(all_papers)

        # 3. Фильтруем уже отправленные
        sent_ids = await self.paper_repo.get_sent_paper_ids(user_id)
        papers = [p for p in all_papers if p.id not in sent_ids]

        if not papers:
            logger.info(f"All papers already sent to user {user_id}")
            return []

        logger.info(f"{len(papers)} new papers after dedup")

        # 4. Keyword pre-filtering с расширением через LLM
        expanded = await self._expand_keywords(profile.keywords)
        papers = self._keyword_filter(papers, expanded)
        logger.info(f"{len(papers)} papers after keyword filter")

        if not papers:
            return []

        # 4.5. Загружаем историю фидбека
        feedback_history = await self.paper_repo.get_feedback_history(user_id)

        # 5. LLM scoring (дешёвая модель)
        await status(f"📊 Оцениваю {len(papers)} статей на релевантность...")
        scored = await self._score_papers(papers, profile, feedback_history)

        # 5.5. Композитный скоринг: LLM relevance × 0.7 + authority × 0.3
        paper_by_id = {p.id: p for p in papers}
        for s in scored:
            p = paper_by_id.get(s.paper_id)
            if p:
                llm_score = s.score
                authority = p.authority_score
                s.score = llm_score * 0.7 + authority * 0.3

        # 6. Выбираем топ-N
        scored.sort(key=lambda x: x.score, reverse=True)
        for i, s in enumerate(scored):
            p = paper_by_id.get(s.paper_id)
            title_short = p.title[:50] if p else s.paper_id
            if p:
                meta = f"auth={p.authority_score:.2f} cit={p.citation_count} h={p.max_author_h_index} up={p.upvotes}"
            else:
                meta = ""
            logger.info(f"  #{i+1} score={s.score:.2f} {meta} | {title_short}")
        top_papers = scored[:max_papers]

        # 7. Генерируем обзоры (мощная модель, только для топ-N)
        await status("✍️ Готовлю персональные обзоры...")
        recommendations = []
        for scored_paper in top_papers:
            if scored_paper.score < 0.3:  # порог релевантности
                continue

            paper = next(p for p in papers if p.id == scored_paper.paper_id)
            review = await self.llm.generate_review(
                paper_id=paper.id,
                paper_title=paper.title,
                paper_abstract=paper.abstract,
                user_interests=profile.keywords,
                user_keywords=profile.keywords,
                research_plan=profile.research_plan,
            )

            recommendations.append(RecommendedPaper(
                paper=paper,
                score=scored_paper.score,
                review=review,
            ))

        logger.info(f"Generated {len(recommendations)} recommendations for user {user_id}")
        return recommendations

    async def _fetch_papers(
        self,
        sources: list[str],
        keywords: list[str],
        days_back: int,
    ) -> list[Paper]:
        """Загрузка статей из источников."""
        all_papers = []

        for source in sources:
            parser = self.parsers.get(source)
            if not parser:
                logger.warning(f"Unknown source: {source}")
                continue

            try:
                papers = await parser.search(
                    keywords=keywords,
                    max_results=50,
                    days_back=days_back,
                )
                all_papers.extend(papers)
            except Exception as e:
                logger.error(f"Error fetching from {source}: {e}")

        # Дедупликация + пересечение источников
        # Нормализуем ID: hf_2501.12345 и 2501.12345 — одна статья
        def _normalize_id(paper_id: str) -> str:
            return paper_id.removeprefix("hf_")

        # Считаем в скольких источниках встретилась статья
        norm_to_sources: dict[str, set[str]] = {}
        for p in all_papers:
            nid = _normalize_id(p.id)
            norm_to_sources.setdefault(nid, set()).add(p.source)

        seen = set()
        unique = []
        for p in all_papers:
            nid = _normalize_id(p.id)
            if nid in seen:
                continue
            seen.add(nid)

            # Бонус за пересечение источников
            if len(norm_to_sources.get(nid, set())) > 1:
                p.upvotes += 50  # условный бонус
                logger.info(f"Cross-source bonus: {p.title[:60]}")

            unique.append(p)

        return unique

    def _keyword_filter(
        self,
        papers: list[Paper],
        keywords: list[str],
    ) -> list[Paper]:
        """Быстрая фильтрация по ключевым словам."""
        keywords_lower = [k.lower() for k in keywords]

        filtered = []
        for paper in papers:
            text = (paper.title + " " + paper.abstract).lower()
            if any(kw in text for kw in keywords_lower):
                filtered.append(paper)

        return filtered

    async def _expand_keywords(self, keywords: list[str]) -> list[str]:
        """Расширить ключевые слова через LLM (синонимы, аббревиатуры)."""
        try:
            prompt = (
                "Ты помогаешь расширить ключевые слова для поиска научных статей на arXiv и HuggingFace.\n\n"
                "Контекст: это названия моделей, технологий, методов или научных концепций в ML/AI.\n\n"
                "Правила:\n"
                "- Добавь ТОЛЬКО научно-технические варианты написания: аббревиатуры, альтернативные названия\n"
                "- НЕ меняй версии и числа в названиях. Если пользователь написал 'opus 4.6' — НЕ добавляй 'opus 3', 'opus 3.5' и т.д.\n"
                "- Например: 'GPT-4' -> 'GPT-4, GPT-4o, OpenAI GPT-4'. 'BERT' -> 'BERT, RoBERTa, DeBERTa'\n"
                "- НЕ добавляй словарные синонимы или переводы (opus НЕ значит 'work' или 'composition', это название модели)\n"
                "- НЕ добавляй общие слова вроде 'text', 'model', 'network', 'system'\n"
                "- Если слово уже конкретное и нет близких вариантов — оставь только его\n"
                "- Сохрани все оригинальные слова\n"
                "- Ответ: только список через запятую, без пояснений\n\n"
                f"Слова: {', '.join(keywords)}"
            )

            response = await self.llm.client.chat.completions.create(
                model=self.llm.generation_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )

            text = response.choices[0].message.content or ""
            expanded = [k.strip() for k in text.split(",") if k.strip()]

            # Гарантируем что оригинальные слова на месте
            result = list(set(keywords + expanded))
            logger.info(f"Keywords expanded: {keywords} -> {result}")
            return result

        except Exception as e:
            logger.warning(f"Keyword expansion failed: {e}, using original")
            return keywords

    async def _score_papers(
        self,
        papers: list[Paper],
        profile: UserProfile,
        feedback_history: list[tuple[str, int]] | None = None,
    ) -> list[ScoringResult]:
        """Оценка релевантности через LLM."""
        papers_data = [
            {
                "id": p.id,
                "title": p.title,
                "abstract": p.abstract[:1500],
            }
            for p in papers
        ]

        results = await self.llm.batch_score(
            papers=papers_data,
            user_interests=profile.keywords,
            user_keywords=profile.keywords,
            feedback_history=feedback_history,
        )

        return results


SOURCE_LABELS = {
    "arxiv": "arXiv",
    "huggingface_papers": "HuggingFace",
}


def _escape_html(text: str) -> str:
    """Экранирование спецсимволов для Telegram HTML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_recommendation_message(rec: RecommendedPaper) -> str:
    """Форматирование рекомендации для Telegram (HTML)."""
    authors = ", ".join(rec.paper.authors[:3])
    if len(rec.paper.authors) > 3:
        authors += " и др."

    source_label = SOURCE_LABELS.get(rec.paper.source, rec.paper.source)
    title = _escape_html(rec.paper.title)
    authors = _escape_html(authors)
    summary = _escape_html(rec.review.summary)
    why_important = _escape_html(rec.review.why_important)
    limitations = _escape_html(rec.review.limitations) if rec.review.limitations else ""
    how_helps = _escape_html(rec.review.how_helps)

    # Мета-строка: дата, источник, метрики
    meta_parts = [
        f"📅 {rec.paper.published.strftime('%d.%m.%Y')}",
        f"📖 {source_label}",
    ]
    if rec.paper.citation_count > 0:
        meta_parts.append(f"📈 {rec.paper.citation_count} цит.")
    if rec.paper.max_author_h_index > 0:
        meta_parts.append(f"h-index: {rec.paper.max_author_h_index}")
    meta_line = " · ".join(meta_parts)

    # Институции
    inst_line = ""
    if rec.paper.institutions:
        inst_names = ", ".join(_escape_html(i) for i in rec.paper.institutions[:3])
        inst_line = f"\n🏛 {inst_names}"

    # Секция ограничений (только если есть)
    limitations_block = ""
    if limitations:
        limitations_block = f"\n⚠️ <b>Ограничения:</b>\n{limitations}\n"

    return (
        f"📚 <b>{title}</b>\n\n"
        f"👥 <i>{authors}</i>{inst_line}\n"
        f"{meta_line}\n\n"
        f"📝 <b>Суть работы:</b>\n{summary}\n\n"
        f"🎯 <b>Почему важно:</b>\n{why_important}\n"
        f"{limitations_block}\n"
        f"🔬 <b>Для ваших исследований:</b>\n{how_helps}\n\n"
        f'🔗 <a href="{rec.paper.url}">Читать статью</a>'
    )
