"""Discovers new posts from two official FINKI sources so they can be added
to the Ресурси/Blog feed automatically, without an admin having to notice and
paste each link by hand:

1. The general student-announcement board ("огласна табла" -
   oldsite.finki.ukim.mk/mk/student-announcement) - category guessed by
   keyword (see guess_category below).
2. The jobs & internships board (finki.ukim.mk/za-nas/studenti-i-zaednica/
   jobs-and-internships/) - every posting there always belongs to the
   "Пракси и работа" tab, so scripts/fetch_finki_announcements.py assigns
   that category directly without guessing.

Only discovers URLs here - fetching each posting's own title/excerpt/image
reuses services/blog_fetcher.py exactly like a manually-pasted link would, so
a scraped post looks and behaves identically to any other Blog card (see
scripts/fetch_finki_announcements.py, which wires this together).

No AI involved, and this module never invents content: a posting not found
on a list page simply isn't discovered, and the page's own <title>/meta tags
(via blog_fetcher) are still what fills in the card.
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
    "public FINKI announcement/job listing pages to surface new posts)"
)
FETCH_TIMEOUT_SECONDS = 20.0


def _fetch(url: str) -> str:
    with httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


# --- 1. General student-announcement board -------------------------------

ANNOUNCEMENTS_LIST_URL = "https://oldsite.finki.ukim.mk/mk/student-announcement"

# A content link on this site always looks like /mk/content/<slug> - this is
# far more stable than trying to match the page's CSS classes (which can
# change on a redesign without notice, silently breaking a class-based
# scraper without ever raising an error).
_CONTENT_LINK_RE = re.compile(r"^/mk/content/")


def discover_announcement_urls(max_pages: int = 2) -> list[str]:
    """Returns announcement detail-page URLs found across the first
    `max_pages` pages of the list (newest first, since that's how the site
    orders them) - in the order encountered, duplicates removed. Caller
    (scripts/fetch_finki_announcements.py) is responsible for filtering out
    URLs already imported, so re-running this with a larger max_pages is
    always safe."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for page in range(max_pages):
        url = ANNOUNCEMENTS_LIST_URL if page == 0 else f"{ANNOUNCEMENTS_LIST_URL}?page={page}"
        try:
            html = _fetch(url)
        except httpx.HTTPError as exc:
            logger.warning("finki_announcements: failed to fetch announcements page %d: %s", page, exc)
            break
        soup = BeautifulSoup(html, "html.parser")
        found_this_page = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not _CONTENT_LINK_RE.match(href):
                continue
            absolute = urljoin(ANNOUNCEMENTS_LIST_URL, href)
            if absolute not in seen_set:
                seen_set.add(absolute)
                seen.append(absolute)
                found_this_page += 1
        if found_this_page == 0:
            break
    return seen


# --- 2. Jobs & internships board ------------------------------------------

JOBS_LIST_URL = "https://finki.ukim.mk/za-nas/studenti-i-zaednica/jobs-and-internships/"

# Detail pages live under a different path root than the listing page itself
# (a custom "jobs-and-internships" post type), so matching on the absolute
# URL prefix is the stable, class-independent way to find them.
_JOB_LINK_RE = re.compile(r"^https://finki\.ukim\.mk/jobs-and-internships/")


def discover_job_urls(max_pages: int = 5) -> list[str]:
    """Returns job/internship detail-page URLs from the FINKI jobs board.
    Pagination there is `?pg=N` - an unrecognized/past-the-end page number
    is NOT an error, it silently falls back to showing page 1's listing
    again, so we stop as soon as a page's links exactly match page 1's:
    that's the site's way of telling us we've gone past the last page."""
    seen: list[str] = []
    seen_set: set[str] = set()
    first_page_links: set[str] | None = None
    for page in range(1, max_pages + 1):
        url = f"{JOBS_LIST_URL}?pg={page}"
        try:
            html = _fetch(url)
        except httpx.HTTPError as exc:
            logger.warning("finki_announcements: failed to fetch jobs page %d: %s", page, exc)
            break
        soup = BeautifulSoup(html, "html.parser")
        page_links: list[str] = []
        for a in soup.find_all("a", href=True):
            absolute = urljoin(JOBS_LIST_URL, a["href"])
            if _JOB_LINK_RE.match(absolute) and absolute not in page_links:
                page_links.append(absolute)
        page_link_set = set(page_links)

        if page == 1:
            first_page_links = page_link_set
        elif page_link_set == first_page_links:
            break

        new_this_page = 0
        for link in page_links:
            if link not in seen_set:
                seen_set.add(link)
                seen.append(link)
                new_this_page += 1
        if new_this_page == 0 and page > 1:
            break
    return seen


# --- Category guessing (announcements only - jobs are always "Пракси и
# работа", assigned directly by the caller) --------------------------------

# Very small, transparent keyword heuristic - NOT AI, just a first guess so
# a freshly-imported announcement lands somewhere sensible instead of always
# sitting uncategorized. Easy to retune: just edit the keyword lists below.
# A wrong guess isn't destructive - it only affects which tab the card shows
# under, never its title/excerpt/link.
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Конкурси", ["стипенди", "конкурс", "повик", "награда", "натпревар"]),
    ("Уписи", ["запишување", "упис", "семестар", "студентска служба", "матура"]),
    ("Настани", ["настан", "конференциј", "трибина", "работилниц", "промоциј", "предавање"]),
    ("Пракси и работа", ["пракса", "пракси", "вработув", "работно место", "job"]),
]


def guess_category(title: str) -> str | None:
    lowered = title.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return category
    return None
