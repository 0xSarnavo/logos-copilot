from logos_copilot.ci_snippets import extract_blocks, verify_markdown


def test_extract_blocks():
    md = "intro\n```python\nprint(1)\n```\nmid\n```rust\nfn main(){}\n```\n"
    b = extract_blocks(md)
    assert len(b) == 2
    assert b[0]["lang"] == "python" and "print(1)" in b[0]["code"]
    assert b[1]["lang"] == "rust"


def test_verify_markdown_skips_unsupported(monkeypatch):
    # with code-exec disabled, supported langs report ok=False(code_exec_disabled) but unsupported skip
    monkeypatch.delenv("ALLOW_CODE_EXEC", raising=False)
    res = verify_markdown("```rust\nfn main(){}\n```\n")
    assert res[0]["ok"] is None and res[0]["skipped"]


def test_untagged_block_counted_as_skipped():
    # untagged ```...``` blocks must be captured (as skipped), not silently dropped
    res = verify_markdown("```\nplain code\n```\n")
    assert res and res[0]["ok"] is None and "language tag" in res[0]["skipped"]
