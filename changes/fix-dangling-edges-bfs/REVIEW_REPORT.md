# Review Report: fix-dangling-edges-bfs

## Re-review Addendum (after remediation commit `d706400`)

The implementer committed `d706400` to address this review. Re-checked
independently:

- **M1 (report/state contradiction) → RESOLVED.** CHANGE_REPORT.md and
  VERIFICATION_REPORT.md now state the change is **committed** on branch
  `fix/dangling-edges-bfs` (not "uncommitted on main"), enumerate `87a91e1` and
  the follow-up commit, and record the commit-before-review ordering as an
  explicit human decision (the supervised-auto flow stopped before committing).
  The artifacts now match the repository. Confirmed accurate against
  `git log`/`git status`.
- **L1 (fetch_neighbors cap boundary untested) → RESOLVED.** Added
  `test_fetch_neighbors_no_dangling_edges_when_limit_reached` (5-neighbor centre,
  `limit=3`): asserts no edge escapes `nodes ∪ {centre}` and that every retained
  neighbor keeps its centre-incident edge — exercising the `neighbor_id in
  visited` clause. The test is correct for the fetch_neighbors endpoint contract
  (uses `nodes ∪ {centre}`, not the plain node set). Independently re-ran the file:
  **5 passed in 8.33s.** Fail-before is confirmed by static analysis (pre-fix code
  recorded edges to all 5 neighbors while only 3 nodes survive → n4/n5 dangle);
  not reproduced by editing implementation code, per reviewer bounds.
- **S1 → accepted** as pre-existing residual behavior, as noted below.

**Re-review verdict:** all findings from this review are resolved or accepted; no
new findings. Core correctness remains CONFIRMED. No Blocking/High items. The
change is, in this reviewer's assessment, ready for human approval / PR. The
reviewer still does not itself approve, merge, or release.

---

## Review Context

- Diff base and scope: commit `87a91e1` ("fix(graph): prevent dangling edges in
  BFS retrieval when node cap is hit") on branch `fix/dangling-edges-bfs`,
  compared against parent `b991840`. Attributable change: `_bfs_expand` in
  `backend/app/graph/cypher_templates.py` (+25/−6) and two regression tests plus
  fixtures in `backend/tests/integration/test_neighbors.py` (+86). The four
  `changes/fix-dangling-edges-bfs/*.md` artifacts are bundled in the same commit.
- Artifacts reviewed: IMPLEMENTATION_PLAN.md (r1, Approved, low/supervised-auto),
  TASK_LOG.md, VERIFICATION_REPORT.md, CHANGE_REPORT.md, the committed diff, the
  two changed source/test files in full, downstream consumers
  (`rag/context_composer.py`, `rag/pipeline.py`, `api/routes_nodes.py`).
- Independence disclosure: **Full independence.** The implementation commit
  carries `Claude-Session: …session_01Utx2gZPzjHJiznJVbhE8WH`; this review runs
  in a different session with no shared implementation context.
- Checks performed: read-only inspection + one containerized read-only test run
  (`docker compose run --rm backend pytest tests/integration/test_neighbors.py`).
  I did **not** modify any implementation file and did **not** re-run the full
  `make test` suite (see Unreviewed Areas).

## Completion Claim Assessment

The central claim — *"for every edge returned by `expand_from_seeds`, both
`source` and `target` are in the returned node ids, including when the node cap
is hit, independent of stored edge direction"* — is **CONFIRMED**.

- Static trace of `_bfs_expand` (`cypher_templates.py:80-114`): each edge's two
  endpoints are `{frontier a, neighbor b}`. The frontier `a` is always already
  in the result set for both entry points (seeds are pre-added to `nodes`; later
  frontiers are exactly the nodes just added). The edge is now recorded only when
  `neighbor_id in nodes or neighbor_id in visited` (both endpoints already
  retained) or when the neighbor is newly added under the cap; otherwise node and
  edge are dropped together. For `expand_from_seeds`, `visited ⊆ nodes` at all
  times, so the invariant holds strictly on `nodes`. Gate keys on the neighbor,
  so it is direction-agnostic — confirmed.
- The change is strictly narrowing: node sets are identical to the pre-fix code
  (the added `neighbor_id in nodes` guard only suppresses idempotent re-adds), and
  no edge between two *retained* nodes is newly dropped (such a neighbor is `in
  nodes` → kept). CHANGE_REPORT's "possibly fewer edges, never fewer nodes" is
  accurate.
- Bug is real and downstream-visible: `context_composer.py:26-27` renders a
  dangling edge as `raw_id --REL--> raw_id` (label lookup falls back to the id),
  and `relationships_used` would reference nodes absent from `supporting_nodes`.
  Fixing at the retrieval source is the correct layer (plan's rejection of a
  compose-layer filter is sound).
- Independent test run on the committed code: **4 passed in 8.18s**, including
  both new regression tests. This confirms the "passes after" half of AC4. The
  "fails before" half is confirmed by static analysis (the removed block recorded
  every edge unconditionally) and by the documented reverted-source run; I did not
  reproduce it myself because doing so requires editing implementation code, which
  is outside a reviewer's permitted writes.

## Findings

### Blocking

None.

### High

None.

### Medium

- **M1 — Review artifacts misstate the repository state (committed vs.
  uncommitted, wrong branch).** CHANGE_REPORT.md:4 says *"implemented + verified;
  **uncommitted on `main`**, handed to review,"* CHANGE_REPORT.md:73-74 says
  *"This flow did not commit, push, merge, or deploy,"* and the plan's
  Current-State Evidence says *"branch `main`, working tree clean."* Actual state:
  the change **is committed** as `87a91e1` on branch **`fix/dangling-edges-bfs`**
  (not `main`), and that commit bundles the change plus all four report artifacts.
  The plan (IMPLEMENTATION_PLAN.md:108) states *"Commit/push permission: No unless
  separately approved after review,"* i.e. the intended sequence was
  review-before-commit. The commit is human-authored (`jett`) with a Claude
  session trailer, so the most likely story is the human committed after the
  reports were written — within their prerogative — but the artifacts now
  describe a state that no longer exists, and the governance sequence
  (review → then commit) was inverted. *Impact:* a downstream approver trusting
  the reports would be misled about whether anything is committed and on which
  branch. *Remediation direction:* reconcile the reports with reality (state that
  the change is committed as `87a91e1` on `fix/dangling-edges-bfs` by human
  decision), and confirm the commit-before-independent-review ordering was
  intended, not an automation overstep. No code change implied.

### Low

- **L1 — `fetch_neighbors` cap-boundary path has no new regression test.**
  `_bfs_expand` is shared by `fetch_neighbors` (GET `/neighbors`,
  routes_nodes.py:28), whose valid-endpoint set is `nodes ∪ {centre}` and whose
  correctness under the fix depends on the `neighbor_id in visited` clause
  (centre lives in `visited`, never in `nodes`). The two new tests only exercise
  `expand_from_seeds`; AC2 leans on the pre-existing
  `test_neighbors_returns_local_subgraph`, which does **not** reach the node cap.
  So the specific interaction "fetch_neighbors with a centre having more than
  `limit` neighbors" is unverified by test. Static analysis shows it is correct
  (centre-incident edges kept via `visited`; new neighbors gated normally), and
  the existing neighbors test still passes — so residual risk is low.
  *Remediation direction (optional):* add one cap-boundary test for
  `fetch_neighbors` mirroring the wide-star fixture, asserting centre-incident
  edges are retained and no non-centre dangling edge is emitted. Note the
  `_assert_no_dangling_edges` helper cannot be reused verbatim for that entry
  point (it would flag legitimate centre edges), which is itself a reason the gap
  is easy to miss.

### Suggestion

- **S1 — Nondeterministic survivor selection under the cap (pre-existing,
  informational).** Which neighbors survive when `>limit` are available depends on
  Neo4j's unspecified record ordering, so retrieval output (and the composed LLM
  context) is nondeterministic once the graph exceeds `MAX_RETURNED_NODES=30`.
  This predates the change and is out of scope; the fix neither introduces nor
  worsens it. Flagged only so it is on record as accepted residual behavior.

