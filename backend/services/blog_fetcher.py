"""Scrapes just enough metadata from a pasted article URL to create a
BlogPost row (see routes/blogRoute.py) - a title, a short excerpt, an image,
and the source site's display name.

No AI involved and no article content is stored beyond that short metadata:
the full piece always stays on its original site, and every card the Blog
page renders links back to and credits that source. This mirrors, in spirit,
the "always disclose where content really comes from" rule already used for
--force-general-knowledge / --generate-without-source lessons - here the
content itself never leaves the source page at all, we just index it.

Runs synchronously (blocking) on purpose - this is a thin wrapper over
requests-style I/O and BeautifulSoup parsing (sync-only), and it's shared
verbatim between the admin route (routes/blogRoute.py, which offloads it to
a thread via starlette's run_in_threadpool so it doesn't block the event
loop) and the scheduled sync script (scripts/fetch_finki_announcements.py,
which is a plain sync CLI). Keeping one sync implementation avoids
duplicating the SSRF/redirect-validation logic below across a sync and an
async copy that could drift apart.
"""
import ipaddress
import logging
import re
import socket
from urllib.parse import urljoin, urlparse

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
# Matches BlogPost.title's column width (database/models.py) - a scraped
# <title>/og:title can be arbitrarily long (or a hostile page can pad it on
# purpose), and without this cap that insert fails with a raw DB error
# instead of the friendly BlogFetchError the route/script already handle.
TITLE_MAX_LEN = 500
# Redirects are followed manually (one hop at a time, see
# _resolve_and_validate below) rather than via httpx's follow_redirects=True,
# specifically so every hop - not just the URL the admin pasted - gets the
# same private/internal-IP check. A real article rarely needs more than one
# or two hops; this is a generous ceiling against redirect loops.
MAX_REDIRECTS = 5


class BlogFetchError(Exception):
    """Raised whenever a pasted URL can't be turned into a usable blog card
    (unreachable, not HTML, not publicly fetchable, or has no discoverable
    title) - the route turns this into a 422 with the message shown
    directly to the admin, and the sync script logs it and skips that URL."""


def _reject(reason: str) -> None:
    raise BlogFetchError(reason)


def _assert_public_address(hostname: str, url: str) -> None:
    """Resolves `hostname` and rejects it if any of its addresses are
    loopback/private/link-local/reserved/multicast - i.e. not a normal
    public website. This is what stops the admin "paste a URL" endpoint (or
    the scheduled sync script) from being used as an SSRF vector to reach
    internal services or cloud metadata endpoints (e.g. the AWS/GCP
    169.254.169.254 metadata IP, which Python's ipaddress module already
    classifies as link-local/private)."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise BlogFetchError(f"Не можам да го разрешам домејнот: {hostname}") from exc

    if not infos:
        _reject(f"Не можам да го разрешам домејнот: {hostname}")

    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            logger.warning("Blocked blog-fetch SSRF attempt: %s resolved %s -> %s", url, hostname, ip)
            _reject("Овој линк не е дозволен (внатрешна/приватна адреса).")


def _validate_hop(url: str) -> str:
    """Validates one URL (the original link, or one redirect hop) before
    it's fetched: only plain http(s), with a hostname that resolves to a
    public address. Returns the normalized url on success."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        _reject("Дозволени се само http/https линкови.")
    if not parsed.hostname:
        _reject("Невалиден линк.")
    _assert_public_address(parsed.hostname, url)
    return url


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


def _fetch_html(client: httpx.Client, url: str) -> httpx.Response:
    """GETs `url`, following redirects one hop at a time so
    _validate_hop() gets a chance to block any hop that resolves to a
    private/internal address - not just the URL the caller passed in."""
    current_url = _validate_hop(url)
    for _ in range(MAX_REDIRECTS + 1):
        resp = client.get(current_url)
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                break
            current_url = _validate_hop(urljoin(current_url, location))
            continue
        resp.raise_for_status()
        return resp
    raise BlogFetchError("Премногу пренасочувања (redirects).")


def fetch_article_metadata(url: str) -> dict:
    """Fetches `url` and pulls {title, excerpt, image_url, source_name} out
    of its own <title>/meta tags. Raises BlogFetchError on anything that
    stops us building a usable card (network failure, non-HTML response, a
    page with no title at all, or a URL/redirect that resolves to a
    private/internal address)."""
    try:
        with httpx.Client(
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        ) as client:
            resp = _fetch_html(client, url)
    except BlogFetchError:
        raise
    except httpx.HTTPError as exc:
        raise BlogFetchError(f"Не успеав да ја отворам страницата: {exc}") from exc

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise BlogFetchError("Линкот не води води во веб-страница (не е HTML).")

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        title = _meta(soup, "og:title", "twitter:title")
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        if not title:
            raise BlogFetchError("Не најдов наслов на страницата.")
        if len(title) > TITLE_MAX_LEN:
            title = title[: TITLE_MAX_LEN - 1].rsplit(" ", 1)[0] + "…"

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
    except BlogFetchError:
        raise
    except Exception as exc:
        # Anything else here (a malformed page tripping up BeautifulSoup, a
        # decoding error, etc.) must not propagate raw: the admin route
        # would 500 instead of a clean 422, and the scheduled sync script
        # (scripts/fetch_finki_announcements.py) only catches BlogFetchError
        # - an unhandled exception there kills the whole run, skipping every
        # source after the one that failed.
        logger.exception("Unexpected error parsing article metadata for %s", url)
        raise BlogFetchError("Не успеав да ја обработам страницата.") from exc
