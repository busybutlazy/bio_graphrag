# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Domain-specific **GraphRAG tutor for high-school biology** (endocrine / blood-glucose domain). Retrieval is hybrid: vector search over chunks → seed a Neo4j subgraph → compose grounded context → LLM answer. The system's defining constraint is **human curation governance**: an LLM only ever *proposes* graph changes; nothing reaches student-facing retrieval until a human approves it.

Authoritative design docs (read these before non-trivial changes): `docs/graph_plan.md` (phase breakdown), `schema/graph_schema.md` (the data layer across all three stores + curation state machine), `docs/api_contract.md` (endpoint schemas + validation limits). Much of the codebase and docs are written in Traditional Chinese.

## Commands

Everything runs through Docker Compose (there is no local Python venv workflow; the backend image mounts source as volumes, so edits are live without rebuild). Targets in `Makefile`:

```bash
make up            # docker compose up -d --build (postgres, neo4j, qdrant, backend, nginx)
make seed          # load seed data into all three stores — safe to re-run
make health        # curl /health
make test          # docker compose run --rm backend pytest tests ingestion/tests
make eval          # replay 22 golden questions, gate on thresholds
make down          # stop; `docker compose down -v` also wipes the volumes
make export-seed   # snapshot current DB (approved graph + chunks) → data/seed/
```

App is served at `http://localhost:8080/` (nginx → FastAPI). The backend is **not** exposed directly; always go through port 8080. Port 8080 is for local dev + CI (`make health`, `scripts/wait_for_services.sh`).

Publicly the `nginx` container also joins the shared reverse-proxy network `web` (owned by `/home/jett/docker/nginx`, container `nginx-proxy`) as `bio-graphrag-nginx`, reached at `http://biograph.busybutlazy.com/` — routing config lives in `/home/jett/docker/nginx/conf.d/biograph.conf` (outside this repo), not in `docker-compose.yml`.

Run a single test (the backend service already has all deps + DB access):

```bash
docker compose run --rm backend pytest tests/integration/test_curation.py
docker compose run --rm backend pytest tests/integration/test_query.py::test_name -x
```

Backend tests live in `backend/tests/{unit,api,integration}`; ingestion tests in `ingestion/tests`. `make test` runs both suites.

## Architecture

**Four datastores, each with one job:**
- **PostgreSQL** — source of truth for chunks, documents, `curation_items` (pending-review queue), `graph_change_logs` (append-only audit log), `ingestion_jobs`, `query_logs`, `evaluation_*`, and `vendors`/`vendor_usage` (per-company token accounts). Schema is created idempotently by `ingestion/pipeline/load_postgres.ensure_schema`, called on FastAPI startup (`app/main.py` lifespan).
- **Neo4j** — the knowledge graph (nodes + relationships). Every node/edge carries a `status` property.
- **Qdrant** — chunk embedding vectors (collection `biology_chunks`).
- **FastAPI backend** (`backend/app/`) fronted by **nginx**, plus a zero-build static SPA in `frontend/` (vanilla HTML/CSS/JS, served by nginx at `/app/`).

**The `status='approved'` invariant.** All student-facing retrieval reads *only* approved nodes/edges. This filter lives in `app/graph/cypher_templates.py` — every Cypher `MATCH` there is gated on `status = 'approved'` for nodes AND relationships. New/proposed knowledge exists in the graph as `status='proposed'` (or in `curation_items`) and is invisible to retrieval until approved. If you add a retrieval query, it must enforce this filter.

**Hybrid retrieval pipeline** (`app/rag/pipeline.py`): `retriever_vector.retrieve` → collect `concept_ids` from chunk hits → `cypher_templates.expand_from_seeds` (BFS, depth-limited, capped at `MAX_RETURNED_NODES=30`) → `context_composer.compose` → `gateway.generate_answer`.

