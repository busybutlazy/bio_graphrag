# Change Report: fix-dangling-edges-bfs

- Plan revision executed: r1 (Approved, low risk, supervised-auto)
- Status: implemented + verified + reviewed. **Committed** on branch
  `fix/dangling-edges-bfs`:
  - `87a91e1` — the fix, its two `expand_from_seeds` regression tests, and the
    initial report artifacts (committed by human `jett` after the supervised-auto
    run finished; the automation itself did not commit).
  - Follow-up commit — the `fetch_neighbors` cap-boundary test (review finding
    L1) plus this report reconciliation (review finding M1).
- Governance-ordering note (M1): the plan set "Commit/push permission: No unless
  separately approved after review," implying review-before-commit. In practice
  the human committed `87a91e1` before independent review and then requested the
  review; the review ran against that commit. This ordering was the human's
  explicit decision, not an automation overstep — the supervised-auto flow
  stopped before committing, as designed.

## What was completed

Fixed the dangling-edge defect in BFS graph retrieval at its source. In
`_bfs_expand` (`backend/app/graph/cypher_templates.py`) the edge was previously
recorded unconditionally while the neighbor node was only added under the node
cap; once the cap (`MAX_RETURNED_NODES=30`) was hit, edges to dropped neighbors
survived, producing edges whose endpoints were absent from the returned node
set.

The per-record loop now records an edge only when its neighbor endpoint is (or
becomes) part of the result:
- `neighbor_id in nodes or neighbor_id in visited` → keep edge (neighbor already
  retained, incl. the `fetch_neighbors` centre which lives in `visited` but not
  `nodes`);
- else if under the cap → add the neighbor node + queue it + keep edge;
- else → drop the node **and** its edge together.

The frontier node is always already in the result set, so gating on the neighbor
guarantees both endpoints are present. The gate keys on the neighbor `b`, so it
is correct whether the neighbor appears as the edge `source` or `target`.

## Observable behavior change

- `expand_from_seeds` now satisfies: for every returned edge, both `source` and
  `target` are in the returned node ids — including when the node limit is hit.
- Result is strictly narrower: possibly fewer edges, never fewer nodes; node
  count still capped at `node_limit`. No change when the graph fits under the cap.
- `fetch_neighbors` unchanged in behavior (centre-incident edges retained).

## Files changed

- `backend/app/graph/cypher_templates.py` (+25/−6): `_bfs_expand` edge gating.
- `backend/tests/integration/test_neighbors.py`: three regression tests —
  `node_limit`-reached and reversed-edge-direction for `expand_from_seeds`, plus
  `test_fetch_neighbors_no_dangling_edges_when_limit_reached` (L1) covering the
  `fetch_neighbors` cap boundary (valid endpoint set `nodes ∪ {centre}`,
  centre-incident edges retained) — supporting fixtures and imports.

## Contract / dependency / migration impact

- API contract: none. Response shape `{"nodes":[...],"edges":[...]}` unchanged;
  `docs/api_contract.md` needs no update.
- Schema / DB / migration: none.
- Dependencies: none added.
- Security: `status='approved'` gating and node-type whitelists untouched.

## Verification summary

- All three regression tests fail on pre-fix code (concrete dangling edges shown,
  including the `fetch_neighbors` case `test:star_a -> test:star_n4`) and pass
  after (5 passed in the file).
- `make test` → 1 failed, 126 passed (initial run, before the L1 test). The single
  failure is the documented pre-existing flake `test_pipeline_run_is_idempotent`
  (non-pristine Postgres volume), unrelated to this change.
- Full detail in `VERIFICATION_REPORT.md` and `TASK_LOG.md`.

## Independent review outcome

- `REVIEW_REPORT.md`: core correctness claim **CONFIRMED**; no Blocking/High
  findings. Two dispositions actioned by human decision:
  - **M1** (reports misstated committed state) → reconciled in this report.
  - **L1** (`fetch_neighbors` cap boundary untested) → regression test added.
  - **S1** (nondeterministic survivor selection above the cap) → accepted as
    pre-existing residual behavior; out of scope.

## Deviations / limitations

- Process note: `docker compose build backend` was required because
  `backend/tests` is not volume-mounted (only `backend/app` is). Within the
  approved container entrypoint; no extra source paths touched.
- The pre-existing idempotency flake remains and is out of scope.
- S1 (nondeterministic survivor selection above `MAX_RETURNED_NODES`) is accepted
  residual behavior, unchanged by this fix.

## Not completed / not verified

- Nothing outstanding within scope. No performance profiling was done (not an
  acceptance criterion; the change adds only O(1) per-record checks).

## Remaining work

- None required by this change. Optional next step: push the branch and open a PR
  if the change is to be merged (not yet done).

## Rollback

Revert the single change to `_bfs_expand` and remove the two added tests (one
diff, two files). No data/schema/config state to unwind.
