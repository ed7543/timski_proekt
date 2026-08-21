"""Fetches and extracts plain text from a course's source (the `source` /
`additional_sources` URL from courses_db.json), for the lesson-content seeding
pipeline (seed_lessons.py, invoked via `cli.py --source lessons`).

Two source kinds, handled very differently in reliability:

  - HTML pages (OpenStax, systemsapproach.org, MIT OCW course pages, ...):
    split using the page's own <h1>-<h4> tags. This is structural, not
    guessed - reliable whenever the source actually uses real headings.
  - PDFs: extracted as plain text via pypdf, then split *heuristically* by a
    regex over short/title-like lines. PDFs vary too much in layout for
    anything more precise without per-document tuning - this is best-effort,
    reviewed via the seed_lessons.py match report (see lesson_matching.py).

Local-file sources (courses_db.json entries with source.url == None - e.g.
Оперативни системи / КМиБ / Е-трговија / Шаблони / Вовед во науката за
податоци) are NOT handled here. Those 5 courses are intentionally excluded
from this pass (agreed in chat) - extract_sections() raises ValueError for
them so the caller skips and logs, rather than silently doing nothing.

Fetched raw bytes are cached to disk (keyed by URL hash) so re-running a batch
after a crash, or re-running with a different confidence threshold, doesn't
re-download anything.
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
import io

logger = logging.getLogger(__name__)

USER_AGENT = (
    "LearnWiseLessonSeedBot/0.1 "
    "(+https://github.com/ed7543/timski_proekt; educational use, open-license sources only)"
)

FETCH_TIMEOUT_SECONDS = 30.0


@dataclass
class Section:
    heading: str
    text: str


# ---------------------------------------------------------------------------
# Fetching + caching
# ---------------------------------------------------------------------------

def _is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def _cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    ext = "pdf" if _is_pdf_url(url) else "html"
    return cache_dir / f"{digest}.{ext}"


def _fetch_raw(url: str) -> bytes:
    with httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def get_or_fetch_raw(url: str, cache_dir: Path) -> bytes:
    """Returns the cached bytes for `url` if present, otherwise fetches and
    caches them. Raises httpx.HTTPError on a network/HTTP failure - caller
    should catch and log a skip for that course."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, url)
    if path.exists():
        logger.info("Using cached source for %s (%s)", url, path.name)
        return path.read_bytes()
    logger.info("Fetching %s ...", url)
    content = _fetch_raw(url)
    path.write_bytes(content)
    return content


# ---------------------------------------------------------------------------
# PDF extraction (heuristic sectioning)
# ---------------------------------------------------------------------------

def extract_pdf_text(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            logger.exception("Failed to extract text from a PDF page - skipping that page")
    return "\n".join(pages)


# A line "looks like a heading" if it's short, has no trailing sentence
# punctuation, and isn't just prose. Deliberately permissive - false positives
# (treating a normal short line as a heading) just create an extra section
# boundary, which is harmless; false negatives (missing a real heading) are
# worse since it merges two topics into one section.
_HEADING_RE = re.compile(
    r"^(chapter\s+\d+|глава\s+\d+|поглавје\s+\d+|\d+(\.\d+)*[.)]?\s+[A-ZА-Ш].{2,80}|[A-ZА-Ш][\w\s,'\-/]{2,80})$",
    re.IGNORECASE,
)


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if not (3 <= len(line) <= 90):
        return False
    if line.endswith((".", ",", ";", ":")):
        return False
    if len(line.split()) > 12:
        return False
    return bool(_HEADING_RE.match(line))


def split_pdf_text_into_sections(text: str, min_section_chars: int = 150) -> List[Section]:
    lines = text.split("\n")
    sections: List[Section] = []
    current_heading = "Вовед"
    current_lines: List[str] = []

    for line in lines:
        if _looks_like_heading(line):
            if current_lines:
                sections.append(Section(current_heading, "\n".join(current_lines).strip()))
            current_heading = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(Section(current_heading, "\n".join(current_lines).strip()))

    # Drop near-empty stub sections (a heading immediately followed by another
    # heading, or by almost nothing) - these are usually false-positive
    # heading detections, not real content sections.
    return [s for s in sections if len(s.text) >= min_section_chars]


# ---------------------------------------------------------------------------
# HTML extraction (structural sectioning via real heading tags)
# ---------------------------------------------------------------------------

_CONTENT_TAGS = ("p", "li", "pre", "code", "td", "blockquote")


def split_html_into_sections(html_bytes: bytes) -> List[Section]:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    heading_tags = soup.find_all(["h1", "h2", "h3", "h4"])
    if not heading_tags:
        body_text = soup.get_text(separator="\n", strip=True)
        return [Section("Цела страница", body_text)] if body_text else []

    heading_set = set(id(t) for t in heading_tags)
    sections: List[Section] = []
    for i, tag in enumerate(heading_tags):
        heading = tag.get_text(strip=True)
        content_parts = []
        for sib in tag.find_all_next():
            if id(sib) in heading_set and sib is not tag:
                break
            if sib.name in _CONTENT_TAGS:
                text = sib.get_text(" ", strip=True)
                if text:
                    content_parts.append(text)
        text = "\n".join(content_parts)
        if text:
            sections.append(Section(heading, text))
    return sections


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_sections(url: str, cache_dir: Path) -> List[Section]:
    """Fetches (or reads from cache) the given source URL and splits it into
    Sections. Raises on network failure or if `url` is falsy (local-file
    source, not supported by this module - see module docstring)."""
    if not url:
        raise ValueError("source has no url (local-file source - not handled by source_text.py yet)")

    raw = get_or_fetch_raw(url, cache_dir)
    if _is_pdf_url(url):
        text = extract_pdf_text(raw)
        return split_pdf_text_into_sections(text)
    return split_html_into_sections(raw)


def extract_sections_multi(urls: List[str], cache_dir: Path) -> List[Section]:
    """Fetches+extracts multiple URLs (see source_discovery.py -
    most real textbooks are one page per chapter, not one page total) and
    combines their Sections into a single list. One page's fetch/parse
    failure is logged and skipped, not fatal to the whole course - a
    half-successful multi-page source is still far better than none."""
    all_sections: List[Section] = []
    for url in urls:
        try:
            all_sections.extend(extract_sections(url, cache_dir))
        except Exception:
            logger.exception("Failed to extract %s - skipping this page", url)
    return all_sections
