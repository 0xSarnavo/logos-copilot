-- Logos Copilot knowledge base schema.
-- EMBED_DIM default = 256 (matches the deps-free HashEmbedder used for local runs).
-- Switching to voyage (1024) / fastembed bge-small (384): ALTER the vector(...) dim,
-- drop & recreate the HNSW index, and re-embed.

CREATE EXTENSION IF NOT EXISTS vector;

-- Rename/alias map (Nomos->logos-blockchain, Codex->logos-storage, Waku->logos-messaging)
CREATE TABLE IF NOT EXISTS components (
  id               text PRIMARY KEY,
  canonical_name   text NOT NULL,
  current_repo     text NOT NULL,
  aliases          text[] NOT NULL DEFAULT '{}',
  is_deprecated    boolean NOT NULL DEFAULT false,
  deprecation_note text,
  latest_version   text
);

CREATE TABLE IF NOT EXISTS chunks (
  id            bigserial PRIMARY KEY,
  source_id     text NOT NULL,
  repo          text,
  component     text NOT NULL,
  version       text NOT NULL DEFAULT 'latest',
  git_sha       text,
  kind          text NOT NULL,                 -- code|doc|spec|sdk|example|openapi|guide
  content       text NOT NULL,
  content_hash  text NOT NULL,
  embedding     vector(384),
  embed_model   text NOT NULL,
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  url           text,
  file_path     text,
  line_start    int,
  line_end      int,
  heading_anchor text,
  deprecated    boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen     timestamptz NOT NULL DEFAULT now(),
  indexed_at    timestamptz NOT NULL DEFAULT now(),
  valid_until   timestamptz,
  deleted_at    timestamptz,
  UNIQUE (source_id, version)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx       ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_comp_ver_idx  ON chunks (component, version) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS chunks_hash_idx      ON chunks (content_hash);
CREATE INDEX IF NOT EXISTS chunks_repo_idx      ON chunks (repo) WHERE deleted_at IS NULL;

-- Symbol/signature index for exact get_api_signature lookups (grounded, never invented).
CREATE TABLE IF NOT EXISTS symbols (
  id          bigserial PRIMARY KEY,
  repo        text,
  component   text NOT NULL,
  version     text NOT NULL DEFAULT 'latest',
  file_path   text NOT NULL,
  name        text NOT NULL,
  kind        text NOT NULL,        -- fn|method|class|struct|trait|enum|interface|proc|endpoint
  signature   text NOT NULL,
  language    text,
  line_start  int,
  git_sha     text,
  url         text,
  indexed_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repo, file_path, name, line_start)
);
CREATE INDEX IF NOT EXISTS symbols_name_idx      ON symbols (component, lower(name));
CREATE INDEX IF NOT EXISTS symbols_name_only_idx ON symbols (lower(name));

-- User/agent feedback (explicit signal channel for the eval/gap loop).
CREATE TABLE IF NOT EXISTS feedback (
  id          bigserial PRIMARY KEY,
  query       text,
  rating      text NOT NULL,          -- 'up' | 'down'
  source_url  text,
  comment     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feedback_rating_idx ON feedback (rating);

-- Query log (records every search so gap detection sees real demand, not just votes).
CREATE TABLE IF NOT EXISTS query_log (
  id bigserial PRIMARY KEY, query text, kind text, component text,
  result_count int, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_log_created_idx ON query_log (created_at);

-- Per-repo state for the freshness engine (last seen commit, last index, active/retired).
CREATE TABLE IF NOT EXISTS repo_state (
  repo            text PRIMARY KEY,
  component       text NOT NULL,
  default_branch  text,
  last_sha        text,
  last_indexed    timestamptz,
  status          text NOT NULL DEFAULT 'active',   -- active | retired
  n_chunks        int DEFAULT 0,
  n_symbols       int DEFAULT 0,
  updated_at      timestamptz NOT NULL DEFAULT now()
);
