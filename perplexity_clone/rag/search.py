"""
Web search layer. Abstracts over multiple search providers so the rest of the
pipeline never has to know which one is configured.

Each provider returns a list of dicts:
    {"title": str, "url": str, "snippet": str}
"""
import os
import requests


class SearchError(RuntimeError):
    pass


def web_search(query: str, max_results: int = 8) -> list[dict]:
    provider = os.getenv("SEARCH_PROVIDER", "tavily").lower()
    if provider == "tavily":
        return _search_tavily(query, max_results)
    elif provider == "serper":
        return _search_serper(query, max_results)
    else:
        raise SearchError(f"Unknown SEARCH_PROVIDER: {provider}")


def _search_tavily(query: str, max_results: int) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise SearchError("TAVILY_API_KEY is not set in your .env file")

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise SearchError(f"Tavily search failed: {e}") from e

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append({
            "title": item.get("title") or item.get("url"),
            "url": item.get("url"),
            "snippet": item.get("content", "")[:500],
        })
    return results


def _search_serper(query: str, max_results: int) -> list[dict]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise SearchError("SERPER_API_KEY is not set in your .env file")

    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise SearchError(f"Serper search failed: {e}") from e

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append({
            "title": item.get("title"),
            "url": item.get("link"),
            "snippet": item.get("snippet", ""),
        })
    return results
