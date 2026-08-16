"""Scraper for snimki.finki-hub.com (lecture recording links per course).

snimki.finki-hub.com is a static VitePress site generated straight from Markdown
files in github.com/finki-hub/recordings-listing (courses/<semester>/<slug>.md).
Rather than render+scrape the VitePress HTML (which just replays the same
Markdown through a client bundle), we pull the Markdown directly from
raw.githubusercontent.com - cheaper, more robust, and easier on their
infrastructure. We use the GitHub REST API once per run to enumerate the course
files (a single request), then fetch each course's Markdown individually
through our rate-limited client.

Markdown shape (see any file under courses/semester-*/*.md):

    ---
    title: Структурно програмирање
    keywords: [...]
    ---

    # Структурно програмирање

    ## Предавања

    ### Стефан Андонов, 2021 {#предавања-са-2021}

    1. [Циклуси (дел 1)](https://bbb-lb.finki.ukim.mk/...)
    2. [Циклуси (дел 2)](https://bbb-lb.finki.ukim.mk/...)

    ## Дополнителна содржина

    - [Изворен код ...](https://github.com/...)

    ## Белешки

    - **Нема**

A level-2 (##) section that has level-3 (###) subsections grouped by
"<presenter>, <year>" (presenter optional, "(English)"/other suffixes ignored
for grouping purposes) is treated as a *recordings* section - every numbered
or bulleted `[text](url)` line under it becomes a Recording. A level-2 section
with no level-3 subsections (typically "Дополнителна содржина", "Белешки") is
treated as a *materials* section - its `[text](url)` lines become
CourseMaterials. Bullet lines with no link (e.g. "**Нема**" = "None") are
skipped.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

from backend.services.ingestion.finki_hub_client import FinkiHubClient

logger = logging.getLogger(__name__)

REPO = "finki-hub/recordings-listing"
GITHUB_TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
SITE_BASE = "https://snimki.finki-hub.com"

_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)\s*(?:\{#.*\})?\s*$")
_ITEM_RE = re.compile(r"^\s*(?:\d+\.|-)\s+\[(?P<topic>[^\]]+)\]\((?P<url>[^)]+)\)")
_PRESENTER_YEAR_RE = re.compile(r"^(?:(?P<presenter>.+?),\s*)?(?P<year>\d{4})(?:\s*\(.*\))?$")
_FRONTMATTER_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class RecordingItem:
    topic: str
    presenter: Optional[str]
    year: Optional[int]
    category: str
    video_url: str


@dataclass
class MaterialItem:
    title: str
    category: Optional[str]
    url: str
    description: Optional[str] = None


@dataclass
class CourseScrapeResult:
    slug: str
    semester: Optional[str]
    name: str
    source_url: str
    recordings: List[RecordingItem] = field(default_factory=list)
    materials: List[MaterialItem] = field(default_factory=list)


def _unwrap_google_redirect(url: str) -> str:
    """Some older entries link through a Google-redirect tracking URL
    (https://www.google.com/url?q=<real-url>&sa=D&...) - unwrap to the real
    target when present, otherwise return the url unchanged."""
    if "google.com/url" not in url:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    target = qs.get("q", [None])[0]
    return target or url


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, body). If there's no frontmatter, returns ('', text)."""
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2]


def parse_course_markdown(text: str) -> tuple[str, List[RecordingItem], List[MaterialItem]]:
    """Parse a recordings-listing course Markdown file into (title, recordings, materials)."""
    frontmatter, body = _split_frontmatter(text)
    title_match = _FRONTMATTER_TITLE_RE.search(frontmatter)
    title = title_match.group(1).strip().strip('"').strip("'") if title_match else ""

    recordings: List[RecordingItem] = []
    materials: List[MaterialItem] = []

    current_h2: Optional[str] = None
    current_presenter: Optional[str] = None
    current_year: Optional[int] = None
    h3_seen_for_h2 = False

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        h2_match = _H2_RE.match(line)
        if h2_match:
            current_h2 = h2_match.group(1).strip()
            h3_seen_for_h2 = False
            current_presenter = None
            current_year = None
            continue

        h3_match = _H3_RE.match(line)
        if h3_match:
            h3_seen_for_h2 = True
            header_text = h3_match.group(1).strip()
            py_match = _PRESENTER_YEAR_RE.match(header_text)
            if py_match:
                current_presenter = py_match.group("presenter")
                current_year = int(py_match.group("year"))
            else:
                # Doesn't match "<presenter>, <year>" - keep the raw label as a
                # pseudo-presenter so it isn't silently dropped, no year.
                current_presenter = header_text or None
                current_year = None
            continue

        item_match = _ITEM_RE.match(line)
        if item_match and current_h2:
            topic = item_match.group("topic").strip()
            url = _unwrap_google_redirect(item_match.group("url").strip())
            if h3_seen_for_h2:
                recordings.append(RecordingItem(
                    topic=topic,
                    presenter=current_presenter,
                    year=current_year,
                    category=current_h2,
                    video_url=url,
                ))
            else:
                materials.append(MaterialItem(
                    title=topic,
                    category=current_h2,
                    url=url,
                ))

    return title, recordings, materials


async def list_course_files(client: FinkiHubClient) -> List[tuple[str, str]]:
    """Return [(semester, slug), ...] for every course Markdown file in the repo,
    via a single GitHub API tree listing call (excludes courses/index.md and the
    per-semester courses/semester-N/index.md placeholder files)."""
    data = await client.get_json(GITHUB_TREE_URL)
    if not data:
        logger.warning("Could not list %s tree from GitHub API", REPO)
        return []

    results: List[tuple[str, str]] = []
    for item in data.get("tree", []):
        path = item.get("path", "")
        m = re.match(r"^courses/(semester-\d+)/([^/]+)\.md$", path)
        if not m:
            continue
        semester, slug = m.group(1), m.group(2)
        if slug == "index":
            continue
        results.append((semester, slug))
    return results


async def fetch_course(client: FinkiHubClient, semester: str, slug: str) -> Optional[CourseScrapeResult]:
    """Fetch and parse a single course's Markdown file."""
    raw_url = f"{RAW_BASE}/courses/{semester}/{slug}.md"
    text = await client.get_text(raw_url)
    if not text:
        return None

    title, recordings, materials = parse_course_markdown(text)
    if not title:
        logger.warning("No frontmatter title found for %s/%s, skipping", semester, slug)
        return None

    source_url = f"{SITE_BASE}/courses/{semester}/{slug}"
    return CourseScrapeResult(
        slug=slug,
        semester=semester,
        name=title,
        source_url=source_url,
        recordings=recordings,
        materials=materials,
    )
