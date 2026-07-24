# Review Report: unified-two-gate-review (Phase 1 — walking skeleton)

## Review Context

- **Diff base and scope:** `5d9ebae..01a08a1` on `feat/two-gate-review` — the single commit
  `feat(review): group-level two-gate review (Phase 1 walking skeleton)` (13 files, +1199/-1).
  Reviewed post-commit; the owner elected to commit directly rather than gate on this review.
- **Artifacts reviewed:** `IMPLEMENTATION_PLAN.md` (rev 1, Approved 2026-07-24), `TASK_LOG.md`,
  `VERIFICATION_REPORT.md`, the full commit diff, `backend/tests/api/test_review.py`,
  `backend/tests/integration/test_review_groups.py`, `docs/api_contract.md`, and live read-only
  probes of the running stack through nginx (`GET /admin/review/groups`, `GET /neighbors/…`,
  `GET /nodes/…`).
- **Independence disclosure:** This review ran in a **separate session** from the implementation
  (commit trailer names session `01EiG9K4QyRYxBqgreDghzHz`; this is `01WNHbLcEsyWvj7k7auRmtGh`), so
  I did not author the plan or the code. Independence is adequate. I share the repository and its
  docs, so shared-assumption blind spots remain possible.
- **Evidence gap (recorded, not a defect):** there is **no `CHANGE_REPORT.md`** for this change —
  `report-change` was skipped between verification and commit. The completion claim was therefore
  assessed against the commit message + `VERIFICATION_REPORT.md`.
- **Worktree state:** `docs/agent-guideline.md` is modified and uncommitted (a skill-forge template
  self-heal, v0.7.0 → v0.8.3). Unrelated to this change; the plan flagged it and it was correctly
  kept out of the commit. Left uncommitted — record, do not bypass.

## Completion Claim Assessment

The claim under test (commit message): *"approve invariant proven (group nodes absent from the
graph before approval, approved after)"*, and acceptance criterion **A2**: *"Before approval, the
group's nodes are **not** returned by `GET /neighbors` / `/query` graph expansion; `POST
.../approve` then writes them and they **are** returned."*

**The claim does not hold for the artifact that actually ships.** It holds only for the synthetic
test fixture (`hormone:t2_insulin`, `regulatory_effect:t2_re`, …), whose ids exist nowhere else. The
one proposal group that `make seed` stages — `group:blood_glucose_case_001` — is built from node ids
that the same `make seed` run *already loaded into Neo4j as `approved`*. Verified live, with the
group still `proposed`:

```
$ curl -s :8080/admin/review/groups        # group:blood_glucose_case_001 present, status proposed
    proposed_nodes: hormone:insulin, physiological_variable:blood_glucose,
                    regulatory_effect:insulin_decreases_blood_glucose

$ curl -s ":8080/neighbors/hormone:insulin?depth=1"   # approved-only retrieval, BEFORE any approval
    nodes: [... physiological_variable:blood_glucose, regulatory_effect:insulin_decreases_blood_glucose ...]
