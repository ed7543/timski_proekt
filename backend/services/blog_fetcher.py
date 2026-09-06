"""Scrapes just enough metadata from a pasted article URL to create a
BlogPost row (see routes/blogRoute.py) - a title, a short excerpt, an image,
and the source site's display name.

No AI involved and no article content is stored beyond that short metadata:
the full piece always stays on its original site, and every card the Blog
page renders links back to and credits that source. This mirrors, in spirit,
the "always disclose where content really comes from" rule already used for
--force-general-knowledge / --generate-without-source lessons - here the
content itself never leaves the source page at all, we just index it.
"""
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "LearnWiseBlogBot/0.1 "
    "(+https://github.com/ed7543/timski_proekt; educational use; every article "
    "we index links back to its original source)"
)
FETCH_TIMEOUT_SECONDS = 15.0
EXCERPT_MAX_LEN = 400


class BlogFetchError(Exception):
    """Raised whenever a pasted URL can't be turned into a usable blog card
    (unreachable, not HTML, or has no discoverable title) - the route turns
    this into a 422 with the message shown directly to the admin."""


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    """First non-empty content= value among the given <meta property=.../
    name=...> tags, checked in the given order (og: tags first - they're
    the ones sites curate specifically for link previews)."""
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            content = tag["content"].strip()
            if content:
                return content
    return None


def _fallback_excerpt(soup: BeautifulSoup) -> str | None:
    """No description meta tag at all - fall back to the first substantial
    paragraph on the page (skips short nav/cookie-banner one-liners)."""
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) >= 60:
            return text
    return None


def _site_display_name(soup: BeautifulSoup, url: str) -> str:
    og_site = _meta(soup, "og:site_name")
    if og_site:
        return og_site
    domain = urlparse(url).netloc
    return re.sub(r"^www\.", "", domain)


def fetch_article_metadata(url: str) -> dict:
    """Fetches `url` and pulls {title, excerpt, image_url, source_name} out
    of its own <title>/meta tags. Raises BlogFetchError on anything that
    stops us building a usable card (network failure, non-HTML response, or
    a page with no title at all)."""
    try:
        with httpx.Client(
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise BlogFetchError(f"Не успеав да ја отворам страницата: {exc}") from exc

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise BlogFetchError("Линкот не води до веб-страница (не е HTML).")

    soup = BeautifulSoup(resp.text, "html.parser")

    title = _meta(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    if not title:
        raise BlogFetchError("Не најдов наслов на страницата.")

    excerpt = _meta(soup, "og:description", "twitter:description", "description")
    if not excerpt:
        excerpt = _fallback_excerpt(soup)
    if excerpt and len(excerpt) > EXCERPT_MAX_LEN:
        excerpt = excerpt[: EXCERPT_MAX_LEN - 1].rsplit(" ", 1)[0] + "…"

    image_url = _meta(soup, "og:image", "twitter:image")

    return {
        "title": title,
        "excerpt": excerpt,
        "image_url": image_url,
        "source_name": _site_display_name(soup, url),
    }
