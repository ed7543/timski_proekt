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
податоци) are handled separately by extract_local_files_sections() below -
NOT via extract_sections()/extract_sections_multi(), which still raise
ValueError for a falsy url (a genuinely-missing source, not a local-file
one, should still fail loudly rather than silently do nothing).

Fetched raw bytes are cached to disk (keyed by URL hash) so re-running a batch
after a crash, or re-running with a different confidence threshold, doesn't
re-download anything.
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

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
    # NOT stripping "header": modern semantic HTML very often wraps a page's
    # actual <h1> in <article><header><h1>...</h1></header> (learncpp.com
    # does this on every lesson page) - decomposing header along with real
    # site-chrome tags destroyed that h1 before find_all(["h1".."h4"]) below
    # ever saw it, so every learncpp page fell back to one "Цела страница"
    # section (whole-page text, no real heading) instead of its real,
    # specific heading. Confirmed by inspecting learncpp.com's actual cached
    # HTML (h1 is nested in article > div > header > h1). footer is still
    # stripped - it doesn't wrap headings and is usually just boilerplate.
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
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


# ---------------------------------------------------------------------------
# Local-file sources (LOCAL_FILE_ONLY_CODES - user-supplied lecture materials,
# no URL at all)
# ---------------------------------------------------------------------------

def extract_docx_text(raw: bytes) -> str:
    """Plain paragraph + table text via python-docx. Does NOT do OCR on
    embedded images - if a .docx is really slides pasted in as screenshots
    (some of these lecture files are multi-MB, which is a hint that might be
    happening), the text pulled out here will be thin even though the file
    itself is large. That's a real limitation, not a bug - worth checking the
    per-file word counts in the run report before assuming a course's local
    files are fully usable."""
    from docx import Document

    doc = Document(io.BytesIO(raw))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)
    return "\n".join(parts)


_LOCAL_FILE_EXTS = (".docx", ".pdf")
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[.)]?\s*")


def _clean_local_heading(stem: str) -> str:
    """"1. Информациска архитектура" -> "Информациска архитектура". Falls
    back to the raw stem if stripping the leading number leaves nothing."""
    cleaned = _LEADING_NUMBER_RE.sub("", stem).strip()
    return cleaned or stem


def extract_local_files_sections(course_code: str, base_dir: Path) -> List[Section]:
    """Local-file courses - the user drops files into <base_dir>/<course_code>/.
    Two usage patterns have been seen in practice, handled differently:

      1. One file per topic (e.g. "3. Шаблони и примери.docx") - each file
         already IS one topic, so the filename (minus a leading number)
         becomes the section heading directly, and the whole file's text
         becomes that section's body. No heading detection needed inside the
         file. This also sidesteps the MK/EN translation-matching problem
         entirely for these courses, since both the lesson titles and these
         filenames are already Macedonian.
      2. One big consolidated "skripta" PDF covering the whole course (e.g.
         an 8MB "NAJDOBRA SKRIPTA (RECOMMEND IT).pdf") - here the filename
         says nothing about individual topics, so for PDFs specifically this
         also tries the heading-heuristic sectioning used for fetched PDFs
         (split_pdf_text_into_sections) and uses that instead whenever it
         finds real internal structure. See the PDF branch below.

    .docx files are always treated as pattern 1 (single section, filename
    heading) - python-docx has no equivalent heading-heuristic splitter here,
    and in practice every .docx uploaded so far has been one-topic-per-file.

    Returns [] if the folder doesn't exist or has no supported files - the
    caller (seed_lessons.py) treats that the same as "no local files
    provided yet" and falls back to the old skip-with-a-note behaviour, so
    this is safe to call even for a course whose files haven't been dropped
    in yet.

    When a topic exists as both "<stem>.docx" and "<stem>.pdf" (seen in
    practice for a few topics), the .docx is preferred and the .pdf sibling
    is skipped - python-docx reads real text runs directly and isn't subject
    to the pypdf font-cmap decoding bug seen elsewhere in this pipeline. This
    is an exact-stem match only; a couple of files in practice have slightly
    inconsistent naming between their .docx/.pdf versions (e.g. "9 NLP.docx"
    vs "9. NLP.pdf") and won't be deduped - both get included as separate
    sections, which just means mildly redundant (not wrong) content for that
    one topic.
    """
    folder = base_dir / course_code
    if not folder.is_dir():
        return []

    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in _LOCAL_FILE_EXTS)

    by_stem: Dict[str, Path] = {}
    for p in files:
        existing = by_stem.get(p.stem)
        if existing is None or (existing.suffix.lower() == ".pdf" and p.suffix.lower() == ".docx"):
            by_stem[p.stem] = p

    sections: List[Section] = []
    for path in sorted(by_stem.values(), key=lambda p: p.name):
        is_pdf = path.suffix.lower() == ".pdf"
        try:
            raw = path.read_bytes()
            text = extract_pdf_text(raw) if is_pdf else extract_docx_text(raw)
        except Exception:
            logger.exception("Failed to extract local file %s - skipping", path)
            continue
        text = text.strip()
        if not text:
            logger.warning("Local file %s extracted to empty text - skipping", path)
            continue

        if is_pdf:
            # A PDF can be either "one topic, one file" (same as the .docx case
            # below) or a whole-course consolidated "skripta" covering many
            # topics in a single big file (seen in practice - e.g. an 8MB PDF
            # named "NAJDOBRA SKRIPTA (RECOMMEND IT)" that was meant to cover
            # an entire operating-systems course). Treating the latter as one
            # giant section makes every lesson in the course match against the
            # same undifferentiated blob (matcher just latches onto whichever
            # lesson titles share a stray word with the filename). Try the
            # same heading-heuristic sectioning already used for fetched PDFs
            # - if it actually finds real internal structure (>1 section),
            # use those instead of the whole-file blob. A genuinely
            # single-topic PDF has no such structure and split_pdf_text_into_sections
            # collapses back to <=1 section, so it falls through to the normal
            # whole-file-as-one-section path below, same as it always has.
            sub_sections = split_pdf_text_into_sections(text)
            if len(sub_sections) > 1:
                sections.extend(sub_sections)
                continue

        sections.append(Section(_clean_local_heading(path.stem), text))
    return sections
