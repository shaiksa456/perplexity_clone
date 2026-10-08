"""
Orchestrates the full pipeline for one query:

    query -> web_search -> parallel scrape -> chunk -> TF-IDF retrieve
          -> LLM generate (with inline [n] citations) -> structured result
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .search import web_search, SearchError
from .scraper import fetch_clean_text
from .retrieval import chunk_text, retrieve_top_chunks
from .llm import generate_answer


def run_query(question: str, history: list[dict]) -> dict:
    t0 = time.time()
    max_sources = int(os.getenv("MAX_SOURCES", "8"))
    k_chunks = int(os.getenv("CHUNKS_PER_ANSWER", "10"))

    # 1. Web search
    try:
        results = web_search(question, max_results=max_sources)
    except SearchError as e:
        return {"error": str(e)}

    if not results:
        return {"error": "No search results found for that query."}

    # 2. Scrape pages in parallel, fall back to the search snippet on failure
    def fetch_one(idx_result):
        idx, r = idx_result
        text = fetch_clean_text(r["url"])
        return idx, text

    scraped = {i: None for i in range(len(results))}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_one, item) for item in enumerate(results)]
        for f in as_completed(futures):
            idx, text = f.result()
            scraped[idx] = text

    # 3. Chunk each source's content (full page text if we got it, else snippet)
    all_chunks = []
    for i, r in enumerate(results):
        body = scraped.get(i) or r.get("snippet", "")
        all_chunks.extend(chunk_text(body, source_index=i))

    # 4. Retrieve the most relevant chunks across all sources
    top_chunks = retrieve_top_chunks(question, all_chunks, k=k_chunks)

    # Guarantee every source appears at least once if it has any chunk,
    # so the model can cite broadly rather than fixating on one page.
    seen_sources = {c.source_index for c in top_chunks}
    for i in range(len(results)):
        if i not in seen_sources:
            src_chunks = [c for c in all_chunks if c.source_index == i]
            if src_chunks:
                top_chunks.append(src_chunks[0])

    chunks_with_sources = [
        {
            "title": results[c.source_index]["title"],
            "url": results[c.source_index]["url"],
            "text": c.text,
        }
        for c in top_chunks
    ]

    # 5. Generate the answer
    try:
        raw_answer = generate_answer(question, chunks_with_sources, history)
    except Exception as e:
        return {"error": f"LLM generation failed: {e}"}

    answer_markdown, followups = _split_followups(raw_answer)

    sources = [
        {
            "n": i + 1,
            "title": r["title"],
            "url": r["url"],
            "domain": _domain(r["url"]),
            "snippet": (scraped.get(i) or r.get("snippet", ""))[:220],
        }
        for i, r in enumerate(results)
    ]

    return {
        "answer_markdown": answer_markdown,
        "answer_plain": re.sub(r"\[\d+\]", "", answer_markdown)[:1200],
        "sources": sources,
        "followups": followups,
        "elapsed_seconds": round(time.time() - t0, 2),
    }


def _split_followups(raw: str) -> tuple[str, list[str]]:
    marker = "FOLLOWUPS:"
    if marker in raw:
        answer, tail = raw.split(marker, 1)
        followups = [q.strip() for q in tail.split("|") if q.strip()]
        return answer.strip(), followups[:3]
    return raw.strip(), []


def _domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)/?", url or "")
    if not m:
        return url or ""
    d = m.group(1)
    return d[4:] if d.startswith("www.") else d
