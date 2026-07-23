# Verification Report: fix-dangling-edges-bfs

- Plan revision: r1 (Approved, low risk, supervised-auto)
- Mode: evidence-only (no implementation edits during this phase)
- Environment: local Docker Compose (postgres, neo4j, qdrant, backend, nginx all
  running). Offline mode (no `OPENAI_API_KEY`). Container entrypoints only.
- Note on test image: `backend/tests` is NOT volume-mounted (compose mounts only
  `backend/app`). New/edited test files require `docker compose build backend`
  before they are visible to `pytest`; this was done.

## Requirement → Implementation → Test

| # | Acceptance criterion | Implementation | Test / evidence | Result |
|---|----------------------|----------------|-----------------|--------|
| AC1 | No dangling edge from `expand_from_seeds` when node cap is hit | `_bfs_expand` gates edge insertion on neighbor retention (`cypher_templates.py:84-110`) | `test_bfs_never_returns_dangling_edges_when_node_limit_reached` — 5 neighbors, `node_limit=3` | Pass |
| AC2 | `fetch_neighbors` behavior preserved (centre-incident edges kept) | `neighbor_id in visited` clause keeps centre (in `visited`, not `nodes`) | `test_neighbors_returns_local_subgraph`, `test_neighbors_returns_404_for_unknown_node` still pass | Pass |
| AC3 | No dangling edge regardless of stored direction | Gate keys on neighbor `b`, independent of `source`/`target` orientation | `test_bfs_no_dangling_edges_with_reversed_edge_direction` (edges stored `Ni -> A`) | Pass |
| AC4 | New test fails before fix, passes after | — | Reverted-source run: 2 failed w/ concrete dangling edges; restored: 4 passed | Pass |
| AC5 | `make test` passes modulo known flake | — | `1 failed, 126 passed`; sole failure is documented flake | Pass (as planned) |

## Commands, exit codes, counts

- `docker compose build backend` → built OK.
- Bug-catch proof (source fix temporarily reverted, live-mounted):
  `docker compose run --rm backend pytest tests/integration/test_neighbors.py`
  → `2 failed, 2 passed`. Failures:
  - `test_bfs_never_returns_dangling_edges_when_node_limit_reached`
  - `test_bfs_no_dangling_edges_with_reversed_edge_direction`
    with dangling edges e.g. `{source: test:star_n3, relation: INCREASES,
    target: test:star_a}` while `nodes = {test:star_a, test:star_n1,
    test:star_n2}`. Fix then restored (verified identical to pre-revert).
- With fix: `docker compose run --rm backend pytest
  tests/integration/test_neighbors.py` → `4 passed` (exit 0).
- Full suite: `make test` (= `docker compose run --rm backend pytest tests
  ingestion/tests`) → `1 failed, 126 passed in 200.38s` (exit 1).

## Known / unresolved failures

- `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent` —
  `assert chunk_count == len(chunks)` → `12 == 9`. Extra chunks persist on a
  non-pristine Postgres volume (prior extract-test data). This is the
  pre-recorded baseline flake (`known-flaky-idempotent-pipeline-test`),
  independent of graph retrieval and of this change. Not introduced here.

## Mocks / skips / uncertainty

- No mocks; tests run against live Neo4j (real driver, real Cypher).
- Nothing skipped intentionally.
- Nondeterminism: Neo4j record ordering is unspecified, but the invariant
  assertion is order-independent, so the tests are stable across runs.

## Conclusion

Change-relevant verification **passes**. The only full-suite failure is the
documented, unrelated pre-existing flake, exactly as anticipated by AC5. No
implementation edits were made during verification.
