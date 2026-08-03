# Review Report 2 — Independent remediation re-review: two-gate-review-p3

## Scope and independence

- **Reviewer:** a *fresh, independent* adversarial reviewer. I did not author the plan, the code,
  the change report, or the earlier `REVIEW_REPORT.md` (including its "Round 2" section). Every
  verdict below is derived from the current code and from my own re-execution, not from trusting the
  implementer's dispositions or the prior reviewer's Round 2. Where I reached the same conclusion as
  Round 2 I say so; I re-verified it rather than inheriting it.
- **Base:** working tree vs `main` @ `fe4da9e`. `feat/two-gate-review-p3` still has **zero commits**
  (`git rev-parse HEAD == fe4da9e`, `git rev-list --count main..HEAD == 0`); the whole change is
  uncommitted working-tree state. Scope: **8 files, +409/−171** (`backend/app/curation/service.py`,
  `backend/app/api/routes_curation.py`, `backend/app/schemas/curation.py`,
  `backend/tests/integration/test_review_groups.py`, `docs/api_contract.md`,
  `frontend/{app.js,index.html,styles.css}`) + untracked `backend/tests/api/test_curation_groups.py`
  and `changes/two-gate-review-p3/`.
- **Posture:** read-only. I edited no code and wrote only this file. Offline test posture
  (`-e OPENAI_API_KEY=`) per the documented design (the `.env` key is credit-exhausted). I did not
  run `docker compose down -v`, so the full clean-slate suite is reported-not-confirmed.

## Read-only checks I ran

| Command | Result |
|---|---|
| `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/api/test_curation_groups.py tests/integration/test_review_groups.py -q` | **23 passed** in 26.6s |
| `docker run --rm … ghcr.io/astral-sh/ruff:0.15.21 check backend/app backend/tests ingestion scripts` | exit 0 — "All checks passed!" |
| `ruff 0.15.21 format --check …` | exit 0 — "103 files already formatted" |
| `node --check frontend/app.js` | OK |
| `git rev-parse HEAD` / `git rev-list --count main..HEAD` / `git diff main --shortstat` | `fe4da9e` / `0` / `8 files, +409/−171` |

Not run (evidence gaps): full clean-slate `pytest tests ingestion/tests` (needs `down -v`), `mypy`
(not installed in the backend image; the project runs it on the host), `make eval`, and the owed
human browser pass. I did not exercise the empty-string-endpoint case in R5 below against the live
DB (it would stage rows); it is traced in code and rated PLAUSIBLE.

## Per-finding remediation verdict

