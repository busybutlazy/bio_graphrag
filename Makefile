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

demo-reset:  ## undo demo review-group approvals; return them to the review queue
	docker compose run --rm backend python -m scripts.reset_demo_review

seed-sample: seed  ## alias kept for backward compat

# Export current DB state (approved nodes/edges + all chunks) to data/seed/.
# data/seed/ is gitignored — copy it manually when switching machines.
# Workflow: ingest chapters → curate → make export-seed → copy data/seed/ to new machine.
export-seed:
	docker compose run --rm backend python -m scripts.export_seed

eval:
	docker compose run --rm backend python -m app.eval.runner

# Lint + type-check inside a container — nothing to install on the host, so any
# reviewer can reproduce "lint passes". Commands and paths live in scripts/lint.sh;
# config in pyproject.toml; tool versions in backend/requirements-dev.txt.
# CI runs this same target.
#
# LINT_UID/GID are read by the compose `lint` service: without them the container
# runs as root and leaves root-owned caches and rewritten files in the repo.
LINT_UID := $(shell id -u)
LINT_GID := $(shell id -g)
export LINT_UID
export LINT_GID

# --build is not optional: `docker compose run` alone reuses an existing image and
# never notices that requirements-dev.txt changed, so bumping ruff/mypy would leave
# this machine silently on the old version while CI (always a cold build) uses the
# new one. That is the exact drift this target exists to remove. Costs ~3s.
lint:
	docker compose run --build --rm lint

# Auto-fix imports + apply the formatter in place.
format:
	docker compose run --build --rm lint --fix
