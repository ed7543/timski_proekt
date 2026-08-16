import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.models import CachedSearch
from backend.models.searchResult import SearchResult
from backend.web_search.search import build_search_query, web_search

# Similarity threshold for the pg_trgm fuzzy-match fallback (0..1, higher = stricter).
# Tune empirically once real usage data comes in.
SIMILARITY_THRESHOLD = 0.35

# Study-content search results don't go stale on a clock the way news does, but we
# still refresh occasionally in case docs have moved/changed.
STALE_AFTER = timedelta(days=90)


def normalize_query(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace - used as the cache key."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_cached(db: Session, question: str, subject: Optional[str]) -> Optional[CachedSearch]:
    """Look up a cached entry for this question: exact normalized match first (cheap,
    index-only), then a pg_trgm similarity fallback for near-duplicate phrasing."""
    normalized = normalize_query(question)
    if not normalized:
        return None

    q = db.query(CachedSearch).filter(CachedSearch.normalized_query == normalized)
    q = q.filter(CachedSearch.subject == subject) if subject else q.filter(CachedSearch.subject.is_(None))
    exact = q.first()
    if exact:
        return exact

    similarity = func.similarity(CachedSearch.normalized_query, normalized)
    q = db.query(CachedSearch).filter(similarity >= SIMILARITY_THRESHOLD)
    q = q.filter(CachedSearch.subject == subject) if subject else q.filter(CachedSearch.subject.is_(None))
    return q.order_by(similarity.desc()).first()


def _serialize(results: List[SearchResult]) -> list:
    return [r.model_dump() for r in results]


def _to_search_results(raw: list) -> List[SearchResult]:
    return [SearchResult(**item) for item in raw]


def _record_hit(db: Session, entry: CachedSearch) -> None:
    entry.hit_count += 1
    entry.last_used_at = datetime.utcnow()
    db.commit()


def _create(
    db: Session, question: str, subject: Optional[str], raw_query: str, results: List[SearchResult]
) -> CachedSearch:
    entry = CachedSearch(
        subject=subject,
        normalized_query=normalize_query(question),
        raw_query=raw_query,
        results=_serialize(results),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


async def get_or_search(
    db: Session, question: str, subject: Optional[str], num_results: int = 5
) -> Tuple[List[SearchResult], bool]:
    """Main entry point: return (results, from_cache). Cache hit -> bump hit_count/
    last_used_at (transparently re-searching if the entry is older than STALE_AFTER);
    cache miss -> live Tavily search, persist a new row, return fresh results."""
    entry = find_cached(db, question, subject)

    if entry:
        if datetime.utcnow() - entry.last_refreshed_at > STALE_AFTER:
            fresh_results = await web_search(entry.raw_query, num_results=num_results)
            if fresh_results:
                entry.results = _serialize(fresh_results)
                entry.last_refreshed_at = datetime.utcnow()
        _record_hit(db, entry)
        return _to_search_results(entry.results), True

    query = build_search_query(question, subject)
    results = await web_search(query, num_results=num_results)
    if results:
        _create(db, question, subject, query, results)
    return results, False


async def get_or_search_many(
    db: Session, questions: List[str], subject: Optional[str], num_results: int = 3
) -> List[SearchResult]:
    """Cached replacement for web_search.explore_search(): runs get_or_search() per
    query and returns a deduplicated, flattened result list."""
    seen_urls = set()
    all_results: List[SearchResult] = []

    for question in questions:
        results, _ = await get_or_search(db, question, subject, num_results=num_results)
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)

    return all_results
