"""Tests for backend/services/mon_konkursi.py (MON konkursi URL discovery).

All HTTP calls are mocked - these tests never hit the real mon.gov.mk server.
"""
from unittest.mock import patch

from backend.services.mon_konkursi import (
    discover_konkursi_urls,
    discover_stipendii_urls,
    is_relevant_to_students,
)

SAMPLE_KONKURSI_PAGE1 = """
<html><body>
  <a href="/mk-MK/konkursi-i-stipendii/konkursi-mon/fulbright-specialist-program">Fulbright</a>
  <a href="/mk-MK/konkursi-i-stipendii/konkursi-mon/yes-programa-povik-za-prijavuvanje">YES програма</a>
  <a href="/mk-MK/konkursi-i-stipendii/stipendii-mon">Стипендии - МОН</a>
  <a href="/mk-MK/ministerstvo/misija-i-vizija">Мисија и визија</a>
</body></html>
"""

SAMPLE_KONKURSI_PAGE2 = """
<html><body>
  <a href="/mk-MK/konkursi-i-stipendii/konkursi-mon/konkurs-za-ucebnici-vo-osnovno-obrazovanie3">Учебници</a>
  <a href="/mk-MK/konkursi-i-stipendii/konkursi-mon/fulbright-specialist-program">Fulbright</a>
</body></html>
"""

EMPTY_PAGE_HTML = "<html><body><p>Нема содржина</p></body></html>"


