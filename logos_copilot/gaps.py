"""Gap detection: turn weak-coverage signals into ingestion candidates (closes the evolve loop).

Down-voted queries that STILL return weak coverage are treated as missing-knowledge signals — to be
ingested, not prompt-tuned (the 2025-26 Corrective-RAG guidance).
"""
from __future__ import annotations

from .feedback import feedback_stats
from .retrieve import search


def detect_gaps(conn, weak_threshold: int = 3, top_k: int = 8) -> dict:
    # Down-votes are the explicit signal; annotate each with current coverage so under-covered ones
    # (likely missing-knowledge) sort to the top as ingestion candidates.
    # NOTE: `results` is a coarse COUNT proxy (hybrid search returns ~top_k whenever any chunk
    # matches), so `under_covered` mainly fires on near-empty corpora. A score-floor relevance
    # signal (Phase-5+ with managed embeddings) would sharpen this; tune weak_threshold to top_k.
    stats = feedback_stats(conn)
    gaps = []
    for g in stats["top_negative_queries"]:
        n = len(search(g["query"], top_k=top_k))
        gaps.append({"query": g["query"], "down_votes": g["c"], "results": n,
                     "under_covered": n < weak_threshold})
    gaps.sort(key=lambda x: (not x["under_covered"], -x["down_votes"]))
    from .querylog import low_coverage_queries
    return {"feedback": {"up": stats["up"], "down": stats["down"]},
            "candidate_gaps": gaps,
            "low_coverage_from_logs": low_coverage_queries(conn, max_results=weak_threshold - 1)}
