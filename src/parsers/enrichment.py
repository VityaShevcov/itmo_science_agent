"""Обогащение статей данными из Semantic Scholar и OpenAlex."""

import asyncio
import json
import logging
import re
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from .base import Paper


logger = logging.getLogger(__name__)

# Таймаут для API запросов
API_TIMEOUT = 10


def _extract_arxiv_id(paper: Paper) -> str | None:
    """Извлечь чистый arXiv ID из paper.id или paper.url (без версии vN)."""
    # paper.id: "2501.12345", "2501.12345v1" или "hf_2501.12345"
    raw = paper.id.removeprefix("hf_")
    # Убираем суффикс версии (v1, v2, ...)
    raw = re.sub(r"v\d+$", "", raw)
    if re.match(r"\d{4}\.\d{4,6}$", raw):
        return raw

    # Из URL
    for pattern in [r"arxiv\.org/abs/(\d{4}\.\d{4,6})", r"papers/(\d{4}\.\d{4,6})"]:
        match = re.search(pattern, paper.url)
        if match:
            return match.group(1)

    return None


async def enrich_papers(papers: list[Paper]) -> None:
    """Обогатить статьи данными из Semantic Scholar и OpenAlex."""
    if not papers:
        return

    loop = asyncio.get_event_loop()

    # Запускаем оба API параллельно
    await asyncio.gather(
        loop.run_in_executor(None, _enrich_semantic_scholar, papers),
        loop.run_in_executor(None, _enrich_openalex, papers),
    )

    # Логируем результаты
    enriched = sum(1 for p in papers if p.citation_count > 0 or p.max_author_h_index > 0)
    logger.info(f"Enriched {enriched}/{len(papers)} papers with external data")


def _enrich_semantic_scholar(papers: list[Paper]) -> None:
    """Батч-запрос к Semantic Scholar API."""
    # Маппинг arxiv_id -> paper
    arxiv_map: dict[str, Paper] = {}
    ids = []
    for p in papers:
        arxiv_id = _extract_arxiv_id(p)
        if arxiv_id:
            s2_id = f"arXiv:{arxiv_id}"
            ids.append(s2_id)
            arxiv_map[s2_id] = p

    if not ids:
        return

    try:
        req = Request(
            "https://api.semanticscholar.org/graph/v1/paper/batch",
            data=json.dumps({"ids": ids}).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ScienceAgent/1.0",
            },
            method="POST",
        )
        # Добавляем fields через query param
        req.full_url += "?fields=citationCount,influentialCitationCount,authors.hIndex"

        response = urlopen(req, timeout=API_TIMEOUT)
        results = json.loads(response.read())

    except (URLError, HTTPError, json.JSONDecodeError) as e:
        logger.warning(f"Semantic Scholar API error: {e}")
        return

    # Разбираем результаты (массив, порядок совпадает с ids)
    for s2_id, result in zip(ids, results):
        if result is None:
            continue

        paper = arxiv_map.get(s2_id)
        if not paper:
            continue

        paper.citation_count = result.get("citationCount", 0) or 0
        paper.influential_citations = result.get("influentialCitationCount", 0) or 0

        # Максимальный h-index среди авторов
        authors = result.get("authors", [])
        h_indices = [a.get("hIndex", 0) or 0 for a in authors if a]
        if h_indices:
            paper.max_author_h_index = max(h_indices)

    logger.info(f"Semantic Scholar: enriched {len([r for r in results if r])} papers")


def _enrich_openalex(papers: list[Paper]) -> None:
    """Запрос к OpenAlex: citations из works + институции из authors."""
    arxiv_map: dict[str, Paper] = {}
    doi_filters = []
    for p in papers:
        arxiv_id = _extract_arxiv_id(p)
        if arxiv_id:
            doi = f"https://doi.org/10.48550/arxiv.{arxiv_id}"
            doi_filters.append(doi)
            arxiv_map[doi] = p

    if not doi_filters:
        return

    # Шаг 1: Works — citations + author IDs
    # author_id -> paper (для шага 2)
    author_to_papers: dict[str, list[Paper]] = {}

    for batch_start in range(0, len(doi_filters), 50):
        batch = doi_filters[batch_start:batch_start + 50]
        pipe_dois = "|".join(batch)

        try:
            url = (
                f"https://api.openalex.org/works?"
                f"filter=doi:{pipe_dois}&"
                f"select=doi,cited_by_count,authorships&"
                f"per_page=50&"
                f"mailto=science-agent@example.com"
            )
            req = Request(url, headers={"User-Agent": "ScienceAgent/1.0"})
            data = json.loads(urlopen(req, timeout=API_TIMEOUT).read())

        except (URLError, HTTPError, json.JSONDecodeError) as e:
            logger.warning(f"OpenAlex works API error: {e}")
            continue

        for work in data.get("results", []):
            doi = work.get("doi", "")
            paper = arxiv_map.get(doi)
            if not paper:
                continue

            oa_citations = work.get("cited_by_count", 0) or 0
            if oa_citations > paper.citation_count:
                paper.citation_count = oa_citations

            # Собираем author IDs (первые 3) для шага 2
            for authorship in work.get("authorships", [])[:3]:
                author = authorship.get("author", {})
                aid = author.get("id", "")
                if aid:
                    author_to_papers.setdefault(aid, []).append(paper)

    if not author_to_papers:
        logger.info("OpenAlex: no author IDs to look up")
        return

    # Шаг 2: Authors batch — last_known_institutions
    all_author_ids = list(author_to_papers.keys())
    for batch_start in range(0, len(all_author_ids), 50):
        batch = all_author_ids[batch_start:batch_start + 50]
        pipe_ids = "|".join(batch)

        try:
            url = (
                f"https://api.openalex.org/authors?"
                f"filter=openalex:{pipe_ids}&"
                f"select=id,display_name,last_known_institutions&"
                f"per_page=50&"
                f"mailto=science-agent@example.com"
            )
            req = Request(url, headers={"User-Agent": "ScienceAgent/1.0"})
            data = json.loads(urlopen(req, timeout=API_TIMEOUT).read())

        except (URLError, HTTPError, json.JSONDecodeError) as e:
            logger.warning(f"OpenAlex authors API error: {e}")
            continue

        for author in data.get("results", []):
            aid = author.get("id", "")
            insts = author.get("last_known_institutions") or []
            inst_names = [i.get("display_name", "") for i in insts if i and i.get("display_name")]

            if inst_names and aid in author_to_papers:
                for paper in author_to_papers[aid]:
                    existing = set(paper.institutions or [])
                    for name in inst_names:
                        if name not in existing:
                            existing.add(name)
                    paper.institutions = list(existing)[:5]

    enriched = sum(1 for p in papers if p.institutions)
    logger.info(f"OpenAlex: got institutions for {enriched} papers")