class TestDiscoverKonkursiUrls:
    @patch("backend.services.mon_konkursi._fetch")
    def test_extracts_detail_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_KONKURSI_PAGE1
        urls = discover_konkursi_urls(max_pages=1)
        assert len(urls) == 2
        assert all("/konkursi-mon/" in u for u in urls)

    @patch("backend.services.mon_konkursi._fetch")
    def test_skips_listing_page_and_unrelated_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_KONKURSI_PAGE1
        urls = discover_konkursi_urls(max_pages=1)
        # "stipendii-mon" is a sibling listing page, not a konkurs detail page
        assert not any("stipendii-mon" in u for u in urls)
        # a top-level ministerstvo/ page is a different section entirely
        assert not any("ministerstvo" in u for u in urls)

    @patch("backend.services.mon_konkursi._fetch")
    def test_deduplicates_across_pages(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_KONKURSI_PAGE1, SAMPLE_KONKURSI_PAGE2]
        urls = discover_konkursi_urls(max_pages=2)
        # Page 1 has 2, page 2 has 1 new + 1 duplicate (fulbright) = 3 unique total
        assert len(urls) == 3
        assert len(set(urls)) == 3

    @patch("backend.services.mon_konkursi._fetch")
    def test_stops_on_empty_page(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_KONKURSI_PAGE1, EMPTY_PAGE_HTML]
        urls = discover_konkursi_urls(max_pages=3)
        # Should stop after page 2 (no new links), not try page 3
        assert mock_fetch.call_count == 2

    @patch("backend.services.mon_konkursi._fetch")
    def test_handles_http_error_gracefully(self, mock_fetch):
        import httpx
        mock_fetch.side_effect = httpx.HTTPError("Connection refused")
        urls = discover_konkursi_urls(max_pages=2)
        assert urls == []

    @patch("backend.services.mon_konkursi._fetch")
    def test_returns_absolute_urls(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_KONKURSI_PAGE1
        urls = discover_konkursi_urls(max_pages=1)
        assert all(u.startswith("https://mon.gov.mk/") for u in urls)

    @patch("backend.services.mon_konkursi._fetch")
    def test_requests_page_param_from_second_page_on(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_KONKURSI_PAGE1, SAMPLE_KONKURSI_PAGE2]
        discover_konkursi_urls(max_pages=2)
        called_urls = [call.args[0] for call in mock_fetch.call_args_list]
        assert called_urls[0] == "https://mon.gov.mk/mk-MK/konkursi-i-stipendii/konkursi-mon"
        assert called_urls[1] == "https://mon.gov.mk/mk-MK/konkursi-i-stipendii/konkursi-mon?page=2"

SAMPLE_STIPENDII_PAGE1 = """
<html><body>
  <a href="/mk-MK/konkursi-i-stipendii/stipendii-mon/stipendii-za-studenti-vo-stranstvo">Стипендии за студенти во странство</a>
  <a href="/mk-MK/konkursi-i-stipendii/stipendii-mon/informacija-za-korisnici-na-ucenicki-stipendii">Информација за корисници на ученички стипендии</a>
  <a href="/mk-MK/konkursi-i-stipendii/konkursi-mon">Конкурси - МОН</a>
  <a href="/mk-MK/ministerstvo/misija-i-vizija">Мисија и визија</a>
</body></html>
"""

SAMPLE_STIPENDII_PAGE2 = """
<html><body>
  <a href="/mk-MK/konkursi-i-stipendii/stipendii-mon/dopolnitelna-stipendija-za-studenti-so-hendikep">Дополнителна стипендија</a>
  <a href="/mk-MK/konkursi-i-stipendii/stipendii-mon/stipendii-za-studenti-vo-stranstvo">Стипендии за студенти во странство</a>
</body></html>
"""


class TestDiscoverStipendiiUrls:
    @patch("backend.services.mon_konkursi._fetch")
    def test_extracts_detail_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_STIPENDII_PAGE1
        urls = discover_stipendii_urls(max_pages=1)
        assert len(urls) == 2
        assert all("/stipendii-mon/" in u for u in urls)

    @patch("backend.services.mon_konkursi._fetch")
    def test_skips_listing_page_and_unrelated_links(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_STIPENDII_PAGE1
        urls = discover_stipendii_urls(max_pages=1)
        # "konkursi-mon" is the sibling listing page, not a stipendija detail page
        assert not any("konkursi-mon" in u for u in urls)
        assert not any("ministerstvo" in u for u in urls)

    @patch("backend.services.mon_konkursi._fetch")
    def test_deduplicates_across_pages(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_STIPENDII_PAGE1, SAMPLE_STIPENDII_PAGE2]
        urls = discover_stipendii_urls(max_pages=2)
        # Page 1 has 2, page 2 has 1 new + 1 duplicate = 3 unique total
        assert len(urls) == 3
        assert len(set(urls)) == 3

    @patch("backend.services.mon_konkursi._fetch")
    def test_stops_on_empty_page(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_STIPENDII_PAGE1, EMPTY_PAGE_HTML]
        urls = discover_stipendii_urls(max_pages=3)
        assert mock_fetch.call_count == 2

    @patch("backend.services.mon_konkursi._fetch")
    def test_handles_http_error_gracefully(self, mock_fetch):
        import httpx
        mock_fetch.side_effect = httpx.HTTPError("Connection refused")
        urls = discover_stipendii_urls(max_pages=2)
        assert urls == []

    @patch("backend.services.mon_konkursi._fetch")
    def test_returns_absolute_urls(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_STIPENDII_PAGE1
        urls = discover_stipendii_urls(max_pages=1)
        assert all(u.startswith("https://mon.gov.mk/") for u in urls)

    @patch("backend.services.mon_konkursi._fetch")
    def test_requests_page_param_from_second_page_on(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_STIPENDII_PAGE1, SAMPLE_STIPENDII_PAGE2]
        discover_stipendii_urls(max_pages=2)
        called_urls = [call.args[0] for call in mock_fetch.call_args_list]
        assert called_urls[0] == "https://mon.gov.mk/mk-MK/konkursi-i-stipendii/stipendii-mon"
        assert called_urls[1] == "https://mon.gov.mk/mk-MK/konkursi-i-stipendii/stipendii-mon?page=2"


# ── is_relevant_to_students (pure function, no mocking) ──────────────────

class TestIsRelevantToStudents:
    def test_true_for_student_dormitory(self):
        assert is_relevant_to_students(
            "Конкурс за прием на студенти запишани на додипломски студии во "
            "државните и приватните студентски домови"
        ) is True

    def test_true_for_subsidized_meal(self):
        assert is_relevant_to_students(
            "Јавен повик за остварување на правото на субвенциониран "
            "студентски оброк за академската 2026/2027 година"
        ) is True

    def test_true_for_faculty_exchange(self):
        assert is_relevant_to_students("Повик за размена на студенти на факултет во странство") is True

    def test_false_for_primary_school_textbooks(self):
        assert is_relevant_to_students("Конкурс за учебници во основно образование") is False

    def test_false_for_gymnasium_textbook(self):
        assert is_relevant_to_students("Конкурс за учебник во гимназиско образование") is False

    def test_false_for_pupil_dormitory(self):
        assert is_relevant_to_students(
            "Резултати од Конкурсот за прием на ученици во јавните ученички домови"
        ) is False

    def test_false_for_pupil_scholarships(self):
        # Regression: "ученик" is not a substring of "ученички" - both
        # exclude keywords need to be present to catch this one.
        assert is_relevant_to_students(
            "Информација за корисници на ученички стипендии"
        ) is False

    def test_false_for_unrelated_ministry_notice(self):
        assert is_relevant_to_students("Известување за спроведена постапка на дел од Конкурс бр.26-1359/1") is False

    def test_exclude_wins_even_if_student_word_present(self):
        # K-12 exclusion keyword takes priority even if "студент" also appears
        assert is_relevant_to_students(
            "Гимназиско образование - известување за наставници и студенти на педагошки факултет"
        ) is False

    def test_is_case_insensitive(self):
        assert is_relevant_to_students("ПОВИК ЗА СТУДЕНТСКИ ДОМ") is True

    def test_true_for_study_abroad_stay(self):
        assert is_relevant_to_students(
            "Конкурс за стипендии за студиски престој во земјите членки на CEEPUS Програмата"
        ) is True

    def test_true_for_mobility_program(self):
        assert is_relevant_to_students(
            "Стипендии во рамки на Словачката национална програма за мобилност"
        ) is True

    def test_true_for_exchange_program(self):
        assert is_relevant_to_students(
            "Повик за размена во рамките на Erasmus+ програмата за високото образование"
        ) is True

