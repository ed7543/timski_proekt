"""Tests for backend/services/search_cache.py.

Requires a real Postgres database with the pg_trgm extension enabled (run
`alembic upgrade head` first) - the fuzzy-match tests use `func.similarity()`,
which is Postgres-specific and has no SQLite equivalent.
"""
import pytest

from backend.database.models import CachedSearch
from backend.database.session import SessionLocal
from backend.models.searchResult import SearchResult
from backend.services import search_cache as sc


@pytest.fixture
def db():
    session = SessionLocal()
    session.query(CachedSearch).delete()
    session.commit()
    yield session
    session.query(CachedSearch).delete()
    session.commit()
    session.close()


def test_normalize_query_strips_punctuation_and_case():
    assert sc.normalize_query("What is  Recursion??") == "what is recursion"
    assert sc.normalize_query("  RECURSION!  ") == "recursion"


def test_find_cached_returns_none_when_empty(db):
    assert sc.find_cached(db, "anything", None) is None


def test_exact_and_fuzzy_match(db):
    results = [SearchResult(title="Recursion", url="https://example.com/r", snippet="...")]
    entry = sc._create(db, "What is recursion?", "Structural Programming", "recursion docs", results)

    exact = sc.find_cached(db, "What is recursion?", "Structural Programming")
    assert exact is not None and exact.id == entry.id

    normalized_variant = sc.find_cached(db, "what is recursion", "Structural Programming")
    assert normalized_variant is not None and normalized_variant.id == entry.id

    fuzzy_variant = sc.find_cached(db, "what is a recursion", "Structural Programming")
    assert fuzzy_variant is not None and fuzzy_variant.id == entry.id


def test_subject_scoping(db):
    results = [SearchResult(title="Recursion", url="https://example.com/r", snippet="...")]
    sc._create(db, "What is recursion?", "Structural Programming", "recursion docs", results)

    assert sc.find_cached(db, "What is recursion?", "Other Subject") is None
    assert sc.find_cached(db, "What is recursion?", None) is None


def test_record_hit_increments_count(db):
    results = [SearchResult(title="Recursion", url="https://example.com/r", snippet="...")]
    entry = sc._create(db, "What is recursion?", None, "recursion docs", results)
    assert entry.hit_count == 1

    sc._record_hit(db, entry)
    db.refresh(entry)
    assert entry.hit_count == 2


@pytest.mark.asyncio
async def test_get_or_search_reuses_cache_on_second_call(db, monkeypatch):
    call_count = {"n": 0}

    async def fake_web_search(query, num_results=5):
        call_count["n"] += 1
        return [SearchResult(title="T", url="https://example.com", snippet="s")]

    monkeypatch.setattr(sc, "web_search", fake_web_search)

    results1, from_cache1 = await sc.get_or_search(db, "What is a binary search tree?", "DSA")
    results2, from_cache2 = await sc.get_or_search(db, "What is a binary search tree?", "DSA")

    assert from_cache1 is False
    assert from_cache2 is True
    assert call_count["n"] == 1  # second call must NOT hit the (fake) live search again
    assert db.query(CachedSearch).count() == 1
