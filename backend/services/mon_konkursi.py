"""Discovers new postings from the Ministry of Education and Science's own
"Конкурси" and "Стипендии" boards - a third and fourth source for the
Ресурси/Blog feed, alongside the two official FINKI sources in
finki_announcements.py.

https://mon.gov.mk/mk-MK/konkursi-i-stipendii/konkursi-mon (calls) and
.../stipendii-mon (scholarships) both list national postings - some relevant
to students at a public/private faculty or university, many not (K-12
textbooks, pupil dormitories, gymnasium programs, "ученички" i.e. pupil
scholarships). Both boards feed the same "Конкурси" category (see
finki_announcements.guess_category) once filtered through
is_relevant_to_students below.

Both list pages are server-rendered per page via a `?page=N` query string
(the site runs on Laravel Livewire, but its paginator also supports plain
query-string navigation for a full page load - confirmed by requesting
?page=2 directly and getting page 2's postings back in the initial HTML, no
JS execution needed). Detail pages live under the same path prefix as their
own list page, e.g.
https://mon.gov.mk/mk-MK/konkursi-i-stipendii/konkursi-mon/<slug>
https://mon.gov.mk/mk-MK/konkursi-i-stipendii/stipendii-mon/<slug>

Only discovers URLs here - fetching each posting's own title/excerpt/image
reuses services/blog_fetcher.py exactly like a manually-pasted link would,
so a scraped post looks and behaves identically to any other Blog card (see
scripts/fetch_finki_announcements.py, which wires this together).
"""
import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "LearnWiseBlogBot/0.1 "
    "(+https://github.com/ed7543/timski_proekt; educational use; fetches only "
    "the public MON konkursi/stipendii listing pages to surface new posts)"
)
FETCH_TIMEOUT_SECONDS = 20.0

KONKURSI_LIST_URL = "https://mon.gov.mk/mk-MK/konkursi-i-stipendii/konkursi-mon"
STIPENDII_LIST_URL = "https://mon.gov.mk/mk-MK/konkursi-i-stipendii/stipendii-mon"


def _fetch(url: str) -> str:
    with httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _discover_from_list(list_url: str, max_pages: int, source_label: str) -> list[str]:
    """Shared pagination/scraping logic for both boards - a detail page
    always lives directly under its own listing page's path, one segment
    deeper (e.g. .../konkursi-mon/fulbright-specialist-program), which is
    far more stable than matching on CSS classes. Stops early if a page
    yields no new links - either an empty/last page, or (defensively) a
    page that repeats an earlier one."""
    detail_re = re.compile(rf"^{re.escape(list_url)}/[^/?#]+/?$")
    seen: list[str] = []
    seen_set: set[str] = set()
    for page in range(1, max_pages + 1):
        url = list_url if page == 1 else f"{list_url}?page={page}"
        try:
            html = _fetch(url)
        except httpx.HTTPError as exc:
            logger.warning("mon_konkursi: failed to fetch %s page %d: %s", source_label, page, exc)
            break
        soup = BeautifulSoup(html, "html.parser")
        found_this_page = 0
        for a in soup.find_all("a", href=True):
            absolute = urljoin(list_url, a["href"])
            if not detail_re.match(absolute):
                continue
            if absolute not in seen_set:
                seen_set.add(absolute)
                seen.append(absolute)
                found_this_page += 1
        if found_this_page == 0:
            break
    return seen


def discover_konkursi_urls(max_pages: int = 3) -> list[str]:
    """Returns konkursi (calls/competitions) detail-page URLs found across
    the first `max_pages` pages of the list (newest first) - in the order
    encountered, duplicates removed. Caller (scripts/fetch_finki_
    announcements.py) is responsible for filtering out URLs already
    imported, so re-running this with a larger max_pages is always safe."""
    return _discover_from_list(KONKURSI_LIST_URL, max_pages, "konkursi")


def discover_stipendii_urls(max_pages: int = 3) -> list[str]:
    """Same as discover_konkursi_urls, for the separate Стипендии
    (scholarships) board."""
    return _discover_from_list(STIPENDII_LIST_URL, max_pages, "stipendii")


# Transparent keyword heuristic (NOT AI - same spirit as
# finki_announcements.guess_category) to keep only postings relevant to
# students at a public or private faculty/university. Both MON boards mix
# national K-12 content (textbooks, pupil dormitories, gymnasium programs,
# "ученички" i.e. pupil scholarships) in with higher-education content
# (student dorms, scholarships, faculty-level exchange programs) - only the
# latter belongs in a tutoring app aimed at FINKI (higher-ed) students. A
# wrong guess isn't destructive: a missed relevant posting just isn't
# imported (same as an unrecognized FINKI announcement), never mislabels or
# corrupts existing data.
_STUDENT_INCLUDE_KEYWORDS = [
    "студент", "факултет", "универзитет", "додипломски", "постдипломски",
    "докторски студии", "студентски дом",
    # Study-abroad / exchange programs (CEEPUS, Erasmus-style mobility,
    # faculty exchange) often phrase things around the program itself
    # rather than saying "студент" outright.
    "студиски", "мобилност", "размена",
]
_NON_STUDENT_EXCLUDE_KEYWORDS = [
    "ученик", "ученич",  # covers both "ученик(от/ци)" and "ученички/а" (adjectival)
    "основно образование", "средно образование", "гимназиско",
    "гимназија", "детска градинка", "наставник", "воспитувач",
]


def is_relevant_to_students(title: str) -> bool:
    """True if `title` looks like it's about students at a public/private
    faculty or university - see the keyword lists above. K-12 keywords
    (ученик/ученич/основно/средно/гимназиско/...) always exclude, even if a
    student-related word also appears, since MON postings sometimes phrase
    K-12 content in ways that could otherwise false-positive (e.g. a
    secondary-school accreditation notice that happens to mention
    "студенти" in an unrelated clause)."""
    lowered = title.lower()
    if any(kw in lowered for kw in _NON_STUDENT_EXCLUDE_KEYWORDS):
        return False
    return any(kw in lowered for kw in _STUDENT_INCLUDE_KEYWORDS)
