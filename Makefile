.PHONY: up down logs test health seed seed-sample export-seed eval lint format

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm backend pytest tests ingestion/tests

health:
	curl -sf http://localhost:8080/health | python3 -m json.tool

# Load seed data into DB (Postgres + Neo4j + Qdrant).
# Reads from data/seed/ if it exists (your real exported knowledge),
# otherwise falls back to data/sample/ (public demo data).
# Run once after `make up` on a fresh DB, or after `docker compose down -v`.
seed:
	docker compose run --rm backend python -m ingestion.pipeline.run

seed-sample: seed  ## alias kept for backward compat

# Export current DB state (approved nodes/edges + all chunks) to data/seed/.
# data/seed/ is gitignored — copy it manually when switching machines.
# Workflow: ingest chapters → curate → make export-seed → copy data/seed/ to new machine.
export-seed:
	docker compose run --rm backend python -m scripts.export_seed

eval:
	docker compose run --rm backend python -m app.eval.runner

# Lint + type-check (needs dev tools: pip install -r backend/requirements-dev.txt).
# Config lives in pyproject.toml. CI runs the same three commands.
LINT_PATHS = backend/app ingestion backend/tests ingestion/tests scripts
lint:
	ruff check $(LINT_PATHS)
	ruff format --check $(LINT_PATHS)
	mypy backend/app ingestion scripts

# Auto-fix imports + apply the formatter in place.
format:
	ruff check --fix $(LINT_PATHS)
	ruff format $(LINT_PATHS)
