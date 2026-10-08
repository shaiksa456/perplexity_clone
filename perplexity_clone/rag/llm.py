"""
LLM abstraction. Supports Anthropic (Claude), OpenAI, and Gemini, selected
via LLM_PROVIDER in .env. All paths build the same citation-grounded prompt
so answers behave identically regardless of provider.
"""
import os

SYSTEM_PROMPT = """You are a precise research assistant that answers questions \
using ONLY the numbered source excerpts provided to you. Behave like an \
answer engine (in the style of Perplexity):

- Write a clear, well-organized answer in your own words. Use short \
paragraphs, and Markdown (headers, bold, bullet lists, tables) where it \
genuinely helps readability.
- Every factual claim must be followed by a citation marker like [1] or \
[1][3] referencing the source excerpt(s) it came from. Cite the minimum \
set of sources needed.
- If the excerpts disagree, say so and cite both sides.
- If the excerpts don't contain enough information to answer fully, say \
plainly what is missing rather than guessing.
- Never invent a source or a citation number that wasn't given to you.
- Do not include a "References" or "Sources" section yourself — the \
application renders that separately from the citation markers.
- After the answer, on a new line starting with "FOLLOWUPS:", give 3 short \
suggested follow-up questions the user might ask next, separated by " | ". \
Do not number them.
"""


def _build_user_prompt(question: str, chunks_with_sources: list[dict], history: list[dict]) -> str:
    context_blocks = []
    for i, item in enumerate(chunks_with_sources, start=1):
        context_blocks.append(
            f"[{i}] Source: {item['title']} ({item['url']})\n{item['text']}"
        )
    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no sources retrieved)"

    convo = ""
    if history:
        turns = []
        for turn in history[-6:]:
            turns.append(f"User: {turn['question']}\nAssistant: {turn['answer_plain']}")
        convo = "Previous conversation (for context only, do not re-cite):\n" + "\n\n".join(turns) + "\n\n"

    return (
        f"{convo}"
        f"Numbered source excerpts:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer the question using the numbered excerpts above, with inline citation markers."
    )


def generate_answer(question: str, chunks_with_sources: list[dict], history: list[dict]) -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    user_prompt = _build_user_prompt(question, chunks_with_sources, history)

    if provider == "anthropic":
        return _generate_anthropic(user_prompt)
    elif provider == "openai":
        return _generate_openai(user_prompt)
    elif provider == "gemini":
        return _generate_gemini(user_prompt)
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")


def _generate_anthropic(user_prompt: str) -> str:
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in your .env file")

    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def _generate_openai(user_prompt: str) -> str:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in your .env file")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    resp = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def _generate_gemini(user_prompt: str) -> str:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in your .env file")

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT)

    resp = model.generate_content(user_prompt)
    return resp.text