```

All three "pending" nodes are already retrievable by students before the expert touches the Review
screen. Everything else in the claim — migration, group assembly, both gates computed live, the two
new endpoints, one audit row per decision, `make test` 140 passed, ruff/format/mypy clean — I was
able to corroborate. The gap is specific and consequential: it sits exactly on the project's
governance thesis, and it turns the headline demo into a no-op.

**Verdict: the walking skeleton works; the completion claim is overstated and the shipped demo data
is wrong for it.**

## Findings

### Blocking

**B1 — Approving the seeded demo group silently mutates already-approved knowledge and duplicates
edges in the student-facing graph.**

- *Evidence:* `ingestion/pipeline/run.py:62` stages `blood_glucose_case_001`;
  `data/sample/expert_demo/cases.json` case 1 proposes `hormone:insulin`,
  `physiological_variable:blood_glucose`, `regulatory_effect:insulin_decreases_blood_glucose` —
  every one of which is also in `data/sample/biology_sample_concepts.json` **and**
  `data/seed/biology_sample_concepts.json`, loaded as `approved` by the same `make seed`.
  `backend/app/curation/service.py:approve_group` passes the case payloads to
  `ingestion/pipeline/load_neo4j.py:write_nodes`, which does
  `MERGE (n:Type {id}) SET n.label = $label, n.description = $description` — an unconditional
  overwrite of the existing approved node.
  Live pre-approval state: `GET /nodes/hormone:insulin` → `label: "Insulin"`,
  `description: "由胰臟分泌,降低血糖濃度的激素"`. Case-1 payload: `label: "胰島素"`,
  `description: "由胰島β細胞分泌、降低血糖的激素。"`.
- *Second effect:* `write_edges` does `MERGE (a)-[r:TYPE {id: $id}]->(b)` — **keyed on edge id**.
  The approved graph already holds `edge:insulin_has_effect_insulin_decreases_blood_glucose`,
  `…_on_variable_…`, `…_decreases_…`. Case 1 proposes the same three relationships under new ids
  `e:c1:has_effect`, `e:c1:on_variable`, `e:c1:decreases`. Approving therefore creates **three
  parallel duplicate relationships** between the same node pairs, which then flow into
  `expand_from_seeds` BFS and every neighbors/concept-map view.
- *Violated requirement:* A2 (invariant), and the CLAUDE.md governance premise that approval is how
  new knowledge *enters* the graph — not a path that rewrites curated knowledge without review of
  the delta.
- *Impact:* one click in the shipped demo degrades the curated graph (a hand-curated English label
  and description replaced by extraction text) and permanently pollutes it with duplicate edges. The
  degradation is invisible: the reviewer is shown a "proposal", not a diff against what already
  exists. `make seed` will not repair the labels — it re-MERGEs, but the duplicate `e:c1:*` edges
  survive. In a portfolio piece whose thesis is *auditable* curation, this is the worst possible
  place for silent overwrite.
- *Bounded remediation direction (do not implement from this report):* pick one —
  (a) seed the demo group from node/edge ids that are **not** in the approved seed graph, so the
  invariant demo is real; or (b) have `approve_group` detect members that already exist as
  `approved` and refuse / surface them as an explicit "update existing node" decision with a
  `before_state` diff. (a) is the smaller, more demo-honest fix; (b) is the one Phase 3+ will need
  anyway once hand-made proposals can touch existing nodes.

### High

**H1 — The verification report and commit message assert an invariant that the shipped data does not
demonstrate.**

- *Evidence:* `VERIFICATION_REPORT.md` line 37 marks A2 **Pass**, citing
  `test_review_groups::test_approve_group_writes_all_and_audits` (node status `None` → `approved`).
  That test uses `hormone:t2_insulin` / `regulatory_effect:t2_re` — synthetic ids absent from the
  seed graph. No test, and no manual observation in the report, exercises the seeded group against
  retrieval. The live probe above shows the seeded group's nodes are retrievable pre-approval.
- *Violated requirement:* A2 as literally worded; the "Requirement → Implementation → Test → Result"
  table's implied claim that the evidence covers the delivered feature.
- *Impact:* the report reads as if the governance invariant is proven end-to-end on real seeded data
  ("proven end-to-end through nginx … including the approve invariant", Summary). It is proven only
  for greenfield ids. Anyone relying on this report — an interviewer, or the next phase's plan —
  inherits a false premise. This is what let B1 through.
- *Remediation direction:* restate A2's evidence as fixture-scoped, and add the missing case —
  approve/reject behaviour when a group member id **already exists** in the approved graph.

**H2 — The "Schema gate" does not gate: `approve_group` writes to the approved graph without
consulting `schema_gate` or the stored `schema_check`.**

- *Evidence:* `backend/app/curation/service.py:approve_group` reads rows, flips status, and calls
  `load_neo4j.write_nodes/write_edges`. It never calls `evaluate_schema_gate` and never reads
  `schema_check`. `list_groups` computes the gate for **display only**. On the client,
  `frontend/app.js::paintExpert` appends `reviewActions(g)` unconditionally — the 核准 button is
  live regardless of `g.schema_gate.result`.
- *Second-order:* grouped items are inserted by raw SQL (`load_postgres.stage_demo_review_group`),
  bypassing `service._validate_curation_payload`, which is the whitelist check CLAUDE.md calls out
  as *"critical because approval interpolates the type into a Cypher label"*. Injection itself is
  still blocked one layer down by `load_neo4j._safe_type`'s identifier regex — so this is **not** an
  injection hole — but an off-whitelist-yet-syntactically-valid label (`Foo`) would be MERGE'd into
  the approved graph unchallenged. Not currently reachable through any API (no endpoint sets
  `group_id`), so it is latent, not exploitable today.
- *Violated requirement:* the plan's own framing — "reviewed as one unit **through** the Schema gate
  … then approved". A gate that cannot stop anything is a label.
- *Impact:* today, benign (the only producer is the trusted seed, and Case 1 passes). **Phase 2
  explicitly seeds the form/meaning rejection cases (D3)** — at that point the demo will show a red
  "未過" badge next to a fully functional 核准 button, and a failing proposal can be written into the
  graph. This becomes a live governance defect the moment P2 lands.
- *Remediation direction:* decide and record whether the schema gate is **advisory** (engineer may
  override, but the override must be captured in the audit row) or **enforcing** (409 when
  `result != pass`). Either is defensible; the current state is neither, and the UI implies
  enforcing. This decision belongs to the human, not the reviewer.

### Medium

**M1 — Audit fidelity regresses relative to `approve_item` on exactly the path that mutates most.**

- *Evidence:* `approve_item` (`service.py:169`) logs `curation_item_id=row["id"]` and
  `after_state=payload` (the whole node/edge). `approve_group` logs
  `after_state={"nodes": [ids], "edges": [ids]}` — **no payloads, no `before_state`, no
  `curation_item_id`** — for a write that touches 6 graph elements at once.
- *Impact:* given B1, the audit row for the shipped demo approval would record "we approved these 3
  node ids" while the actual effect was "we rewrote the label and description of 3 curated nodes and
  added 3 duplicate edges." The append-only log cannot reconstruct what changed. For a project whose
  spine is *auditable* governance, the group path is the least auditable path in the system.
- *Remediation direction:* capture `before_state` (the pre-write graph state of the touched ids) and
  the full member payloads in `after_state`; consider one audit row per member plus a group row, or
  a single row carrying both payload sets.

**M2 — Plan deviation: `CurationError` is not mapped to the documented error contract.**

- *Evidence:* Plan T4 says *"Map `CurationError` to the error contract."*
  `backend/app/api/routes_review.py` raises `HTTPException(status_code, detail=…)`, yielding
  `{"detail": …}`. CLAUDE.md and `app/api/errors.py` state the contract is
  `{"error": {"code", "message"}}`; `app/main.py` registers a handler for `APIError` only — there is
  no `HTTPException` handler.
- *Mitigating:* this exactly matches the pre-existing convention in `routes_curation.py`, and
  `frontend/app.js:59` already tolerates both shapes
  (`(body.error && body.error.message) || body.detail`), so nothing is user-visibly broken.
  `docs/api_contract.md` documents the new status codes but not the body shape.
- *Impact:* the new endpoints extend a documented-contract violation to fresh surface, and the
  deviation is not recorded in `TASK_LOG.md` (T4's only listed deviation is the router-restart
  gotcha). Low functional risk; real drift between CLAUDE.md and reality.
- *Remediation direction:* either raise `APIError` in the new routes, or amend CLAUDE.md /
  `api_contract.md` to state that `/admin/*` uses `{"detail"}`. Consistency matters more than which.

**M3 — A4 (transactionality) is claimed Pass on happy-path evidence only, and the 409 path is
untested at every layer.**

- *Evidence:* Plan T2 lists *"transactional all-or-nothing"* as a required test. No such test exists
  in `test_review_groups.py` or `test_review.py`; `VERIFICATION_REPORT.md:39` concedes "**Not**
  failure-injected" yet still records **Pass**. Separately, both files test only 404 — the 409
  ("no proposed items" / double-approve) branch in `approve_group`/`reject_group` has **zero**
  coverage, despite Plan T4 naming "unknown id 404/409".
- *Also:* in `approve_group`/`reject_group` the `SELECT` and the 404/409 guard run **outside**
  `conn.transaction()`; the transaction opens afterwards. Two concurrent approves can both observe
  `proposed`, both write Neo4j, and both append an `approve` audit row — the second's `UPDATE …
  WHERE status='proposed'` matches nothing but the response still reports `nodes: 3, edges: 3`. Not
  a realistic single-reviewer demo risk; a correctness wart on an audited path.
- *Remediation direction:* add the 409 test (cheap, closes a named plan requirement); add a
  fault-injected rollback test or downgrade A4 to "Partial — happy path only" in the report; move
  the guard inside the transaction with `FOR UPDATE`.

### Low

**L1 — The approve/reject success message is never visible.**
`frontend/app.js::reviewActions.act()` sets `msg.textContent = '已核准並寫入知識圖譜(nodes …)'` and
then immediately calls `paintList(); paintPanel()` — or, when the list empties (the Phase-1 case,
since there is exactly one group), `return renderReview(host)`. Both paths run `clear(...)` over the
node holding `msg`. The reviewer clicks 核准 and sees only "目前沒有待審的提案群組。" — no confirmation
that anything was written. A5 was signed off manually by the owner; this is the kind of thing a
single manual pass misses. Remediation: surface the result outside the repainted region, or repaint
after an acknowledgement.

**L2 — `approve_group` ignores `curation_items.action`.**
It partitions purely on `item_type` and always writes as a create. A grouped item with
`action='delete'` or `'update'` would be written into the graph rather than deprecated/merged.
`create_item` accepts an arbitrary `action` string. Unreachable today (nothing sets `group_id`
except the seed, which writes `'create'`), but it is a silent-wrong-behaviour trap for P3's
hand-made group create. Remediation: assert `action == 'create'` in `approve_group` and fail loudly
otherwise.

**L3 — Process/evidence gaps.** No `CHANGE_REPORT.md`; independent review ran **after** the commit
rather than before (owner's explicit election — recorded, not challenged); `docs/agent-guideline.md`
remains modified and uncommitted in the worktree.

### Suggestion

- **S1** — the Review tab is labelled **"AI 提案"**, but `proposed_by` is `'demo'` and the content is
  hand-authored seed JSON, not an LLM extraction. For a portfolio piece defending honest governance,
  consider a label that does not assert an LLM provenance the data does not have (or surface
  `proposed_by` next to it, which the panel already fetches).
- **S2** — Plan T4 named `backend/app/schemas/review.py`; the implementation reuses
  `app.schemas.curation.ApproveRejectRequest` instead. That is the better call (no new DTO for an
  identical shape), but it is an unlogged plan deviation. Worth one line in `TASK_LOG.md`.
- **S3** — `list_groups` builds `build_context` from **proposed groups only**, so a group whose edge
  references an existing *approved* node renders that node as a humanized id in the expert lens
  (and as "（相關概念）" in the concept map). Acceptable for Phase 1 (Case 1 has
  `references_existing: []`), but it will visibly degrade the expert view as soon as P2 adds cases
  that reference the existing graph.

## Requirement and Test Coverage Gaps

| Criterion | Claimed | Assessed |
|---|---|---|
| A1 — group listed with live gate + understanding | Pass | **Confirmed** (live `GET /admin/review/groups`: `schema_gate.result=pass`, P1 sentence) |
| A2 — invariant absent-before / present-after | Pass | **Not supported for shipped data** — see H1/B1. Holds for synthetic fixtures only |
| A3 — reject writes nothing + audit; approve audits | Pass | Confirmed by tests; audit *content* is thin (M1) |
| A4 — transactional all-or-nothing | Pass | **Partial** — happy path only, no fault injection, plan-required test absent (M3) |
| A5 — Review view renders 3 tabs + actions | Pass | Human sign-off only; no automated FE coverage. L1 is a defect that survived that pass |
| A6 — `make test` green except known flake | Pass | Confirmed (140 passed, 1 = documented non-pristine-volume flake). The "not a regression" argument from the diff is sound — `stage_demo_review_groups` writes only `curation_items` |

Untested paths: 409 (no proposed items / double-approve); concurrent approve; transactional
rollback; approval of a group whose ids collide with approved graph state (**the shipped case**);
approval of a group whose `schema_gate.result != pass`; any frontend behaviour.

## Compatibility, Security, and Scope Assessment

- **Migration:** `ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS group_id TEXT` — idempotent,
  nullable, ordered before `created_at` in `schema.sql` only for fresh installs. Backward-compatible;
  existing per-element curation is untouched; `list_items` and `approve_item` ignore `group_id`.
  Verified twice-run idempotence claim is consistent with the DDL. No concerns.
- **Contract:** purely additive (`GET /admin/review/groups`, `POST …/{id}/approve|reject`),
  documented in `docs/api_contract.md`. `/admin/curation/*` and `/admin/expert-demo/*` unchanged.
  Error-body shape diverges from CLAUDE.md (M2).
- **Security:** the new router carries `dependencies=[Depends(require_admin)]`, consistent with every
  other `/admin` router — correct. **No Cypher injection:** `load_neo4j._safe_type`'s
  `^[A-Za-z_][A-Za-z0-9_]*$` guard stands between group payloads and label interpolation. The
  whitelist *bypass* described in H2 is a data-quality gap, not an injection vector, and is not
  reachable through any HTTP endpoint. `group_id` is only ever passed as a bound parameter.
  No new secrets, no new dependencies, offline mode unaffected (both gates are pure functions —
  `engineer_gate` and `back_translation` make no LLM calls).
- **Scope:** the diff stays inside the plan's approved paths. Nothing from the P2–P5 roadmap leaked
  in. The `expert` view was correctly retained (retirement is P4). One out-of-plan simplification
  (S2), no out-of-scope edits, no generated or untracked artifacts. `data/seed/` is untouched, and
  `_EXPERT_DEMO_CASES` correctly pins to `parse_source.DATA_DIR` (always `data/sample`) rather than
  `_active_seed_dir()`, so a populated `data/seed/` cannot break `make seed` — I checked this
  specifically because it would have been an easy trap.
- **Rollback:** the plan's rollback section is honest about the additive column. It does **not**
  cover undoing an approval — and per B1, an approval is not cleanly undoable (the overwritten
  labels are gone, `make seed` will not remove the duplicate `e:c1:*` edges). Rollback should be
  revised alongside B1.

## Unreviewed Areas and Residual Risk

- **Frontend rendering and interaction were not executed.** I read `renderReview` and the CSS
  classes it reuses (all present in `frontend/styles.css`; `ex-case-body` is unstyled but is used
  identically by the pre-existing `renderExpertDemo`, so not a regression). L1 was found by reading,
  not by clicking. Layout, the force-directed concept map, and the expert-tab id/JSON isolation
  claim rest on the owner's manual pass alone.
- **I did not execute `approve_group` against the live seeded group** — doing so would have mutated
  the approved graph, which is outside a reviewer's authority. B1 is therefore established from
  MERGE semantics, the two datasets, and the confirmed live pre-state, not from an observed
  mutation. I consider it confirmed; a human can settle it in seconds by approving on a throwaway
  volume and diffing `GET /nodes/hormone:insulin`.
- `make eval` was not run (retrieval untouched — though note B1's duplicate edges *would* enter
  retrieval expansion once an approval happens).
- The known `test_pipeline_run_is_idempotent` flake was accepted as documented and unrelated; I did
  not re-verify against a pristine volume.
- Absence of further findings is not proof of correctness. The largest residual risk is that H2's
  non-enforcing gate and B1's collision are the *same* underlying gap — approval writes without
  reconciling against what the gate said or against what the graph already holds — and a fix that
  addresses only one leaves the other.

## Human Disposition Required

B1 (blocking) and the H2 advisory-vs-enforcing question are **scope and design decisions**, not
reviewer calls. B1 in particular should be settled before Phase 2 seeds the rejection cases, because
P2 lands directly on top of both.

The reviewer does not approve, fix, merge, or release this change.

---

## Re-review — remediation pass (2026-07-24, commit `a23d9ac`)

Re-ran against `fix(review): close review findings` (`a23d9ac`), which the owner committed on top of
the reviewed `01a08a1`. Independence unchanged (still a separate session from both the implementation
and the fix). I read the full remediation diff and re-probed the live stack read-only. The
`REVIEW_REPORT.md` I authored is byte-identical to what shipped — not edited to soften findings.

### Disposition of each finding

| # | Finding | Status | Evidence |
|---|---|---|---|
| **B1** | Approve overwrites curated knowledge / duplicate edges | **Fixed (both ways)** | New seed `data/sample/expert_demo/review_groups.json` proposes `hormone:cortisol` + `regulatory_effect:cortisol_increases_blood_glucose` — neither id is in `data/sample` or `data/seed` concepts; `physiological_variable:blood_glucose` is *referenced by edges, never re-proposed*. **And** `approve_group` now runs `_existing_approved_ids` → 409 if any member id already exists approved. Live: `GET /nodes/hormone:cortisol` → **404**; `blood_glucose` neighbors do **not** contain the cortisol RE pre-approval. Test `test_approve_refuses_when_a_member_already_exists_approved` asserts the pre-existing node is left untouched. |
| **H1** | Report claimed invariant proven on shipped data | **Fixed** | A2 row in `VERIFICATION_REPORT.md` rewritten to disclose the original synthetic-only evidence and cite the real 404 probe. Honest now. |
| **H2** | Schema gate did not gate | **Fixed (enforcing)** | `approve_group` computes `evaluate_schema_gate` inside the txn and raises 409 unless `result == 'pass'`; UI disables 核准 with an explanation. `test_approve_refuses_when_schema_gate_fails` (a `fail_pattern` group is refused, nothing written). The raw-SQL whitelist-bypass sub-point is now moot for the write path — the gate runs the same validation before any MERGE. Audited engineer override explicitly deferred (owner: "enforcing now, override later"). |
| **M1** | Thin audit row | **Fixed** | `after_state` now carries full node/edge payloads + `item_ids` + gate result; `test_approve_audit_records_full_payloads` asserts payloads, not bare ids. |
| **M2** | Error contract deviation | **Fixed** | New routes raise `APIError` via `_as_api_error`; live 404 returns `{"error":{"code":"not_found","message":…}}`. Deviation from `/admin/curation/*` documented in `api_contract.md`. |
| **M3** | Transactionality / 409 untested; guard outside txn | **Partially fixed** | 409 now covered at both layers (`test_double_approve_is_409`, `test_double_approve_409_uses_error_contract`); row `SELECT … FOR UPDATE` moved inside the transaction, closing the concurrent-approve race. **A4 fault-injected rollback still not tested** — openly recorded as not-fixed. Acceptable for a walking skeleton; will matter more as the path grows. |
| **L1** | Success message destroyed by repaint | **Fixed (code)** | Result banner (`flash`) now lives outside the repainted list/panel. Not browser-verified — see residual risk. |
| **L2** | `action` ignored | **Fixed** | Non-`create` actions → 422 (`test_approve_refuses_non_create_action`). |
| **L3 / S2** | Missing CHANGE_REPORT / unlogged DTO reuse | **Fixed** | `CHANGE_REPORT.md` added; `ApproveRejectRequest` reuse logged as a deviation. |
| **S1** | False "AI 提案" label | **Fixed** | Tab relabelled 提案內容; `proposed_by` shown. |
| **S3** | Referenced approved nodes render as humanized ids | **Fixed** | `list_groups` resolves approved-node labels; live understanding reads "使**Blood glucose**上升" (real graph label). |

### Verified independently this pass
- `make test` → **146 passed, 1 failed**; the sole failure is the documented `test_pipeline_run_is_idempotent`
  flake (chunk_count 12≠9), which the diff cannot cause (`stage_demo_review_groups` writes only
  `curation_items`). Review suites **14 passed** after a backend rebuild.
- Live: single seeded group `group:demo_cortisol_blood_glucose`, gate `pass`; both proposed nodes 404
  pre-approval; error contract confirmed on the wire.

### Residual risk (unchanged disposition)
- **A4 rollback is still not fault-injected** — the one review finding carried forward unaddressed, by
  the owner's explicit choice. Low risk at this scale; note it before the group path takes on
  update/delete verbs.
- **The L1/H2/S1 UI changes were made *after* the owner's manual browser pass and have not been
  re-checked in a browser.** All FE evidence remains `node --check` + code reading + live API. A
  human should click through 群組審閱 once (esp. the disabled-approve-on-gate-fail state and the flash
  banner) before this is called done.
- The B1 collision guard keys on `status = 'approved'`; a member id colliding with a `proposed`/`deprecated`
  graph node would still MERGE. Not reachable in the current flow (Neo4j nodes are only ever written as
  `approved`), so latent, not a defect.

### Re-review verdict

**All blocking and high findings are resolved; the completion claim now holds for the data that
ships.** The remediation is well-targeted, tested at the service and API layers, and the reports were
corrected rather than papered over. Two items remain open and are *honestly disclosed, not hidden*:
A4 fault-injection (owner-deferred) and a browser re-check of the post-remediation UI. Neither is
blocking for a Phase-1 walking skeleton.

Remaining disposition is the human's: accept with the two disclosed follow-ups, or require the browser
pass first. The reviewer still does not approve, merge, or release.
