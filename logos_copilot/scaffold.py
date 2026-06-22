"""Safe wrapper around `logos-co/scaffold` (the `lgs` / `logos-scaffold` CLI).

Design: NO arbitrary passthrough. Only an allowlisted set of actions maps to fixed argv, the project
`name` is validated to a plain identifier, and `lgs` absence is handled gracefully (with an install
hint) so the MCP server runs even when the binary isn't present.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

# action -> argv appended after the binary. Conservative, mostly project-scoped / read-only.
_ACTIONS: dict[str, list[str]] = {
    "version": ["--version"],
    "help": ["--help"],
    "create": ["create"],            # + <name>  : bootstrap a new LEZ project
    "new": ["new"],                  # + <name>
    "init": ["init"],                # init in an existing dir
    "doctor": ["doctor"],            # diagnostics
    "build": ["build"],              # build a project
    "localnet_status": ["localnet", "status", "--json"],
}
_NEEDS_NAME = {"create", "new"}

INSTALL_HINT = (
    "logos-scaffold (lgs) is not installed on this host. Install it with "
    "`cargo install --git https://github.com/logos-co/scaffold` "
    "(see https://github.com/logos-co/scaffold), or set LGS_BIN to its path."
)


def _safe_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name or ""))


def _confine(project_path: str) -> tuple[str | None, str | None]:
    """Confine a caller-supplied project_path under LGS_WORKDIR. Returns (cwd, error)."""
    root = os.environ.get("LGS_WORKDIR")
    if not root:
        return None, "project_path requires LGS_WORKDIR to be configured"
    real = os.path.realpath(project_path)
    rroot = os.path.realpath(root)
    if not (real == rroot or real.startswith(rroot + os.sep)):
        return None, "project_path escapes LGS_WORKDIR"
    if not os.path.isdir(real):
        return None, "project_path does not exist"
    return real, None


def lgs_bin() -> str | None:
    return os.environ.get("LGS_BIN") or shutil.which("lgs") or shutil.which("logos-scaffold")


def available() -> bool:
    return lgs_bin() is not None


def version() -> dict:
    return run("version")


def run(action: str, name: str | None = None, project_path: str | None = None,
        timeout: int = 180) -> dict:
    if action not in _ACTIONS:
        return {"ok": False, "error": f"unsupported action '{action}'",
                "allowed": sorted(_ACTIONS)}
    binp = lgs_bin()
    if not binp:
        return {"ok": False, "error": "lgs_not_installed", "hint": INSTALL_HINT}
    argv = [binp, *_ACTIONS[action]]
    if action in _NEEDS_NAME:
        if not _safe_name(name or ""):
            return {"ok": False, "error": "invalid_or_missing_name",
                    "hint": "name must match [A-Za-z0-9_-]{1,64}"}
        argv.append(name)
    cwd = None
    if project_path is not None:
        cwd, err = _confine(project_path)
        if err:
            return {"ok": False, "error": "invalid_project_path", "hint": err}
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True,
                           text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "cmd": " ".join(_ACTIONS[action])}
    except OSError as e:
        return {"ok": False, "error": f"exec_failed: {e}"}
    return {
        "ok": p.returncode == 0,
        "exit_code": p.returncode,
        "cmd": " ".join(_ACTIONS[action]) + ((" " + name) if name else ""),
        "stdout": p.stdout[-4000:],
        "stderr": p.stderr[-2000:],
    }