| # | Sev | Claimed | **My independent verdict** | Evidence |
|---|---|---|---|---|
| F1 | Blocking | Fixed | **Fixed-confirmed.** `E()` now `continue`s on `v === false` and maps `v === true → setAttribute(k,'')` (`app.js:12,17`). The builder no longer relies on the `selected` attribute at all: `typeSelect` builds plain `<option>`s and sets `sel.value = current` *after* construction (`app.js:1048-1051`), and `paintNodes`/`paintEdges` feed it `n.type`/`ed.type` from `state` (`app.js:1058,1074`). State and display cannot diverge. | `app.js:4-20,1048-1074` |
| F2 | Blocking | Fixed | **Fixed-confirmed for the input path P3 opened**, with residuals (R4, R5, R6). `create_group` collects `source`+`target` of every edge, subtracts in-group proposed node ids, and for any remainder resolves against approved Neo4j nodes, else `422` (`service.py:191-207`). Covers both endpoints. Two new tests: `test_dangling_edge_endpoint_rejected_422`, `test_edge_to_approved_node_is_accepted`. | `service.py:191-207`, `test_curation_groups.py:234,257` |
| F3 | High | Note fixed; gap accepted | **Fixed-confirmed (note) / Accepted (gap) — owner sign-off still owed.** The extract note no longer names the deleted `審訂佇列`; it now states extract output is single-item, not grouped, absent from 群組審閱, and API-only until a later phase (`app.js:1155-1159`). The reviewability gap itself is real and accepted; it is a **product** decision the owner must sign, not the implementer. | `app.js:1155-1159` |
| F4 | High | Fixed | **Fixed-confirmed, well designed.** `reason → schema_check.propose_reason` (`service.py:212-217`), deliberately *not* `curation_items.reason` (which approve/reject overwrite with the reviewer's reason). Surfaced by `list_groups` as `propose_reason` (`service.py:414-427`), rendered on the review card (`app.js:883`), builder has a real reason input (`app.js:1108,1123`), contract updated, `test_reason_is_persisted_and_surfaced` asserts the round trip. | `service.py:212-217,414-427`; `app.js:883,1108,1123` |
| F5 | Medium | Fixed | **Fixed-confirmed.** `CHANGE_REPORT.md` present and discloses all four deviations. | `CHANGE_REPORT.md` |
| F6 | Medium | Disclosed + narrowed | **Fixed-confirmed.** The three out-of-scope files are named in the change report. The app-wide `@media (max-width:560px)` that repainted `.page-head`/`.ing-wrap`/`.lib-groups` is gone; surviving responsive rules touch only `.sb-row`/`.sb-x`/`.sb-select` and are commented as builder-scoped. | `styles.css:243-272` |
| F7 | Medium | Fixed | **Fixed-confirmed.** `paint()` takes a generation token, builds into a **detached** holder, and commits (`clear(sub); sub.append(holder)`) only if `gen === paintGen` (`app.js:1019-1027`). A stale in-flight `paintExtract` is dropped. `paintExtract` uses no layout-dependent DOM API, so off-document build is safe. | `app.js:1006-1028` |
| F8 | Low | Fixed | **Fixed-confirmed.** Sentinel is now `f"manual:{proposed_by}"` → `manual:human`, matching the `prefix:id` convention; documented in the contract. | `service.py:209-217`, contract |
| F9 | Low | Accepted | **Accepted-appropriately.** Pre-existing project-wide pattern (`CurationItemCreate` equally unbounded); admin-gated; a project-wide tightening, not a P3 regression. | `schemas/curation.py:26-36` |
| F10 | Low | Accepted | **Accepted-appropriately.** `proposed_by` hardcoded `"human"` mirrors legacy `create_item`; no `/admin` route consumes the vendor name today. Governance-spine improvement for a dedicated later change. | `service.py:151`, `routes_curation.py:45-55` |
| S1 | Suggestion | Fixed | **Fixed-confirmed.** `cursor: pointer` folded into the base `.seg button` rule; no duplicate selector. | `styles.css:243` |
| S2 | Suggestion | Fixed | **Fixed-confirmed.** `collections.Counter` replaces the quadratic `ids.count(i)` scan. | `service.py:2,186-189` |

**Summary: 10 of 10 findings + both suggestions resolved or appropriately accepted. Both Blocking
items are genuinely closed.** No fix was cosmetic; no finding was waved through.

## Collateral / regression check on the remediation

- **Shared `E()` helper (F1 fix):** the only boolean-ish call sites in the file are two
  `checked: on ? '' : null` (`app.js:722,731`). `''` takes the unchanged `else setAttribute(k,'')`
  path and `null` is skipped — behaviour identical to before. The new `v === false` / `v === true`
  branches are dead for every existing call site. No regression.
- **F2 Neo4j read at propose time:** `create_group` now does a synchronous Neo4j round trip
  (`anyio.to_thread.run_sync(_approved_labels, …)`) only when an edge has an external endpoint. If
  Neo4j is down this raises inside the request rather than a clean `422`/`503`, but that matches how
  the rest of the service treats Neo4j (`approve_group` etc.) and only fires for the external-endpoint
  case. Acceptable.
- **`schema_check` collision:** `propose_reason` and `group_possible_schema_gap` are distinct keys in
  the same member dict (`service.py:212-217`); `list_groups` reads them independently
  (`_propose_reason` scans `propose_reason`; the gap flag path reads `group_possible_schema_gap`).
  No collision. `test_possible_schema_gap_flag_surfaces_needs_schema_extension` and
  `test_reason_is_persisted_and_surfaced` both pass, confirming they coexist.

## New findings

All minor; none blocks merge. R1–R3 overlap the prior Round 2's R1/R2/R3 (I reached them
independently and confirm them); **R4 is new to this review**.

### R4 (Low, residual on F2) — empty-string edge endpoints slip past the dangling guard and re-open the F2 silent-drop class

- **Evidence:** the guard builds `referenced = {ep for e in proposed_edges for ep in
  (e.get("source"), e.get("target")) if ep}` (`service.py:192`). The `if ep` filter drops any endpoint
  that is `None` **or the empty string**. `_validate_curation_payload("edge", …)` checks only the
  edge's own `id` and `type` (`service.py:38-45`) — it never requires `source`/`target`. So an edge
  with `source: ""` (or `target: ""`) is staged with no existence check. A *missing* endpoint is caught
  later by the live schema gate (`extraction_output_schema` marks `source`/`target` `required`,
  `schema/extraction_output_schema.json:60`), so it can't be approved — but an **empty-string**
  endpoint *is present* as a valid `string`, so the schema gate passes, and at approval
  `load_neo4j.write_edges`'s `MATCH (a {id:""})` finds nothing → MERGE no-ops → the audit log records
  an edge that was never written. That is exactly the F2 silent-drop / false-audit behaviour the fix
  was meant to close, reached through a different input.
- **Reachability:** only via direct API. The builder trims endpoints and blocks submit when any
  relation is missing `source`/`target` (`app.js:1095-1096`), and the endpoint is admin-gated — so a
  real curator using the UI cannot hit it. Hence **Low**, verdict **PLAUSIBLE** (traced in code, not
  executed against the DB to avoid staging rows).
