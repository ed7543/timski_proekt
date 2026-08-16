"""Polite HTTP client for ingesting public data from the finki-hub.com community
project (github.com/finki-hub) - specifically the static/raw endpoints backing
predmeti.finki-hub.com and snimki.finki-hub.com. This is someone else's
community-run infrastructure, not a load target, so every request:

  - identifies itself with a real User-Agent (project + contact),
  - is rate-limited with a small delay,
  - has a sane timeout.

Not used by any live API request path - this only runs from the standalone
`python -m backend.services.ingestion.cli` entrypoint.
"""
import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "LearnWiseIngestionBot/0.1 "
    "(+https://github.com/ed7543/timski_proekt; contact: eva.dimitrova@thedatavision.com)"
)

# Minimum delay between outgoing requests, to stay a well-behaved client.
DEFAULT_DELAY_SECONDS = 1.5


class FinkiHubClient:
    """Thin async HTTP wrapper: custom UA, per-request delay, timeout."""

    def __init__(self, delay_seconds: float = DEFAULT_DELAY_SECONDS, timeout: float = 20.0):
        self.delay_seconds = delay_seconds
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._robots_checked: set[str] = set()

    async def __aenter__(self) -> "FinkiHubClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

    async def check_robots(self, base_url: str) -> None:
        """Best-effort robots.txt check, logged once per host. This is advisory:
        both predmeti.finki-hub.com and snimki.finki-hub.com are client-rendered
        sites with no robots.txt of their own (requests fall through to their SPA
        shell / VitePress 404 page), and we don't actually scrape their rendered
        HTML - we instead pull the same public static assets/raw markdown that
        those sites themselves are built from. Still logged here so a real
        Disallow shows up if the target ever adds one."""
        host = base_url.split("//", 1)[-1].split("/", 1)[0]
        if host in self._robots_checked:
            return
        self._robots_checked.add(host)
        robots_url = f"https://{host}/robots.txt"
        try:
            resp = await self._client.get(robots_url)
            if resp.status_code == 200 and "disallow" in resp.text.lower():
                logger.info("robots.txt found for %s - review before broad scraping:\n%s", host, resp.text[:500])
            else:
                logger.info("No enforceable robots.txt rules found for %s (status %s)", host, resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Could not fetch robots.txt for %s: %s", host, exc)
        await self._throttle()

    async def get_text(self, url: str) -> Optional[str]:
        await self._throttle()
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("GET %s failed: %s", url, exc)
            return None
        if resp.status_code != 200:
            logger.warning("GET %s -> HTTP %s", url, resp.status_code)
            return None
        return resp.text

    async def get_json(self, url: str) -> Optional[Any]:
        await self._throttle()
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("GET %s failed: %s", url, exc)
            return None
        if resp.status_code != 200:
            logger.warning("GET %s -> HTTP %s", url, resp.status_code)
            return None
        return resp.json()
