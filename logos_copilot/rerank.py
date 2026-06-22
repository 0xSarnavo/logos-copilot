"""Pluggable reranker over the fused candidates — the 2nd-biggest retrieval-quality lever.

Default `LexicalReranker` ($0, deps-free): re-scores by query-term coverage across content AND the
file path / identifiers, with a path-match bonus that BM25-on-content alone misses (so the main
`node-upload.ts` beats `data.spec.ts` for an "upload" query). Swap to a cross-encoder via
RERANKER=voyage for semantic reranking. No re-ingest required.
"""
from __future__ import annotations

import os
import re

_WORD = re.compile(r"[A-Za-z0-9_]+")


def _tokens(s: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(s or "") if len(t) > 2]


class LexicalReranker:
    def rerank(self, query: str, candidates: list[dict], top_k: int | None = None) -> list[dict]:
        qset = set(_tokens(query))
        if not qset or not candidates:
            return candidates[:top_k] if top_k else candidates
        scored = []
        for i, r in enumerate(candidates):
            content = r.get("content", "")
            ctoks = _tokens(content)
            cset = set(ctoks)
            path = (r.get("file_path") or "").replace("-", " ").replace("/", " ").replace(".", " ")
            pset = set(_tokens(path))
            cov = len(qset & cset)                         # distinct query terms present in content
            path_hit = len(qset & pset)                    # query terms in the file path (strong signal)
            tf = sum(ctoks.count(t) for t in qset)         # term frequency (capped)
            score = cov * 2 + path_hit * 3 + min(tf, 10) * 0.2
            scored.append((score, -i, r))                  # -i = keep RRF order as a stable tiebreak
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out = [r for _, _, r in scored]
        return out[:top_k] if top_k else out


class VoyageReranker:
    def __init__(self, model: str = "rerank-2"):
        import voyageai

        self._c = voyageai.Client()
        self.model = model

    def rerank(self, query: str, candidates: list[dict], top_k: int | None = None) -> list[dict]:
        if not candidates:
            return candidates
        docs = [c.get("content", "")[:2000] for c in candidates]
        res = self._c.rerank(query, docs, model=self.model, top_k=top_k or len(candidates))
        return [candidates[r.index] for r in res.results]


def get_reranker():
    mode = os.environ.get("RERANKER", "lexical").lower()
    if mode == "none":
        return None
    if mode == "voyage":
        try:
            return VoyageReranker(os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2"))
        except Exception:
            return LexicalReranker()
    return LexicalReranker()
