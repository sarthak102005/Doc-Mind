"""Keyword and lexical retrieval matching for hybrid search."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

from app.retrieval.schema import EvidenceChunk


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"\b\w{2,}\b", text)]


def score_bm25(query_tokens: list[str], chunk_text: str, avg_len: float = 100.0) -> float:
    """Lightweight BM25 term frequency calculation."""
    tokens = _tokenize(chunk_text)
    if not tokens:
        return 0.0

    doc_len = len(tokens)
    tf = Counter(tokens)
    k1 = 1.5
    b = 0.75
    score = 0.0

    for q in query_tokens:
        count = tf.get(q, 0)
        if count > 0:
            num = count * (k1 + 1)
            denom = count + k1 * (1 - b + b * (doc_len / avg_len))
            score += num / denom

    return score


def rank_keyword_candidates(
    query: str,
    candidates: Sequence[EvidenceChunk],
) -> list[EvidenceChunk]:
    """Score and rank an existing candidate pool using BM25 token matching."""
    query_tokens = _tokenize(query)
    if not query_tokens or not candidates:
        return list(candidates)

    avg_len = sum(len(_tokenize(c.text)) for c in candidates) / max(1, len(candidates))
    scored = []
    for c in candidates:
        s = score_bm25(query_tokens, c.text, avg_len)
        scored.append((s, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]
