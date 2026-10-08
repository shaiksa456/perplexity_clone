# Ask — a Perplexity-style research assistant (Flask + RAG)

A self-hosted answer engine: type a question, it searches the live web,
scrapes and reads the top results, retrieves the most relevant passages,
and asks an LLM to write a cited answer — inline `[1][2]` markers linking
straight to sources, plus suggested follow-ups, in a threaded UI.

## How it works (RAG pipeline)

```
your question
   │
   ▼
1. web_search()        → Tavily or Serper API: top N results (title, url, snippet)
   │
   ▼
2. fetch_clean_text()  → scrape each URL in parallel, strip nav/ads/scripts,
   │                      fall back to the search snippet if a page fails
   ▼
3. chunk_text()        → split each page into overlapping ~800-word chunks
   │
   ▼
4. retrieve_top_chunks → TF-IDF cosine similarity ranks chunks against the
   │                      question, keeps the most relevant ~10
   ▼
5. generate_answer()   → Claude or GPT writes a Markdown answer using ONLY
   │                      the retrieved chunks, with [n] citation markers
   ▼
6. frontend renders answer + source cards + clickable citations + follow-ups
```

Conversation history (last 6 turns) is included in the prompt so follow-up
questions ("what about in Europe?") work naturally.

## 1. Install

```bash
cd perplexity_clone
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in **one LLM provider** and **one search provider**:

- **LLM** — pick one:
  - Anthropic: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...` (console.anthropic.com)
  - OpenAI: `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...` (platform.openai.com)
- **Search** — pick one:
  - Tavily (built for RAG, generous free tier): `SEARCH_PROVIDER=tavily`, `TAVILY_API_KEY=...` (tavily.com)
  - Serper (Google results via API): `SEARCH_PROVIDER=serper`, `SERPER_API_KEY=...` (serper.dev)

## 3. Run

```bash
python app.py
```

Open **http://localhost:5000**.

## Project layout

```
perplexity_clone/
├── app.py                 Flask routes + in-memory conversation threads
├── rag/
│   ├── search.py           Web search (Tavily / Serper)
│   ├── scraper.py          Fetches & cleans page text
│   ├── retrieval.py        Chunking + TF-IDF retrieval
│   ├── llm.py               Prompting + generation (Anthropic / OpenAI)
│   └── pipeline.py         Wires the above into one run_query() call
├── templates/index.html
├── static/css/style.css
├── static/js/app.js
├── requirements.txt
└── .env.example
```

## Notes, limits, and where to extend

- **Retrieval** uses TF-IDF rather than a hosted embedding model, so there's
  no extra API key or cost for retrieval itself — it's re-ranking a few
  dozen freshly-scraped chunks per query, not searching a large corpus.
  Swap in `OPENAI_EMBED_MODEL` + a vector similarity step in
  `rag/retrieval.py` if you want semantic (not just lexical) matching.
- **Threads** are stored in an in-memory Python dict (`app.py: THREADS`),
  which resets when the server restarts and doesn't scale past one
  process. Swap in Redis or a database for multi-user/production use.
- **Scraping** respects nothing beyond a normal `requests.get` — for a
  production tool, add robots.txt checks and rate limiting per domain.
- **Cost**: every question makes 1 search call, up to `MAX_SOURCES` page
  fetches (free), and 1 LLM call. Tune `MAX_SOURCES` and
  `CHUNKS_PER_ANSWER` in `.env` to trade quality for latency/cost.
- No data is sent anywhere except the search API, the pages you scrape,
  and your chosen LLM provider.
