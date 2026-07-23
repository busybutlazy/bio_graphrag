# Task Log: expert-gate-integrity

- Plan revision: 1 (Approved)
- Approval evidence: IMPLEMENTATION_PLAN.md §Human Decisions — user (jett) 2026-07-23; hybrid mode, supervised-auto for T1/T5/T6.
- Risk level: medium
- Automation mode: supervised-auto
- Auto-approved tasks: T1, T5, T6
- Approved path scope: data/sample/expert_demo/**, backend/tests/**
- Baseline Git state and tests: branch `main` (no commits performed — prohibited in this workflow). Worktree at start: `docs/agent-guideline.md` M (skill-forge-managed self-heal to 0.8.3, unrelated + outside scope, left untouched); `changes/expert-gate-integrity/` untracked (this change's artifacts). Known pre-existing flake: `test_pipeline_run_is_idempotent` on non-pristine Postgres volume. Baseline expert-demo suite green at 5 cases before edits.

## T1 — add cases 6 (form-reject) & 7 (meaning-reject)

- Boundary and allowed paths: `data/sample/expert_demo/cases.json` only.
- Files changed: `data/sample/expert_demo/cases.json` (+134 lines, additive; round-trip-verified formatting).
- Tests added/modified: none (behavior asserted in T5).
- Container commands and exit codes: `docker compose build backend` (0); targeted pytest below.
- Acceptance criteria demonstrated: endpoint returns 7 cases; case 6 → `fail_pattern`; case 7 → gate `pass`, `is_gap=false`, `expert_review.status="rejected"`.
- Tests not run and why: n/a.
- Deviations: None.
- Result: Pass

## T5 — engineer-gate + api coverage

- Boundary and allowed paths: `backend/tests/unit/test_engineer_gate.py`, `backend/tests/api/test_expert_demo.py`.
- Files changed: added `test_case6_incomplete_pattern_fails`, `test_case7_wrong_biology_still_passes_form_gate`; updated `len(cases)` 5→7; added case 6/7 gate + expert-status assertions.
- Container commands and exit codes: `docker compose run --rm backend pytest tests/unit/test_engineer_gate.py tests/unit/test_back_translation.py tests/api/test_expert_demo.py tests/gold/test_gold_examples.py -q` → **21 passed** (0).
- Acceptance criteria demonstrated: G5-A, G5-B, G5-C.
- Deviations: `./backend/tests` is not volume-mounted (only `./backend/app` is) → rebuilt image via `docker compose build backend` before tests reflected. Process step, not a scope change.
- Result: Pass

## T6 — gold-per-case invariant scoped to promoted cases

- Boundary and allowed paths: `backend/tests/gold/test_gold_examples.py`.
- Files changed: renamed `test_every_case_has_a_gold_file` → `test_every_promoted_case_has_a_gold_file`; asserts gold ids == `{promote==true}` cases (excludes rejection cases 6/7).
- Container commands and exit codes: included in the 21-passed run above (0).
- Acceptance criteria demonstrated: gold net excludes non-promoted rejection cases; suite green.
- Deviations: None.
- Result: Pass

## Full verification (evidence-only)

- Command: `make test` → **129 passed, 1 failed** in 231s.
- Sole failure: `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent` (`chunk_count 12 != 9`) — known pre-existing non-pristine-volume flake, documented in memory and excluded by the plan's stop conditions. Unrelated to this change (ingestion chunk pipeline; expert_demo data is not loaded by the seed pipeline).
- Conclusion: this change's requirements fully verified; no regression introduced. Stop and hand to review-change.

## T2 — expert-review persistence service (one-task-at-a-time)

- Boundary and allowed paths: `backend/app/**`, `backend/tests/**`. Endpoint (T3) and frontend (T4) NOT touched.
- Files changed:
  - `backend/app/curation/service.py` — added `record_expert_review(case_id, decision, schema_gap_type, notes, actor) -> str` reusing `_log_change` (action=`expert_review`, target_type=`expert_demo_case`, target_id=case_id, reason=notes, after_state={decision, schema_gap_type}); made `_log_change` return its `change_id` (additive; annotation `-> None`→`-> str`; existing callers ignore the return — needed by T3).
  - `backend/tests/integration/test_expert_review_log.py` — new; 2 tests.
- Tests added: `test_record_expert_review_writes_one_audit_row`, `test_record_expert_review_persists_schema_gap_decision`.
- Container commands and exit codes:
  - `docker compose build backend` → 0.
  - `docker compose run --rm backend pytest tests/integration/test_expert_review_log.py -q` → **2 passed** (0).
  - Regression: `pytest tests/integration/test_curation.py -q` → **5 passed** (0) — shared `_log_change` unaffected.
- Acceptance criteria demonstrated: G2-A (one `graph_change_logs` row with action=`expert_review`, target_type=`expert_demo_case`, actor, reason, after_state carrying decision; row count == 1; nothing written to Neo4j/approved graph — service only calls `_log_change`).
- Tests not run and why: lint/type-check (`ruff`/`mypy`) not present in the backend runtime image (Makefile runs them on host; host exec avoided) → deferred to full `verify-change`/CI. Code matches existing style.
- Deviations: rebuilt image because `backend/tests` is not volume-mounted (same as batch). No scope/contract/dependency/migration change. No endpoint or frontend edit.
- Result: Pass

## T3 — POST /admin/expert-demo/reviews endpoint + contract doc (one-task-at-a-time)

- Boundary and allowed paths: `backend/app/**`, `backend/tests/**`, plus `docs/api_contract.md` (contract doc, named in plan T3). Frontend (T4) NOT touched.
- Files changed:
  - `backend/app/schemas/expert_demo.py` — new; `ExpertReviewRequest` (case_id 1–200, decision Literal, schema_gap_type ≤100, notes ≤2000).
  - `backend/app/api/routes_expert_demo.py` — added `POST /expert-demo/reviews` (status 201) calling `record_expert_review` with `actor="demo-viewer"`; updated module docstring (read-only → read + append-only audit write).
  - `docs/api_contract.md` — GET note scoped to "此 GET 唯讀"; added `POST /admin/expert-demo/reviews` subsection (request shape, 201 body, side effect = one audit row only).
  - `backend/tests/api/test_expert_demo.py` — added `test_post_review_validates_and_records` (invalid decision → 422; valid → 201 + change_id) with asyncpg cleanup.
- Container commands and exit codes:
  - `docker compose build backend` → 0.
  - `docker compose run --rm backend pytest tests/api/test_expert_demo.py tests/integration/test_expert_review_log.py -q` → **5 passed** (0). POST test exercises full FastAPI path incl. DB write → confirms router wired, no import cycle.
- Acceptance criteria demonstrated: G2-A endpoint half — `POST` persists via T2 service, admin-gated, returns change_id; invalid decision → 422; never writes Neo4j/approved graph/curation_items.
- **DEVIATION (disclosed):** plan T3 wrote `decision ∈ {approve, doubt, schema_gap}`, but the frontend expert tab (`frontend/app.js:831`) actually uses `agree | doubt | cannot` (gap only when `cannot`). Implemented the endpoint enum as the **frontend-consistent `agree|doubt|cannot`** so T4 can talk to it. This changes the plan's literal enum wording (not the intent). Flag for human confirmation.
- Tests not run and why: `ruff`/`mypy` not in backend image (host-only per Makefile; host exec avoided) → deferred to full `verify-change`/CI. Code matches existing style.
- Deviations (other): rebuilt image (tests not volume-mounted). No dependency/migration; no `schema/` type change; no approved-graph or curation mutation.
- Result: Pass

## T4 — frontend expert tab: persist via POST + seeded verdict + M1 (one-task-at-a-time)

- Boundary and allowed paths: `frontend/**` only. Backend/docs NOT touched (frontend/app.js only; no CSS change — reused `.notice`/`.btn`).
- Files changed: `frontend/app.js` (`renderExpertDemo`):
  - `buildReviewForm`: added a **送出審查** submit button that `api.post('/admin/expert-demo/reviews', {case_id, decision, schema_gap_type (only when cannot), notes})`; keeps the sessionStorage echo for local browsing; replaced the now-false "不寫入資料庫" note with an append-only-audit note + submit status line.
  - `paintExpert` + new `expertVerdict`/`EXPERT_STATUS`: renders the **seeded authoritative expert verdict** read-only by default (approved→green, rejected→red, schema_gap→neutral; white-language, no id/schema/gap code — isolation preserved), so Case 7's "rejected" shows by default. (Seeded `expert_review.status` uses a different vocabulary than the viewer radios, so it is surfaced as an authoritative banner rather than pre-selecting a radio.)
  - **M1 fix (folded in per review disposition):** for `engineer_gate.result ∈ {fail_schema, fail_pattern, fail_testability}`, the expert tab now shows "在工程師 gate 因形式問題被退回,不進入專家審查" instead of the misleading P5 gap "system understanding". A genuine `needs_schema_extension` (Case 5) still reaches the expert with its gap sentence.
- Tests added: none — no automated frontend suite exists in the repo.
- Container/commands and results:
  - `node --check frontend/app.js` → **syntax OK**.
  - `make up` + wait-for-health; `curl http://localhost:8080/app/app.js` → served JS contains the new code (5 matches).
  - End-to-end through nginx: `GET /admin/expert-demo/cases` → 7; `POST /admin/expert-demo/reviews` valid → **201 + change_id**; invalid decision → **422**; cleanup `DELETE 1` (exactly one audit row written). E2E test row removed.
- Acceptance criteria demonstrated: G2-B (expert tab persists via the endpoint; offline/no-key demo path unchanged — admin auth open in demo). Seeded rejection reflected by default. M1 resolved.
- Tests not run and why: **visual/interaction rendering is manual-only** (no FE harness) — the verdict banner, form-reject notice, and submit UX were verified by code + served-JS + the API contract they call, not by a rendered browser session. Recommend a manual click-through of the 審閱 tab (esp. cases 5/6/7) before acceptance. `ruff`/`mypy` N/A (frontend). Neo4j was warming (degraded health) during checks — unrelated to T4.
- Deviations: none beyond the manual-only verification limit above.
- Result: Pass

## T10 — README thesis + walkthrough + doc reconciliation (one-task-at-a-time, docs only)

- Boundary and allowed paths: `README.md`, `docs/**`. No backend/frontend/tests touched.
- Files changed:
  - `README.md` — added "The one idea" thesis block (governance-spine sentence + real-expert career-transition framing) + a six-step "Governance walkthrough (all of it runs)" mapped to real screens/endpoints.
  - `docs/demo-cases-blood-glucose.md` — added Case 6 (form-reject) & Case 7 (meaning-reject) sections; refreshed header (7 cases, implemented) and the overview table (now 7 rows); noted expert-review persistence.
  - `docs/expert-in-the-loop-workflow.md` — case list 5→7 (incl. 6/7) and the `POST /admin/expert-demo/reviews` persistence note.
  - `docs/expert-in-the-loop-plan.md` — status line "尚未實作"→"已實作"; Phase A–C roadmap boxes `[ ]`→`[x]`; added a 2026-07-23 update note (G5 cases + M1, G2 §五.4 read-only→append-only-write reversal, deferred G1/G3/G4/G6).
- Tests added: none (docs). No doc-test/markdownlint harness in repo.
- Container/commands and results: `grep` verification — no stale `[ ]` roadmap boxes or "尚未實作" left; README-cited `POST /admin/expert-demo/reviews` and cases 006/007 exist; demo-cases overview = 7 rows; changed paths ⊆ {README.md, docs/**}.
- Acceptance criteria demonstrated: README-A (thesis + walkthrough describing only what runs); Doc-A (contract already updated in T3; plan/workflow/demo-cases reconciled; §五.4 reversal + new cases recorded).
- Tests not run and why: no automated doc checks exist; accuracy verified by cross-reference grep + careful review. README mermaid untouched.
- Deviations: none. (`docs/agent-guideline.md` shows dirty in the tree = unrelated skill-forge self-heal, not a T10 edit — see review L1.)
- Result: Pass
