"""Finds the real content-page URLs for a course's source book, via Gemini's
`google_search` grounding tool - fixes sources whose stored URL
(courses_db.json's source.url) points to a catalog/marketing page instead of
actual readable content. Confirmed for OpenStax:
openstax.org/details/books/X is a JS-only catalog page with no text at all;
the real chapters live at openstax.org/books/X/pages/... - one URL per
chapter, dozens per book. Most non-single-page sources in this pipeline have
the same shape.

Deliberately does NOT combine `google_search` with the `url_context` tool in
the same call - that combination has a known unresolved bug where
url_context can't follow the redirect-style URLs google_search grounding
returns (googleapis/python-genai#1322, still open as of this writing).
Also deliberately does NOT combine `google_search` with response_schema/JSON
mode - that combination is only documented for the newer Interactions API
(client.interactions.create), not the client.models.generate_content() path
this whole project is built on. So: plain-text output (one URL per line),
parsed with a regex - simpler, stays on the already-tested code path.

Gemini only *finds* URLs here - it never reads or summarizes their content
itself. The actual fetching is done by source_text.py's plain httpx fetch
(same as before this module existed), so the "documentation is only ever
written from text we actually fetched" guarantee stays intact.
"""
import logging
import re
from textwrap import dedent
from typing import List
from urllib.parse import urlparse

from google.genai import types

from backend.services.ingestion.gemini_generator import GEMINI_MODEL, _get_client

logger = logging.getLogger(__name__)

MAX_DISCOVERED_PAGES = 30

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def _domain(url: str) -> str:
    return urlparse(url).netloc


def build_discovery_prompt(source_title: str, source_author: str, source_url: str, domain: str) -> str:
    return dedent(f"""
        Пребарувај на интернет за да ги најдеш точните URL-адреси на СИТЕ
        поглавја/страници со вистинска содржина (текст на книгата, не
        каталог) од книгата "{source_title}" од {source_author}, достапна
        на веб-сајтот {domain}.

        Познат почетен линк: {source_url}

        ПРАВИЛА:
        - Секоја URL мора да биде под доменот {domain}.
        - Само страници со вистинска содржина на книгата (поглавја,
          секции) - НЕ каталошки/маркетинг/пребарувачки страници.
        - Ако не најдеш ништо подобро од почетниот линк, наведи само него.
        - Најмногу {MAX_DISCOVERED_PAGES} URL-адреси.

        Врати ги URL-адресите, ЕДНА ПО РЕД, без нумерирање, без markdown
        форматирање, без дополнителен текст пред/по нив - само чисти
        URL-адреси, по едно на линија.
    """).strip()


def discover_content_pages(source_title: str, source_author: str, source_url: str) -> List[str]:
    """Returns a list of URLs (same domain as source_url) that Gemini's
    search found as likely containing the book's actual content. Always
    includes source_url itself (never returns empty for a course that has a
    URL at all - falls back to just that URL on any failure or empty
    discovery, so callers can proceed with at least what they already had)."""
    domain = _domain(source_url)
    client = _get_client()
    prompt = build_discovery_prompt(source_title, source_author, source_url, domain)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
        text = response.text or ""
    except Exception:
        logger.exception(
            "Content-page discovery failed for %r - falling back to just source_url", source_title
        )
        return [source_url]

    found = _URL_RE.findall(text)
    same_domain = [u.rstrip(".,)") for u in found if _domain(u) == domain]
    unique = list(dict.fromkeys(same_domain))  # de-dupe, preserve order

    if not unique:
        logger.warning("Discovery found no same-domain URLs for %r - falling back to source_url", source_title)
        return [source_url]

    if source_url not in unique:
        unique.insert(0, source_url)

    return unique[:MAX_DISCOVERED_PAGES]
