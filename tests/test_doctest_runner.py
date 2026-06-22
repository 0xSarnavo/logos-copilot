from logos_copilot import doctest_runner


def test_unsupported_language(monkeypatch):
    monkeypatch.setenv("ALLOW_CODE_EXEC", "1")
    r = doctest_runner.verify_snippet("rust", "fn main(){}")
    assert r["ok"] is False and r["error"] == "unsupported_language"
    assert "python" in r["supported"]


def test_code_exec_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_CODE_EXEC", raising=False)
    r = doctest_runner.verify_snippet("python", "print('hi')")
    assert r["ok"] is False and r["error"] == "code_exec_disabled"


def test_not_installed(monkeypatch):
    monkeypatch.setenv("ALLOW_CODE_EXEC", "1")
    monkeypatch.delenv("DOCTEST_BIN", raising=False)
    monkeypatch.setattr(doctest_runner.shutil, "which", lambda *_: None)
    r = doctest_runner.verify_snippet("python", "print('hi')")
    assert r["ok"] is False and r["error"] == "doctest_not_installed"


def test_available_requires_both(monkeypatch, tmp_path):
    stub = tmp_path / "doctest"
    stub.write_text("#!/bin/sh\n")
    stub.chmod(0o755)
    monkeypatch.setenv("DOCTEST_BIN", str(stub))
    monkeypatch.delenv("ALLOW_CODE_EXEC", raising=False)
    assert doctest_runner.available() is False        # configured but not allowed
    monkeypatch.setenv("ALLOW_CODE_EXEC", "1")
    assert doctest_runner.available() is True


def test_spec_yaml_shape():
    y = doctest_runner._spec_yaml("python", "snippet.py", ["python", "snippet.py"],
                                  "print('x')", ["x"])
    assert "verify-snippet" in y and "expect_contains" in y and "snippet.py" in y
