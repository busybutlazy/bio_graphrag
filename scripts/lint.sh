#!/usr/bin/env bash
# Lint + type-check. This file is the ONLY place the command list and the linted
# paths are written down; Makefile, docker-compose.yml and CI all route here, so
# they cannot drift apart.
#
# Runs inside the `lint` compose service (see docker-compose.yml) — the host needs
# no ruff/mypy, which is the point: "lint passes" has to be reproducible by anyone.
#
#   scripts/lint.sh          check mode  (`make lint`, CI)
#   scripts/lint.sh --fix    fix mode    (`make format`)
#
# Config lives in the repo-root pyproject.toml; tool versions in
# backend/requirements-dev.txt.
set -euo pipefail

LINT_PATHS=(backend/app ingestion backend/tests ingestion/tests scripts)
TYPE_PATHS=(backend/app ingestion scripts)

if [[ "${1:-}" == "--fix" ]]; then
	ruff check --fix "${LINT_PATHS[@]}"
	ruff format "${LINT_PATHS[@]}"
else
	ruff check "${LINT_PATHS[@]}"
	ruff format --check "${LINT_PATHS[@]}"
	mypy "${TYPE_PATHS[@]}"
fi
