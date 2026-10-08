"""
Chunking + retrieval, implemented in pure Python (no scikit-learn/scipy) so
there's no native binary dependency to install or get blocked by OS-level
security policies. TF-IDF + cosine similarity, computed manually.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
import math
import re


@dataclass
class Chunk:
    text: str
    source_index: int
    chunk_index: int


STOPWORDS = {
    "the","a","an","and","or","but","is","are","was","were","be","been","being",
    "to","of","in","on","at","for","with","by","from","as","that","this","these",
    "those","it","its","it's","not","no","do","does","did","can","could","will",
    "would","should","have","has","had","i","you","he","she","we","they","them",
    "his","her","their","our","your","my","what","which","who","whom","if","then",
    "so","than","too","very","just","about","into","over","after","before",
}


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def chunk_text(text: str, source_index: int, chunk_size: int = 800, overlap: int = 120) -> list[Chunk]:
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(chunk_size - overlap, 1)
    i = 0
    idx = 0
    while i < len(words):
        piece = " ".join(words[i:i + chunk_size])
        if len(piece.strip()) > 40:
            chunks.append(Chunk(text=piece, source_index=source_index, chunk_index=idx))
            idx += 1
        i += step
    return chunks


def _tfidf_vectors(docs: list[list[str]]) -> list[Counter]:
    df = Counter()
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1

    n_docs = len(docs)
    vectors = []
    for tokens in docs:
        tf = Counter(tokens)
        vec = Counter()
        for term, count in tf.items():
            idf = math.log((n_docs + 1) / (df[term] + 1)) + 1
            vec[term] = count * idf
        vectors.append(vec)
    return vectors


def _cosine(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_top_chunks(query: str, all_chunks: list[Chunk], k: int = 10) -> list[Chunk]:
    if not all_chunks:
        return []

    docs = [_tokenize(c.text) for c in all_chunks] + [_tokenize(query)]
    vectors = _tfidf_vectors(docs)
    query_vec = vectors[-1]
    doc_vectors = vectors[:-1]

    scores = [_cosine(query_vec, v) for v in doc_vectors]
    ranked = sorted(zip(scores, all_chunks), key=lambda x: x[0], reverse=True)
    top = [c for score, c in ranked[:k] if score > 0]
    return top or all_chunks[:k]