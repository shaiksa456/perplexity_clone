"""
Fetches a URL and extracts readable article text, stripping nav/ads/scripts.
Deliberately defensive: any single page failing (timeout, 403, non-HTML)
must never take down the whole answer — the pipeline just falls back to
the search-engine snippet for that source.
"""
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

UNWANTED_TAGS = [
    "script", "style", "nav", "footer", "header", "aside", "form",
    "iframe", "noscript", "svg", "button", "input",
]


def fetch_clean_text(url: str, timeout: int = 8, max_chars: int = 12000) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(UNWANTED_TAGS):
            tag.decompose()

        # Prefer <article>, then <main>, then whole body
        container = soup.find("article") or soup.find("main") or soup.body
        if container is None:
            return None

        text = container.get_text(separator="\n")
        text = re.sub(r"\n{2,}", "\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()

        if len(text) < 200:
            return None

        return text[:max_chars]
    except Exception:
        return None
