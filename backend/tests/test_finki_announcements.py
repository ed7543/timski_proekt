"""Tests for the FINKI announcements auto-sync feature:

- backend/services/finki_announcements.py (URL discovery + category guessing)
- backend/scripts/fetch_finki_announcements.py (import orchestration)

All HTTP calls are mocked - these tests never hit real FINKI servers.
DB-touching tests (sync / _import_urls) use the real database but clean up
after themselves, matching the project's existing test pattern (see conftest.py).
"""
import pytest
from unittest.mock import patch, MagicMock

from backend.services.finki_announcements import (
    discover_announcement_urls,
    discover_job_urls,
    guess_category,
)
from backend.services.blog_fetcher import BlogFetchError
from backend.scripts.fetch_finki_announcements import (
    existing_source_urls,
    sync,
    _import_urls,
)
from backend.database.models import BlogPost
from backend.database.session import SessionLocal


# ── guess_category (pure function, no mocking) ──────────────────────────

class TestGuessCategory:
    def test_returns_konkursi_for_stipendii(self):
        assert guess_category("Конкурс за стипендии 2025") == "Конкурси"

    def test_returns_konkursi_for_natprevar(self):
        assert guess_category("Натпревар по програмирање") == "Конкурси"

    def test_returns_konkursi_for_povik(self):
        assert guess_category("Повик за апликации") == "Конкурси"

    def test_returns_konkursi_for_nagrada(self):
        assert guess_category("Награда за најдобар студент") == "Конкурси"

    def test_returns_upisi_for_zapishuvanje(self):
        assert guess_category("Запишување на зимски семестар") == "Уписи"

    def test_returns_upisi_for_upis(self):
        assert guess_category("Упис на нови студенти") == "Уписи"

    def test_returns_upisi_for_semestar(self):
        assert guess_category("Летен семестар 2025/26") == "Уписи"

    def test_returns_upisi_for_matura(self):
        assert guess_category("Информации за матура") == "Уписи"

    def test_returns_nastani_for_konferencija(self):
        assert guess_category("Меѓународна конференција ICT") == "Настани"

    def test_returns_nastani_for_rabotilnica(self):
        assert guess_category("Работилница за вештачка интелигенција") == "Настани"

    def test_returns_nastani_for_predavanje(self):
        assert guess_category("Гостинско предавање") == "Настани"

    def test_returns_nastani_for_promocija(self):
        assert guess_category("Промоција на дипломирани студенти") == "Настани"

    def test_returns_praksi_for_praksa(self):
        assert guess_category("Пракса во ИТ компанија") == "Пракси и работа"

    def test_returns_praksi_for_vrabotuvanje(self):
        assert guess_category("Оглас за вработување") == "Пракси и работа"

    def test_returns_praksi_for_job(self):
        assert guess_category("Open job position at FINKI") == "Пракси и работа"

    def test_returns_none_for_unrecognized(self):
        assert guess_category("Академски календар | ФИНКИ") is None

    def test_returns_none_for_navigation_link(self):
        assert guess_category("Лаборатории на ФИНКИ | ФИНКИ") is None

    def test_is_case_insensitive(self):
        assert guess_category("КОНКУРС ЗА СТИПЕНДИИ") == "Конкурси"

    def test_first_matching_category_wins(self):
        # "конкурс" matches Конкурси before anything else
        assert guess_category("Конкурс за работно место") == "Конкурси"


# ── discover_announcement_urls (mocked HTTP) ─────────────────────────────

SAMPLE_ANNOUNCEMENTS_HTML = """
<html><body>
  <a href="/mk/content/konkurs-za-stipendii-2025">Конкурс за стипендии</a>
  <a href="/mk/content/zapishuvanje-zimski-2025">Запишување зимски</a>
  <a href="/mk/about">За нас</a>
  <a href="/mk/content/gostinsko-predavanje">Гостинско предавање</a>
  <a href="https://example.com/external">Надворешен линк</a>
</body></html>
"""

SAMPLE_ANNOUNCEMENTS_PAGE2 = """
<html><body>
  <a href="/mk/content/nov-oglas-praksa">Нов оглас за пракса</a>
  <a href="/mk/content/konkurs-za-stipendii-2025">Конкурс за стипендии</a>
</body></html>
"""

EMPTY_PAGE_HTML = "<html><body><p>Нема содржина</p></body></html>"