## Requirement and Test Coverage Gaps

- AC1 (no dangling edge from `expand_from_seeds` at the cap): covered by
  `test_bfs_never_returns_dangling_edges_when_node_limit_reached`; independently
  re-run — pass.
- AC2 (`fetch_neighbors` preserved): covered for the non-cap path only; the
  cap-boundary path for that entry point is a coverage gap (L1).
- AC3 (direction-agnostic): covered by
  `test_bfs_no_dangling_edges_with_reversed_edge_direction`; re-run — pass.
- AC4 (fail-before / pass-after): pass-after independently confirmed;
  fail-before confirmed by static analysis + documented reverted run, not
  independently reproduced by this review (reviewer may not edit implementation
  code to reproduce).
- AC5 (`make test` green modulo the known flake): **not independently re-run** by
  this review. Relying on TASK_LOG/VERIFICATION (`1 failed, 126 passed`, sole
  failure `test_pipeline_run_is_idempotent`, matching the pre-recorded flake).

## Compatibility, Security, and Scope Assessment

- API contract: unchanged. Response shape `{"nodes":[…],"edges":[…]}` preserved;
  only spurious edges are removed. `docs/api_contract.md` correctly untouched.
- Security: `status = 'approved'` gating on nodes/edges (`_EXPAND_QUERY`) and the
  node-type whitelists are untouched; no new inputs, no new Cypher interpolation.
  No regression to the curation invariant.
- Scope: edits confined to the two approved paths (`_bfs_expand` and the test
  file). No out-of-scope source edits; `_EXPAND_QUERY`, compose/pipeline layers,
  response schema, and `MAX_RETURNED_NODES` all untouched, matching the plan's
  stop conditions.
- Consumers checked: `pipeline.py:46` and `routes_nodes.py:44` (both
  `expand_from_seeds` with `MAX_RETURNED_NODES`) and `routes_nodes.py:28`
  (`fetch_neighbors`) all benefit from the fix; none relied on the previous
  dangling-edge behavior.
- Rollback: single-commit revert of one function + one test; no data/schema/config
  state to unwind. Accurate as reported.

## Unreviewed Areas and Residual Risk

- Full `make test` suite was not re-run in this review; the `1 failed / 126
  passed` result and the pre-existing-flake attribution are taken from the
  implementation-side reports (consistent with the `known-flaky-idempotent-
  pipeline-test` record). Residual risk: low.
- The fail-before behavior was not independently reproduced (would require a
  reviewer edit to implementation code, which is out of bounds); reliance is on
  static analysis of the removed unconditional-edge block plus the documented run.
- `fetch_neighbors` under the node cap is unverified by test (L1); low residual
  risk given the static trace and the direction-agnostic gate.
- Nondeterministic survivor selection above the cap (S1) remains as accepted
  behavior.

## Human Disposition Required

The reviewer does not approve, fix, merge, or release this change. The core
correctness claim is verified and the implementation is sound and in-scope. Two
items need a human decision before this is considered closed:
1. **M1** — reconcile the report artifacts with the actual committed state and
   confirm the commit-before-independent-review ordering was intended.
2. **L1** — decide whether to add a `fetch_neighbors` cap-boundary regression
   test or accept the documented low residual risk.
