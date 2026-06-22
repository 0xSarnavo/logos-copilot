"""Runtime configuration (stdlib only — no pydantic dependency)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in os.environ.get(name, default).split(",") if s.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://logos:logos@localhost:5432/logos_copilot"
    )
    # fastembed (local BGE, semantic, $0) is the default; hash = deps-free fallback; voyage = premium
    embedder: str = os.environ.get("EMBEDDER", "fastembed")
    # 384 = BGE-small (fastembed) AND the hash embedder, so hash<->fastembed needs no schema change.
    embed_dim: int = int(os.environ.get("EMBED_DIM", "384"))
    local_model: str = os.environ.get("LOCAL_MODEL", "BAAI/bge-small-en-v1.5")
    voyage_api_key: str | None = os.environ.get("VOYAGE_API_KEY")
    voyage_model: str = os.environ.get("VOYAGE_MODEL", "voyage-3-large")
    orgs: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "LOGOS_ORGS", "logos-co,logos-blockchain,logos-storage,logos-messaging"
        )
    )
    max_age_days: int = int(os.environ.get("MAX_AGE_DAYS", "365"))
    # Loopback by default: dangerous tools (code-exec, scaffold) must not be network-reachable
    # out of the box. Binding non-loopback requires AUTH_TOKEN (enforced in server.main()).
    mcp_host: str = os.environ.get("MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.environ.get("MCP_PORT", "8000"))
    web_host: str = os.environ.get("WEB_HOST", "127.0.0.1")   # web playground binds its own host
    web_port: int = int(os.environ.get("WEB_PORT", "8800"))
    auth_token: str | None = os.environ.get("AUTH_TOKEN")
    # Snippet execution is OFF unless explicitly enabled AND doctest configured (see doctest_runner).
    allow_code_exec: bool = os.environ.get("ALLOW_CODE_EXEC", "").lower() in ("1", "true", "yes")
    sandbox_cmd: str | None = os.environ.get("SANDBOX_CMD")  # e.g. "firejail --net=none --read-only=/"
    lgs_workdir: str | None = os.environ.get("LGS_WORKDIR")  # confine scaffold project_path under this


settings = Settings()


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")