**Offline vs. online mode is a first-class design axis.** With no `OPENAI_API_KEY` the whole system runs deterministically and for free:
- `app/rag/retriever_vector.py` — semantic (OpenAI embeddings + Qdrant) only when a key is set; otherwise **lexical bigram search over Postgres** (`app/db/chunks.py`). Hash-based embeddings from ingestion carry no cosine meaning, hence the lexical fallback.
- `app/llm/gateway.py` — OpenAI chat vs. an **extractive, clearly-labelled offline answer**. The offline paths report zero tokens.
- A fresh clone + `make seed` runs every screen with no secrets. Preserve this: any new LLM-touching code needs an offline branch, and tests run offline (no key configured).

**Two ingestion paths — do not conflate them:**
- `ingestion/pipeline/` — the **seed loader** (`make seed`, entry `pipeline/run.py`). Takes structured JSON (`data/seed/` if present, else `data/sample/`) → loads Neo4j + Qdrant + Postgres directly. Data written here is already `approved`.
- `ingestion/extract/` — **document ingestion** (`extract/runner.py::ingest_document`). Takes a raw markdown chapter → parse → chunk → per-chunk LLM extraction → schema-validate → stage as `proposed` in `curation_items`. Chunks are written immediately; nodes/edges wait for human approval. `dry_run=True` (used by `/admin/ingest/preview`) does parse+chunk+prompt-assembly only — zero token spend, zero writes.

**Curation governance flow** (`app/curation/service.py`): propose (`create_item`, or LLM staging) → `curation_items` queue → `approve_item` writes the payload into Neo4j as `approved` / `reject_item` / `merge_nodes` / `delete_node`(→`deprecated`). Every mutation appends to `graph_change_logs` with actor + action + reason. Node/edge types are validated against whitelists (`VALID_NODE_TYPES` / `VALID_RELATIONSHIP_TYPES` in `ingestion/pipeline/normalize_concepts.py`) at *create* time — critical because approval interpolates the type into a Cypher label, so an unvalidated type would be an injection vector.

## Auth model (three independent gates)

All are **closed-or-open by config**, driven by `app/core/config.py` / `.env`:
- `ADMIN_API_KEYS` (`vendor:key,...`) guards `/admin/*` via `X-API-Key`. **Empty = auth disabled** (local demo + tests run open). `app/api/auth.py::require_admin`.
- `INGEST_OWNER_SECRET` — a *second* gate on `POST /admin/ingest/run` (the token-spending, graph-mutating action) via `X-Ingest-Owner-Token`. **Empty = locked for everyone** (no open fallback). `options`/`preview` need only the admin key so an interviewer can explore for free.
- `vendors` table — per-company token quotas gate `POST /query` and `POST /check-answer` via `X-API-Key`. **Closed by default** (no key → `login_required`). Managed by `scripts/manage_vendors.py`. Quota is a soft cap (checked at request start). Browsing (library/graph/nodes) stays open.

Note the two different meanings of "empty": admin keys empty = *open*; ingest secret / vendor account absent = *closed*.

## Error contract

All errors return `{"error": {"code": "...", "message": "..."}}` (see `app/api/errors.py::APIError` + the handlers in `app/main.py`). Request-validation limits (question length, `top_k`, `graph_depth`, returned node/chunk counts) are enforced by Pydantic schemas in `app/schemas/` and return `422`. There is deliberately no arbitrary-Cypher or bulk-export endpoint.

## Data & secrets

- `data/sample/` — public committed demo data (endocrine graph + chapters). Always present.
- `data/seed/` — **gitignored** real exported knowledge; takes priority over `data/sample/` when present. Populated by `make export-seed`; copy manually between machines.
- `prompts/graph_extraction_prompt.md` is the public base template; `prompts/profiles/*.profile.md` are gitignored per-chapter IP overlays applied via a chapter's `extraction_profile` front-matter field.
- The `change_me` credential defaults in `config.py` / `.env.example` are placeholders for the local Docker demo only — override every credential in any exposed deployment.
