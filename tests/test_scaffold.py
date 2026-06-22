from logos_copilot import scaffold


def test_unsupported_action():
    r = scaffold.run("rm-rf")
    assert r["ok"] is False and "unsupported" in r["error"]
    assert "create" in r["allowed"]


def test_not_installed(monkeypatch):
    monkeypatch.delenv("LGS_BIN", raising=False)
    monkeypatch.setattr(scaffold.shutil, "which", lambda *_: None)
    r = scaffold.run("version")
    assert r["ok"] is False and r["error"] == "lgs_not_installed"
    assert "cargo install" in r["hint"]


def test_create_rejects_bad_name(monkeypatch):
    monkeypatch.setenv("LGS_BIN", "/bin/echo")
    for bad in ["../evil", "a b", "x;y", "", "rm -rf /"]:
        r = scaffold.run("create", name=bad)
        assert r["ok"] is False and r["error"] == "invalid_or_missing_name"


def test_stub_runs(monkeypatch, tmp_path):
    stub = tmp_path / "lgs"
    stub.write_text('#!/bin/sh\necho "logos-scaffold 9.9.9"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("LGS_BIN", str(stub))
    r = scaffold.run("version")
    assert r["ok"] is True and "9.9.9" in r["stdout"]
    r2 = scaffold.run("create", name="my-app")
    assert r2["ok"] is True and r2["cmd"] == "create my-app"


def test_project_path_requires_workdir(monkeypatch):
    monkeypatch.setenv("LGS_BIN", "/bin/echo")
    monkeypatch.delenv("LGS_WORKDIR", raising=False)
    r = scaffold.run("doctor", project_path="/tmp")
    assert r["ok"] is False and r["error"] == "invalid_project_path"


def test_project_path_escape_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("LGS_BIN", "/bin/echo")
    monkeypatch.setenv("LGS_WORKDIR", str(tmp_path))
    r = scaffold.run("doctor", project_path="/etc")
    assert r["ok"] is False and r["error"] == "invalid_project_path"


def test_project_path_inside_workdir_ok(monkeypatch, tmp_path):
    stub = tmp_path / "lgs"
    stub.write_text('#!/bin/sh\necho ok\n')
    stub.chmod(0o755)
    monkeypatch.setenv("LGS_BIN", str(stub))
    monkeypatch.setenv("LGS_WORKDIR", str(tmp_path))
    r = scaffold.run("doctor", project_path=str(tmp_path))
    assert r["ok"] is True
