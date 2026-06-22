"""verify_snippet: execute a code snippet through logos-co/logos-doctest and report pass/fail.

Generates a minimal doctest spec (write the snippet to a file + run it with the language runtime,
optionally asserting on output) and invokes the real `logos-doctest` engine. Disabled (returns a
hint) unless DOCTEST_BIN points at a checkout's doctest.py / bin/doctest.

SECURITY: this executes code. It is gated behind operator-set DOCTEST_BIN and runs in a throwaway
temp dir with a timeout. Public deployments MUST additionally sandbox it (container/gVisor). See
DEPLOYMENT.md.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import yaml

# language -> (filename, run argv) executed in the doctest workdir
RUNTIME: dict[str, tuple[str, list[str]]] = {
    "python": ("snippet.py", [sys.executable, "snippet.py"]),
    "py": ("snippet.py", [sys.executable, "snippet.py"]),
    "javascript": ("snippet.js", ["node", "snippet.js"]),
    "js": ("snippet.js", ["node", "snippet.js"]),
    "node": ("snippet.js", ["node", "snippet.js"]),
    "bash": ("snippet.sh", ["sh", "snippet.sh"]),
    "sh": ("snippet.sh", ["sh", "snippet.sh"]),
    "shell": ("snippet.sh", ["sh", "snippet.sh"]),
}
INSTALL_HINT = (
    "logos-doctest is not configured. Clone https://github.com/logos-co/logos-doctest and set "
    "DOCTEST_BIN to its doctest.py (or bin/doctest). Snippet execution stays off until then."
)


def _allow_exec() -> bool:
    return os.environ.get("ALLOW_CODE_EXEC", "").lower() in ("1", "true", "yes")


def _sandbox() -> list[str]:
    s = os.environ.get("SANDBOX_CMD")
    return s.split() if s else []


def doctest_cmd() -> list[str] | None:
    b = os.environ.get("DOCTEST_BIN")
    if b:
        return [sys.executable, b] if b.endswith(".py") else [b]
    w = shutil.which("doctest")
    return [w] if w else None


def available() -> bool:
    """Enabled only when code-exec is explicitly allowed AND a doctest engine is configured."""
    return _allow_exec() and doctest_cmd() is not None


def _spec_yaml(language: str, fname: str, runcmd: list[str], code: str, expect) -> str:
    run_step: dict = {"title": "run snippet", "run": " ".join(runcmd)}
    if expect:
        run_step["expect_contains"] = list(expect)
    spec = {
        "name": "verify-snippet",
        "sections": [{
            "title": "verify",
            "step": True,
            "steps": [
                {"title": "write snippet",
                 "file": {"path": fname, "language": language, "content": code}},
                run_step,
            ],
        }],
    }
    return yaml.safe_dump(spec, sort_keys=False)


def verify_snippet(language: str, code: str, expect_contains=None, timeout: int = 120) -> dict:
    lang = (language or "").lower().strip()
    if lang not in RUNTIME:
        return {"ok": False, "error": "unsupported_language",
                "supported": sorted(set(RUNTIME)),
                "hint": "Rust/Nim/Go need a toolchain — use logos_scaffold/localnet instead."}
    if not _allow_exec():
        return {"ok": False, "error": "code_exec_disabled",
                "hint": "Snippet execution is off. Set ALLOW_CODE_EXEC=1 (plus DOCTEST_BIN, and "
                        "ideally SANDBOX_CMD for isolation) to enable."}
    cmd = doctest_cmd()
    if not cmd:
        return {"ok": False, "error": "doctest_not_installed", "hint": INSTALL_HINT}
    fname, runcmd = RUNTIME[lang]
    d = tempfile.mkdtemp(prefix="verify_")
    spec_path = os.path.join(d, "spec.test.yaml")
    with open(spec_path, "w") as f:
        f.write(_spec_yaml(language, fname, runcmd, code, expect_contains))
    try:
        p = subprocess.run([*_sandbox(), *cmd, "run", spec_path, "--verbose"],
                           cwd=d, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except OSError as e:
        return {"ok": False, "error": f"exec_failed: {e}"}
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return {"ok": p.returncode == 0, "exit_code": p.returncode, "language": lang,
            "output": (p.stdout + "\n" + p.stderr)[-6000:]}
