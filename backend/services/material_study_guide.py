"""Text extraction for Marketplace study guides - the equivalent of the
curated-textbook flow in services/ingestion/source_text.py, but for a single
arbitrary material URL (a user-submitted PDF/link) instead of a matched
textbook section. Reuses source_text's disk-cached fetch + PDF extraction
directly rather than duplicating them; HTML goes through a simple direct
BeautifulSoup(...).get_text() call instead of the more elaborate
heading-based split_html_into_sections() (which exists for curated
textbook topic-matching - unnecessary for a single ad-hoc material)."""
from pathlib import Path

from bs4 import BeautifulSoup

from backend.services.ingestion import source_text

_CACHE_DIR = Path("backend/services/material_study_guide_cache")
MAX_EXCERPT_CHARS = 40_000
_UNSUPPORTED_CATEGORY = "video"


class UnsupportedMaterialError(Exception):
    """Raised when a material's content can't be turned into readable text
    at all (empty extraction, fetch failure) - distinct from a category
    that's rejected outright (see is_generatable_category)."""


def is_generatable_category(category: str | None) -> bool:
    """Video materials have no text to extract - a study guide can't be
    generated for them (the frontend also hides the toggle entirely for
    these, see MaterialStudyGuide.tsx, but the backend guards it too since
    the endpoint is reachable directly)."""
    return (category or "").strip().lower() != _UNSUPPORTED_CATEGORY


def _is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def extract_material_text(url: str) -> str:
    """Fetches (disk-cached) and extracts readable text from a material's own
    URL - PDF via pypdf (source_text.extract_pdf_text), anything else treated
    as HTML. Raises UnsupportedMaterialError if nothing readable comes out."""
    raw = source_text.get_or_fetch_raw(url, _CACHE_DIR)
    if _is_pdf_url(url):
        text = source_text.extract_pdf_text(raw)
    else:
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

    text = text.strip()
    if not text:
        raise UnsupportedMaterialError(
            "Couldn't extract any readable text from this material - it may be a scanned "
            "(image-only) PDF or an empty/malformed file."
        )
    return text[:MAX_EXCERPT_CHARS]
