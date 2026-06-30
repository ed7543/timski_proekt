from typing import List, Optional

import httpx

from backend.models.searchResult import SearchResult
from config import TAVILY_API_KEY


async def web_search(query: str, num_results: int = 5) -> List[SearchResult]:
    """Search the web using Tavily Search API for up-to-date documentation."""
    if not TAVILY_API_KEY:
        return []

    async with httpx.AsyncClient(timeout=10) as client:
        # Tavily API endpoint (corrected)
        resp = await client.post(
            "https://api.tavily.com/search",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
            }
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
            ))
        return results


def build_search_query(user_message: str, subject: Optional[str]) -> str:
    """Build a targeted search query from user message + subject context."""
    if subject:
        return f"{subject} {user_message} documentation tutorial"
    return f"{user_message} documentation"


def format_search_context(results: List[SearchResult]) -> str:
    """Format search results into a clean context block for the AI."""
    if not results:
        return ""
    lines = ["## Relevant Documentation & Resources (from live web search)\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"**[{i}] {r.title}**")
        lines.append(f"URL: {r.url}")
        lines.append(f"{r.snippet}\n")
    return "\n".join(lines)

async def explore_search(queries: List[str], num_results: int = 3) -> List[SearchResult]:
    """Run several search queries and return a deduplicated, flattened result list."""
    seen_urls = set()
    all_results: List[SearchResult] = []

    for q in queries:
        results = await web_search(q, num_results=num_results)
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)

    return all_results