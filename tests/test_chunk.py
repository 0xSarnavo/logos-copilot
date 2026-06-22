from logos_copilot.chunk import (
    chunk_code,
    chunk_file,
    chunk_markdown,
    content_hash,
    file_kind,
)


def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")


def test_markdown_splits_on_heading():
    chunks = chunk_markdown("# A\nalpha\n\n# B\nbeta\n")
    assert len(chunks) == 2
    assert chunks[0][1] == "a"  # heading anchor
    assert "alpha" in chunks[0][0]
    assert chunks[1][1] == "b"


def test_code_windows_overlap():
    text = "\n".join(f"line{i}" for i in range(300))
    chunks = chunk_code(text, max_lines=120, overlap=20)
    assert len(chunks) >= 3
    assert chunks[0][2] == 1
    assert chunks[0][3] == 120


def test_file_kind():
    assert file_kind("src/main.rs") == "code"
    assert file_kind("README.md") == "doc"
    assert file_kind("api/openapi.yaml") == "openapi"
    assert file_kind("image.png") is None


def test_chunk_file_dispatch():
    kind, chunks = chunk_file("a.md", "# H\nbody text here\n")
    assert kind == "doc" and chunks
    kind, chunks = chunk_file("a.bin", "x")
    assert kind is None and chunks == []