- **Remediation (bounded):** either treat a falsy endpoint as invalid (`422 "edge endpoint required"`)
  in `_validate_curation_payload` for edges, or change the guard to check
  `ep is not None` / `ep != None`-style presence and resolve `""` as unresolved. One-line change in
  `create_group`.

### R3 (Low, residual on F2) — the guard hardens the input, not the sink

- `approve_group` is unchanged: it still returns `"edges": len(edge_payloads)` and writes
  `after_state={"edges": edge_payloads}` without confirming `write_edges`' `MATCH` matched
  (`service.py:504,522-532`). Groups **not** created through `create_group` — the seeder
  (`stage_demo_review_group`) and any future grouped-extract staging — keep the original silent-drop
  behaviour. Live risk is nil today (seeded external endpoints resolve against the seed graph), but the
  bug *class* is untouched. Confirmed independently; carry forward as a known constraint into the
  extract-grouping phase (or make `write_edges` raise on a zero-row MATCH).

### R2 (Low) — the F2 guard reuses a *label* lookup as an *existence* check

- `_approved_labels` filters `if r["label"]` (`service.py:372`), returning only approved nodes with a
  **truthy** label. `_validate_curation_payload` never requires a non-empty `label` and
  `extraction_output_schema` accepts `""`, so an approved node with an empty label would be reported as
  an unresolved endpoint → a false-negative `422` on a guard whose job is existence. PLAUSIBLE; empty
  approved-node labels are unlikely in practice. Fix: use a dedicated `RETURN n.id` existence query
  without the label filter.

### R1 (Low) — `VERIFICATION_REPORT.md` body is stale

- A superseding banner was added, but the body still states pre-remediation figures ("163 passed",
  "20 passed", "7 tests", `source_chunk_id:"manual"`, `?v=20260803-1`, "+347/−169") and the AC5 row
  still reads "Pass (functional) / Owed (visual)" — the exact framing that hid F1. Current reality:
  166/23 passed, 10 group tests, `manual:human`, `?v=20260803-2`, +409/−171. The banner is honest and
  points at `CHANGE_REPORT.md`, so this is a stale-artifact issue, not a misleading-report one.
  Regenerate the traceability/command tables or strike the superseded rows.

### R5 (Suggestion) — no loading state during a sub-view switch

- `paint()` now defers `clear(sub)` until after the `await`, so toggling to `LLM 抽取` leaves the
  previous sub-view on screen for the `/admin/ingest/options` round trip. Correct (that is what fixes
  F7) but slightly less responsive; a one-line skeleton or disabling the toggle mid-paint would close
  it.

## Unreviewed areas / residual risk

- **Full clean-slate suite** (`pytest tests ingestion/tests` on a pristine volume), **mypy**, and
  **`make eval`** — not run here (destructive / not installed / out of scope). The change report claims
  166 passed + mypy success; plausible and self-consistent, treat as reported-not-confirmed. My
  targeted run (23 passed), ruff check+format (clean), and `node --check` (OK) are independently
  confirmed.
- **Owed human browser pass** — still owed and now worth running: F1 and F7 (the two defects checklist
  items 1 and 3 target) are fixed, so the pass is no longer against a build known to be wrong.
  Automation still cannot assert that each builder row's `<select>` *visibly* shows `state.type` after
  add/remove cycles.
- **No frontend test harness** exists (vanilla-JS SPA). F1 was a real Blocking defect the entire
  automated suite could not see — an infra gap, now twice-demonstrated; a small headless-DOM harness is
  worth a future change.
- **P2 dispose surface, `paintExtract` preview/run (owner-token-locked)** — read for context, not
  re-exercised; unchanged by P3.

## Overall disposition

**Not for me to approve, fix, merge, or release.** For the human owner:

- **Both Blocking findings (F1, F2) are genuinely closed**, and I have **no Blocking or High finding**
  in this round. All 10 findings + 2 suggestions are resolved or appropriately accepted.
- The new findings are R1–R3 (Low, all overlapping/confirming Round 2) plus **R4 (Low, new)** — an
  empty-string edge endpoint that re-opens the F2 silent-drop class via direct API only. Recommend a
  one-line tightening in `create_group`/`_validate_curation_payload`, or explicitly accepting it as
  direct-API-only and admin-gated.
- Before merge the owner should: (1) **sign the F3 acceptance** (a product call — after P3,
  `POST /admin/ingest/run` produces knowledge no in-app surface can review until the extract-grouping
  phase); (2) run the owed **browser checklist**; (3) refresh `VERIFICATION_REPORT.md` (R1); (4) decide
  R4, and carry R3 forward as a known constraint into the extract-grouping phase.

Disposition recommendation: **close to ready-for-commit; no blocking finding.** The residuals are Low
and bounded; the human owner holds the F3 product call and the merge/commit authority.
