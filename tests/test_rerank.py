from logos_copilot.rerank import LexicalReranker


def test_lexical_rerank_prefers_term_and_path_match():
    cands = [
        {"content": "import { assert, describe, it } from 'vitest'", "file_path": "data.spec.ts"},
        {"content": "export class NodeUploadStrategy upload data cid",
         "file_path": "src/data/node-upload.ts"},
    ]
    out = LexicalReranker().rerank("NodeUploadStrategy upload data", cands)
    assert out[0]["file_path"] == "src/data/node-upload.ts"


def test_empty_query_keeps_order():
    cands = [{"content": "a", "file_path": "x"}, {"content": "b", "file_path": "y"}]
    assert LexicalReranker().rerank("", cands) == cands