class TestDiscoverAnnouncementUrls:
    @patch("backend.services.finki_announcements._fetch")
    def test_extracts_content_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_ANNOUNCEMENTS_HTML
        urls = discover_announcement_urls(max_pages=1)
        assert len(urls) == 3
        assert all("/mk/content/" in u for u in urls)

    @patch("backend.services.finki_announcements._fetch")
    def test_skips_non_content_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_ANNOUNCEMENTS_HTML
        urls = discover_announcement_urls(max_pages=1)
        assert not any("about" in u for u in urls)
        assert not any("example.com" in u for u in urls)

    @patch("backend.services.finki_announcements._fetch")
    def test_deduplicates_across_pages(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_ANNOUNCEMENTS_HTML, SAMPLE_ANNOUNCEMENTS_PAGE2]
        urls = discover_announcement_urls(max_pages=2)
        # Page 1 has 3, page 2 has 1 new + 1 duplicate = 4 unique total
        assert len(urls) == 4
        assert len(set(urls)) == 4

    @patch("backend.services.finki_announcements._fetch")
    def test_stops_on_empty_page(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_ANNOUNCEMENTS_HTML, EMPTY_PAGE_HTML]
        urls = discover_announcement_urls(max_pages=3)
        # Should stop after page 2 (empty), not try page 3
        assert mock_fetch.call_count == 2

    @patch("backend.services.finki_announcements._fetch")
    def test_handles_http_error_gracefully(self, mock_fetch):
        import httpx
        mock_fetch.side_effect = httpx.HTTPError("Connection refused")
        urls = discover_announcement_urls(max_pages=2)
        assert urls == []

    @patch("backend.services.finki_announcements._fetch")
    def test_returns_absolute_urls(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_ANNOUNCEMENTS_HTML
        urls = discover_announcement_urls(max_pages=1)
        assert all(u.startswith("https://oldsite.finki.ukim.mk/") for u in urls)


# ── discover_job_urls (mocked HTTP) ──────────────────────────────────────

SAMPLE_JOBS_HTML_PAGE1 = """
<html><body>
  <a href="https://finki.ukim.mk/jobs-and-internships/htec-praksa/">HTEC пракса</a>
  <a href="https://finki.ukim.mk/jobs-and-internships/ai-intern/">AI Intern</a>
  <a href="https://finki.ukim.mk/za-nas/kontakt/">Контакт</a>
</body></html>
"""

SAMPLE_JOBS_HTML_PAGE2 = """
<html><body>
  <a href="https://finki.ukim.mk/jobs-and-internships/web-dev/">Web Dev</a>
  <a href="https://finki.ukim.mk/jobs-and-internships/qa-tester/">QA Tester</a>
</body></html>
"""


class TestDiscoverJobUrls:
    @patch("backend.services.finki_announcements._fetch")
    def test_extracts_job_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_JOBS_HTML_PAGE1
        urls = discover_job_urls(max_pages=1)
        assert len(urls) == 2
        assert all("jobs-and-internships" in u for u in urls)

    @patch("backend.services.finki_announcements._fetch")
    def test_skips_non_job_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_JOBS_HTML_PAGE1
        urls = discover_job_urls(max_pages=1)
        assert not any("kontakt" in u for u in urls)

    @patch("backend.services.finki_announcements._fetch")
    def test_collects_across_pages(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_JOBS_HTML_PAGE1, SAMPLE_JOBS_HTML_PAGE2]
        urls = discover_job_urls(max_pages=2)
        assert len(urls) == 4

    @patch("backend.services.finki_announcements._fetch")
    def test_stops_when_page_repeats_page1(self, mock_fetch):
        # Page 3 returns the same links as page 1 = past the end
        mock_fetch.side_effect = [
            SAMPLE_JOBS_HTML_PAGE1,
            SAMPLE_JOBS_HTML_PAGE2,
            SAMPLE_JOBS_HTML_PAGE1,  # duplicate of page 1
        ]
        urls = discover_job_urls(max_pages=5)
        assert mock_fetch.call_count == 3
        assert len(urls) == 4  # only page 1 + page 2 links

    @patch("backend.services.finki_announcements._fetch")
    def test_handles_http_error_gracefully(self, mock_fetch):
        import httpx
        mock_fetch.side_effect = httpx.HTTPError("Timeout")
        urls = discover_job_urls(max_pages=2)
        assert urls == []


# ── _import_urls (mocked fetcher + real DB) ──────────────────────────────

# Unique prefix so cleanup never touches real data
_TEST_URL_PREFIX = "https://test.example/__finki_test__/"


def _cleanup_test_blog_posts(db):
    """Remove only blog posts created by these tests."""
    db.query(BlogPost).filter(
        BlogPost.source_url.like(f"{_TEST_URL_PREFIX}%")
    ).delete(synchronize_session=False)
    db.commit()


class TestImportUrls:
    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    def test_adds_posts_to_database(self, mock_fetch_meta):
        mock_fetch_meta.return_value = {
            "title": "Тест оглас",
            "excerpt": "Краток опис",
            "image_url": "https://example.com/img.jpg",
        }
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            urls = [f"{_TEST_URL_PREFIX}post-1", f"{_TEST_URL_PREFIX}post-2"]
            added = _import_urls(
                db, urls, dry_run=False,
                category_of=lambda meta: "Настани",
                source_name="TEST",
            )
            assert added == 2
            posts = db.query(BlogPost).filter(
                BlogPost.source_url.like(f"{_TEST_URL_PREFIX}%")
            ).all()
            assert len(posts) == 2
            assert all(p.category == "Настани" for p in posts)
            assert all(p.source_name == "TEST" for p in posts)
            assert all(p.added_by_id is None for p in posts)
        finally:
            _cleanup_test_blog_posts(db)
            db.close()

    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    def test_dry_run_does_not_write(self, mock_fetch_meta):
        mock_fetch_meta.return_value = {
            "title": "Тест dry-run",
            "excerpt": "Нема да се запише",
            "image_url": None,
        }
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            urls = [f"{_TEST_URL_PREFIX}dry-1"]
            added = _import_urls(
                db, urls, dry_run=True,
                category_of=lambda meta: "Уписи",
            )
            assert added == 1  # counted but not written
            posts = db.query(BlogPost).filter(
                BlogPost.source_url.like(f"{_TEST_URL_PREFIX}%")
            ).all()
            assert len(posts) == 0
        finally:
            _cleanup_test_blog_posts(db)
            db.close()

    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    def test_skips_when_category_is_none(self, mock_fetch_meta):
        mock_fetch_meta.return_value = {
            "title": "Лаборатории на ФИНКИ",
            "excerpt": "Навигација",
            "image_url": None,
        }
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            urls = [f"{_TEST_URL_PREFIX}nav-link"]
            added = _import_urls(
                db, urls, dry_run=False,
                category_of=lambda meta: None,  # no category
            )
            assert added == 0
        finally:
            _cleanup_test_blog_posts(db)
            db.close()

    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    def test_skips_on_fetch_error(self, mock_fetch_meta):
        mock_fetch_meta.side_effect = BlogFetchError("404 Not Found")
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            urls = [f"{_TEST_URL_PREFIX}broken"]
            added = _import_urls(
                db, urls, dry_run=False,
                category_of=lambda meta: "Настани",
            )
            assert added == 0
        finally:
            _cleanup_test_blog_posts(db)
            db.close()


# ── existing_source_urls ─────────────────────────────────────────────────

class TestExistingSourceUrls:
    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    def test_returns_known_urls(self, mock_fetch_meta):
        mock_fetch_meta.return_value = {
            "title": "Тест", "excerpt": "Тест", "image_url": None,
        }
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            url = f"{_TEST_URL_PREFIX}existing-check"
            _import_urls(db, [url], dry_run=False,
                         category_of=lambda meta: "Настани", source_name="TEST")
            known = existing_source_urls(db)
            assert url in known
        finally:
            _cleanup_test_blog_posts(db)
            db.close()


# ── sync (end-to-end with all externals mocked) ─────────────────────────

class TestSync:
    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.discover_job_urls")
    @patch("backend.scripts.fetch_finki_announcements.discover_announcement_urls")
    def test_imports_from_both_sources(
        self, mock_announcements, mock_jobs, mock_fetch_meta
    ):
        mock_announcements.return_value = [
            f"{_TEST_URL_PREFIX}sync-ann-1",
            f"{_TEST_URL_PREFIX}sync-ann-2",
        ]
        mock_jobs.return_value = [
            f"{_TEST_URL_PREFIX}sync-job-1",
        ]
        mock_fetch_meta.return_value = {
            "title": "Конкурс за стипендии",
            "excerpt": "Опис",
            "image_url": None,
        }
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            added = sync(db, max_pages=1, dry_run=False)
            # 2 announcements (both have "конкурс" in mocked title) + 1 job
            assert added == 3
            posts = db.query(BlogPost).filter(
                BlogPost.source_url.like(f"{_TEST_URL_PREFIX}sync-%")
            ).all()
            assert len(posts) == 3
            job_posts = [p for p in posts if "job" in p.source_url]
            assert len(job_posts) == 1
            assert job_posts[0].category == "Пракси и работа"
        finally:
            _cleanup_test_blog_posts(db)
            db.close()

    @patch("backend.scripts.fetch_finki_announcements.FETCH_DELAY_SECONDS", 0)
    @patch("backend.scripts.fetch_finki_announcements.fetch_article_metadata")
    @patch("backend.scripts.fetch_finki_announcements.discover_job_urls")
    @patch("backend.scripts.fetch_finki_announcements.discover_announcement_urls")
    def test_does_not_duplicate_existing_posts(
        self, mock_announcements, mock_jobs, mock_fetch_meta
    ):
        mock_fetch_meta.return_value = {
            "title": "Конкурс тест",
            "excerpt": "Опис",
            "image_url": None,
        }
        db = SessionLocal()
        try:
            _cleanup_test_blog_posts(db)
            url = f"{_TEST_URL_PREFIX}sync-dup-1"
            mock_announcements.return_value = [url]
            mock_jobs.return_value = []

            # First run - should add 1
            added1 = sync(db, max_pages=1, dry_run=False)
            assert added1 == 1

            # Second run with same URL - should add 0 (already known)
            added2 = sync(db, max_pages=1, dry_run=False)
            assert added2 == 0

            posts = db.query(BlogPost).filter(
                BlogPost.source_url == url
            ).all()
            assert len(posts) == 1  # no duplicate
        finally:
            _cleanup_test_blog_posts(db)
            db.close()
