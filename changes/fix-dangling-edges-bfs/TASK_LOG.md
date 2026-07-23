# Task Log: fix-dangling-edges-bfs

- Plan revision: r1
- Approval evidence: human invoked `/run-approved-change` on change-id
  `fix-dangling-edges-bfs`; plan Status=Approved, low risk, supervised-auto,
  Task 1 only, paths `backend/app/graph/cypher_templates.py` (`_bfs_expand`) +
  `backend/tests/integration/test_neighbors.py`.
- Risk level: low
- Automation mode: supervised-auto
- Auto-approved tasks: Task 1
- Approved path scope:
  - `backend/app/graph/cypher_templates.py` (edit `_bfs_expand` only)
  - `backend/tests/integration/test_neighbors.py` (tests only)
- Baseline Git state and tests: branch `main`, clean except untracked
  `changes/fix-dangling-edges-bfs/`. No unrelated staged/modified files. Known
  pre-existing flake: `test_pipeline_run_is_idempotent` on non-pristine Postgres
  volume (unrelated).

## Task 1 — Gate edge insertion on neighbor retention in `_bfs_expand`

- Boundary and allowed paths: `_bfs_expand` in
  `backend/app/graph/cypher_templates.py`; regression tests appended to
  `backend/tests/integration/test_neighbors.py`.
- Files changed:
  - `backend/app/graph/cypher_templates.py` — `_bfs_expand` per-record body now
    gates edge insertion on neighbor retention (`neighbor_id in nodes or in
    visited`, else add-if-under-cap, else drop node+edge together).
- Tests added/modified: `backend/tests/integration/test_neighbors.py` — added
  `wide_star_forward` + `wide_star_reversed` fixtures, `_assert_no_dangling_edges`
  helper, and tests `test_bfs_never_returns_dangling_edges_when_node_limit_reached`
  and `test_bfs_no_dangling_edges_with_reversed_edge_direction`; added import of
  `expand_from_seeds`.
- Container commands and exit codes:
  - `docker compose build backend` → success (tests dir is baked into the image,
    not volume-mounted; rebuild required to pick up new tests).
  - Bug-catch proof: with the source fix temporarily reverted,
    `pytest tests/integration/test_neighbors.py` → **2 failed, 2 passed**; both
    new tests failed with concrete dangling edges (e.g. `test:star_n3
    -INCREASES-> test:star_a` with `nodes={star_a, star_n1, star_n2}`), and the
    reversed case showed the dangling endpoint as `source`. Fix then restored.
  - With fix: `pytest tests/integration/test_neighbors.py` → **4 passed**.
  - Full: `make test` → **1 failed, 126 passed** (exit 1). Sole failure is the
    documented pre-existing flake `test_pipeline_run_is_idempotent`
    (chunk_count 12 vs 9, extra persisted chunks on non-pristine Postgres
    volume) — not caused by this change.
- Acceptance criteria demonstrated: AC1–4 via the two new tests (fail→pass) and
  the reversed-direction case; AC2 via unchanged `test_neighbors_*`; AC5 modulo
  the known flake as planned.
- Tests not run and why: none skipped intentionally; the one failure is the
  pre-existing unrelated flake.
- Deviations: One process note — `docker compose build backend` was required
  because `backend/tests` is not volume-mounted (only `backend/app` is), so new
  test files need an image rebuild. This is within the approved container
  entrypoint and touched no additional source paths. No scope/contract deviation.
- Result: **Pass** (change-relevant suite green; only the documented baseline
  flake fails).
