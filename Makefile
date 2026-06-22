# Local dev against the dockerized pgvector (host port 5433).
export DATABASE_URL ?= postgresql://logos:logos@localhost:5433/logos_copilot
export PYTHONPATH := $(CURDIR)
PY := .venv/bin/python

.PHONY: install test db-up db-down scrape seed ingest-core serve e2e

install:                ## create venv + install deps
	python3 -m venv .venv && $(PY) -m pip install -U pip && $(PY) -m pip install -r requirements.txt

test:                   ## run unit tests
	$(PY) -m pytest tests -q

db-up:                  ## start pgvector (applies db/schema.sql on first boot)
	docker compose up -d db

db-down:                ## stop + remove the db (keeps volume)
	docker compose down

scrape:                 ## crawl the Logos orgs -> sources.generated.yaml (1yr freshness filter)
	$(PY) -m logos_copilot.scrape sources.generated.yaml

seed:                   ## seed the component alias/rename map
	$(PY) -m logos_copilot.ingest seed

ingest-core:            ## ingest a few core repos
	$(PY) -m logos_copilot.ingest repo logos-storage/logos-storage-js
	$(PY) -m logos_copilot.ingest repo logos-blockchain/logos-blockchain-specs
	$(PY) -m logos_copilot.ingest repo logos-co/logos-rust-sdk

migrate:                ## apply idempotent schema migrations (repo-scoping + repo_state)
	$(PY) -m logos_copilot.migrate

refresh:                ## self-update: re-scrape orgs + re-index changed repos + reconcile
	$(PY) -m logos_copilot.refresh all

freshness:              ## print the freshness/coverage report
	$(PY) -m logos_copilot.refresh freshness

serve:                  ## run the MCP server (http://127.0.0.1:8000/mcp by default)
	$(PY) -m logos_copilot.server

web:                    ## run the human web playground (http://127.0.0.1:8800)
	$(PY) -m logos_copilot.web

eval:                   ## run the golden retrieval eval + CI gate
	$(PY) -m logos_copilot.eval eval/golden.yaml

gaps:                   ## report knowledge gaps (down-voted + under-covered queries)
	$(PY) -m logos_copilot.refresh freshness >/dev/null; $(PY) -c "from logos_copilot.db import connect; from logos_copilot.gaps import detect_gaps; import json; print(json.dumps(detect_gaps(connect()),indent=2))"

ci-snippets:            ## run executable code snippets in recipes/ through logos-doctest
	$(PY) -m logos_copilot.ci_snippets recipes

reembed:                ## re-embed the whole KB with the current EMBEDDER (e.g. after EMBEDDER=voyage)
	@echo "Using EMBEDDER=$${EMBEDDER:-hash}. For voyage/fastembed first: ALTER chunks embedding dim + recreate HNSW (see DEPLOYMENT.md)."
	$(PY) -c "from logos_copilot.db import connect;c=connect();cur=c.cursor();cur.execute('TRUNCATE chunks, symbols, repo_state');c.commit();print('cleared')"
	$(PY) -m logos_copilot.refresh all

e2e: db-up seed ingest-core ## full local bring-up
	@echo "KB ready. Run 'make serve' then point an MCP client at http://localhost:8000/mcp"
