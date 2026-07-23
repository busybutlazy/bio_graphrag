# Implementation Plan: fix-dangling-edges-bfs

## Objective

Guarantee that BFS graph retrieval never returns an edge whose endpoint is
absent from the returned node set ("dangling edge"). Fix the defect at its
source in `_bfs_expand` (graph retrieval), not downstream in context
composition, and add a defensive test that locks the invariant.

Invariant to enforce for `expand_from_seeds`:

```
For every returned edge:
  edge.source ∈ returned_node_ids
  edge.target ∈ returned_node_ids
```

## In Scope

- Reorder / gate edge insertion inside `_bfs_expand`
  (`backend/app/graph/cypher_templates.py`) so an edge is recorded only when its
  neighbor endpoint is retained in the node set.
- One new regression test asserting the no-dangling-edge invariant when the node
  limit is reached (per the review's proposed test).

## Out of Scope

- Any change to `context_composer`, `pipeline.py`, or prompt templates (the
  review explicitly rejects a compose-layer filter as the wrong place).
- Changing `MAX_RETURNED_NODES` (30) or the depth/limit contract.
- Changing the `status = 'approved'` retrieval invariant or `_EXPAND_QUERY`
  Cypher.
- Public API / response schema changes (shape of `{"nodes":[...],"edges":[...]}`
  is unchanged; only spurious edges are removed).

## Current-State Evidence

- Repository state: branch `main`, working tree clean (`git status`). No
  unexplained edits. Existing `changes/` dir: `expert-readable-review`.
- Relevant files and symbols:
  - `backend/app/graph/cypher_templates.py`
    - `_EXPAND_QUERY` (lines 9-16): undirected `MATCH (a)-[r]-(b)`, filtered to
      `status = 'approved'` on `a`, `b`, and `r`. Returns `startNode(r).id AS
      source`, `endNode(r).id AS target`, and `b.id AS neighbor_id`. **Because
      source/target are the stored direction, the neighbor `b` may appear as
      either `source` or `target`.**
    - `_bfs_expand` (lines 66-101): the defect. Lines 85-89 insert the edge
      unconditionally; lines 91-97 add the neighbor node only if
      `len(nodes) < limit`. When the cap is hit, the edge survives but the
      neighbor does not → dangling edge.
    - `expand_from_seeds` (lines 104-121): pre-seeds `nodes` with surviving
      approved seeds, then calls `_bfs_expand`. Returned node set == `nodes`.
    - `fetch_neighbors` (lines 124-140): calls `_bfs_expand` with an **empty**
      `nodes` and `seed_ids={node_id}`; the centre is returned separately as
      `center_node`, **not** in `nodes`. So for this entry point the valid
      endpoint set is `nodes ∪ {center}`, and the fix must not drop legitimate
      centre-incident edges.
  - `backend/app/rag/pipeline.py:21,46`: `MAX_RETURNED_NODES = 30` passed as
    `node_limit` to `expand_from_seeds`. This is where the cap bites in
    production.
- Existing behavior and baseline tests:
  - `backend/tests/integration/test_neighbors.py` — the only direct coverage of
    this module; builds a `test:`-prefixed subgraph against live Neo4j and
    tears it down. Establishes the fixture pattern to reuse.
  - No existing test exercises the node-limit boundary; the dangling-edge case
    is currently uncovered.
  - Known baseline: `test_pipeline_run_is_idempotent` is flaky on a
    non-pristine Postgres volume (pre-existing, unrelated).

## Acceptance Criteria

1. After the fix, for every edge returned by `expand_from_seeds`, both
   `source` and `target` are present in the returned node ids — including when
   the node limit is reached mid-expansion.
2. `fetch_neighbors` behavior is preserved: centre-incident edges (centre in
   `center_node`, not in `nodes`) are still returned; no legitimate edge is
   dropped.
3. No dangling edge is emitted regardless of stored edge direction (neighbor as
   `source` or as `target`).
4. New regression test fails against the current code and passes after the fix.
5. `make test` passes (modulo the known pre-existing flaky idempotency test).

## Contract, Schema, Dependency, and Migration Impact

- API contract: none. Response shape unchanged; only spurious edges removed
  (strictly fewer or equal edges, never fewer nodes). No `docs/api_contract.md`
  change required.
- Schema/DB/migration: none.
- Dependencies: none added.
- Security: none. `status = 'approved'` gating and node-type whitelists
  untouched.

## Execution Policy

- Plan revision: r1
- Risk level: **low** (single private function, additive test, no contract/
  schema/dependency change, behavior strictly narrows an over-inclusive result).
- Automation mode: **supervised-auto** (chosen by human).
- Auto-approved task IDs (`supervised-auto` only): Task 1.
- Approved file/path scope:
  - `backend/app/graph/cypher_templates.py` (edit `_bfs_expand` only)
  - `backend/tests/integration/test_neighbors.py` (test only — chosen location)
- Human checkpoints: review the diff of `_bfs_expand` before commit; approve any
  deviation from the two files above.
- Mandatory stop conditions: any need to touch `_EXPAND_QUERY`, compose/pipeline
  layers, the response schema, or `MAX_RETURNED_NODES`; any test requiring a new
  fixture pattern beyond the existing `test:`-prefixed live-Neo4j convention.
- Commit/push permission: **No unless separately approved after review.**

## Tasks

### Task 1 — Gate edge insertion on neighbor retention in `_bfs_expand`

- Files/symbols: `backend/app/graph/cypher_templates.py::_bfs_expand`.
- Implementation: replace the per-record body (lines 85-97) so the edge is
  recorded only when the neighbor endpoint is (or becomes) part of the node
  set. The frontier node `a` is always already in the result set for both entry
  points, so gating on the neighbor is sufficient:

  ```python
  for record in session.run(_EXPAND_QUERY, frontier=list(frontier)):
      neighbor_id = record["neighbor_id"]
      if neighbor_id in nodes or neighbor_id in visited:
          keep_edge = True            # neighbor already retained (nodes, or centre for fetch_neighbors)
      elif len(nodes) < limit:
          nodes[neighbor_id] = {
              "id": neighbor_id,
              "label": record["neighbor_label"],
              "type": record["neighbor_type"],
          }
          next_frontier.add(neighbor_id)
          keep_edge = True
      else:
          keep_edge = False           # neighbor dropped by cap → would dangle
      if keep_edge:
          edges[(record["source"], record["relation"], record["target"])] = {
              "source": record["source"],
              "relation": record["relation"],
              "target": record["target"],
          }
  ```

  Notes:
  - `neighbor_id in nodes` covers seeds, previously-added neighbors, and a
    neighbor added earlier in the *same* frontier iteration (avoids wrongly
    dropping a valid edge when the cap is hit between two records for the same
    neighbor).
  - `neighbor_id in visited` preserves `fetch_neighbors`: the centre is in
    `visited` (from `seed_ids`) but not in `nodes`, so centre-incident edges are
    kept while the centre is still not double-added to `nodes`.
  - Correct regardless of stored direction, since the only potentially-unretained
    endpoint is the neighbor `b`.
- Tests and container command: add regression test (below), then
  `docker compose run --rm backend pytest tests/integration/test_neighbors.py -x`
  and finally `make test`.
- Stop/handoff: stop after the two in-scope files are edited and tests pass;
  do not commit.

### Test to add (part of Task 1)

Integration-style test against live Neo4j, matching the existing
`sample_subgraph` teardown pattern (`test:`-prefixed nodes, `DETACH DELETE` in
teardown). Build a star wider than the cap so the limit bites, then assert the
invariant. Suggested shape:

```python
def test_bfs_never_returns_dangling_edges_when_node_limit_reached(...):
    # seed A + 5 approved neighbors A-[REL]->Ni, all status='approved'
    result = expand_from_seeds(driver, ["test:A"], depth=2, node_limit=3)
    node_ids = {n["id"] for n in result["nodes"]}
    assert node_ids  # non-empty
    assert all(
        e["source"] in node_ids and e["target"] in node_ids
        for e in result["edges"]
    )
```

(The exact fixture wiring mirrors `test_neighbors.py`; `node_limit=3` with 5
neighbors forces the cap. Confirm the test **fails on current `main`** before
applying the fix, then passes after.)

## Verification Strategy

- Normal: `expand_from_seeds` on a small graph within the cap → unchanged
  nodes+edges (no regression) — covered by existing `test_neighbors.py`.
- Boundary: node_limit reached mid-expansion → new regression test asserts no
  dangling edge (both `source` and `target` in node set).
- Direction: neighbor stored as `source` (reversed edge) still gated correctly —
  **explicit reversed-edge test case included** (edge stored `neighbor -> frontier`)
  asserting the invariant holds when the dangling endpoint would be `source`.
- Compatibility: `fetch_neighbors` — existing
  `test_neighbors_returns_local_subgraph` still passes (centre-incident edge
  retained).
- Failure/security: unchanged `status='approved'` gating; no new inputs.
- Commands (container-only):
  - `docker compose run --rm backend pytest tests/integration/test_neighbors.py -x`
  - `make test`

## Risks and Unknowns

- Risk: over-dropping legitimate edges. Mitigated by the `neighbor_id in nodes`
  clause covering same-iteration re-encounters and pre-seeded/visited nodes.
- Risk: breaking `fetch_neighbors` centre edges. Mitigated by the
  `neighbor_id in visited` clause and the existing neighbors test.
- Unknown: whether reviewer wants an additional explicit reversed-direction
  test case. Default: cover via code review of the direction-agnostic gate;
  add a case if requested.
- Nondeterminism: BFS record ordering from Neo4j is not guaranteed, but the
  invariant assertion is order-independent, so the test is stable.

## Rollback

Single-commit change to one source function plus one test. Revert the commit;
no data, schema, or config state to unwind.

## Human Decisions and Approval

- Decisions required (all resolved by human):
  1. Automation mode: **supervised-auto**.
  2. Test location: **extend `test_neighbors.py`**.
  3. Reversed-edge-direction test case: **yes, include it**.
- Status: **Approved**
- Approved plan revision: r1
- Approved risk level and automation mode: low / supervised-auto
- Approved by/date: user (busybutlazy@gmail.com), 2026-07-23
- Approval evidence: human invoked `/run-approved-change` on change-id
  `fix-dangling-edges-bfs` after locking all three decisions (supervised-auto;
  extend `test_neighbors.py`; include reversed-edge case). Auto-approved: Task 1
  within `backend/app/graph/cypher_templates.py::_bfs_expand` and
  `backend/tests/integration/test_neighbors.py`.
