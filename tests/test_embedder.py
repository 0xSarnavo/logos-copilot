import math

from logos_copilot.embedder import HashEmbedder


def test_hash_embedder_dim_and_determinism():
    e = HashEmbedder(dim=64)
    a = e.embed_query("logos blockchain cryptarchia")
    b = e.embed_query("logos blockchain cryptarchia")
    assert len(a) == 64
    assert a == b


def test_hash_embedder_normalized():
    e = HashEmbedder(dim=64)
    v = e.embed_documents(["alpha beta gamma"])[0]
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6


def test_empty_text_safe():
    e = HashEmbedder(dim=16)
    v = e.embed_query("")
    assert len(v) == 16 and all(x == 0.0 for x in v)
