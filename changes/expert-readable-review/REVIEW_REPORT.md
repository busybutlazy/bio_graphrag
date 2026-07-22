# Review Report: expert-readable-review

## Review Context

- **Diff base and scope**: `main` (merge-base `2de60c7`) → `HEAD` (`feat/expert-readable-review`, tip `bc666dc`). 31 files, +2005/-40. Change delivers Part 1 (curation-page 白話化, frontend-only), Part 2 (Phase B engines: `back_translation.py` / `engineer_gate.py` + gold + backlog), Part 3 (Phase C: read-only `GET /admin/expert-demo/cases` endpoint + `renderExpertDemo` three-tab UI + docs).
- **Artifacts reviewed**: IMPLEMENTATION_PLAN (r1, Approved), CHANGE_REPORT, VERIFICATION_REPORT, TASK_LOG, full attributable diff, all new tests, `cases.json` data, `extraction_output_schema.json`, `validate_extraction.py`, `main.py` handlers, `api_contract.md` diff. Re-ran the change-scoped test suites in the backend container.
- **Independence disclosure**: This review ran in a **fresh session** that did not implement the change. Independence is adequate. I did not run the full `make test` (260s); I re-ran the four change-scoped suites and inspected the rest statically.

## Completion Claim Assessment

The claim — "all 13 ACs met; 19 new tests green; one pre-existing unrelated full-suite failure; nothing committed of the code change; governance invariants preserved" — **largely holds under adversarial checking**:

- Re-ran `pytest tests/api/test_expert_demo.py tests/unit/test_back_translation.py tests/unit/test_engineer_gate.py tests/gold/test_gold_examples.py` → **19 passed** (matches claim). Tests are substantive, not tautological: they assert exact 白話 output strings, gap detection, and per-case gate results (`engineer_gate.py:67`, `test_back_translation.py:27-55`, `test_gold_examples.py:44-46`).
- **AC5 (approve/reject payload unchanged)**: verified by diff — `submit()` and `decide()` bodies are untouched (`git diff` shows no `-` lines on `curation/items`, `reviewer`, or the POST payloads). Confirmed.
- **Governance invariants preserved**: the new endpoint (`routes_expert_demo.py`) only reads a committed JSON file and computes pure functions; it performs **no Neo4j write, no new Cypher, no approved-graph mutation, no schema/type change**. The `status='approved'` retrieval invariant is untouched. No new arbitrary-Cypher/bulk-export endpoint. Confirmed.
- **Error contract & auth**: router is mounted under `prefix="/admin"` with `Depends(require_admin)` (consistent with other `/admin/*`); unhandled errors (e.g. missing `cases.json`) fall through the generic `Exception` handler in `main.py:39` that returns the `{error:{code,message}}` shape. Confirmed.
- **Referential-integrity concern investigated and cleared**: Cases 2/3/4 have edges pointing at `references_existing` nodes not present in `proposed_nodes`. I checked whether the reused `validate_extraction_output` would reject these — it only runs jsonschema shape validation (`validate_extraction.py:10`, schema has no endpoint-in-nodes constraint), so Cases 1–4 legitimately reach `pass`. Not a defect.
- **Case 5 classification traced**: it has empty `proposed_edges`, so `_pattern_check` finds no local RE/Interaction to fault (`fail_pattern` not raised); `render_understanding` returns `is_gap=True`; `_decide` precedence (`fail_schema→fail_pattern→needs_schema_extension→fail_testability`) correctly yields `needs_schema_extension`. Correct.

## Findings

### Blocking
None.

### High
None.

### Medium

**M1 — Full test suite is not green; "unrelated" attribution is by inspection, not demonstration.**
- Evidence: CHANGE_REPORT / VERIFICATION_REPORT / TASK_LOG all record `make test` → `124 passed, 1 failed`, the failure being `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent` (`chunk_count 12 != 9`).
- Risk/requirement: AC13 asks for `make test` 全綠. The delivered state does not meet that literally.
- Impact: Low in practice — the failure is a whole-table row-count assertion against a non-pristine shared Postgres volume, corroborated independently by the project memory note *known-flaky-idempotent-pipeline-test* and by the diff scope (this change adds **no** chunks and touches **no** ingestion/pipeline code). I did not independently reproduce a pass on a pristine volume, so attribution rests on inspection.
- Remediation direction: accept as a known pre-existing environmental flake (recommended), OR, separately from this change, make the idempotent test scope its count to the sample source rather than the whole table. Do **not** fold that fix into this change's scope.

### Low

**L2 — Out-of-approved-path edits.** `frontend/index.html` (`?v=-1`→`-3` cache-bump) and `docs/agent-guideline.md` (272-line doc, separate commit `bc666dc`) are outside the IMPLEMENTATION_PLAN approved path scope. The index.html bump is disclosed in TASK_LOG as a user-approved cache fix and is harmless (version string only, verified by diff). `docs/agent-guideline.md` is unrelated to this change and rides along on the branch. Remediation: confirm both are intended to land with this change; consider splitting the agent-guideline doc if the branch is meant to be single-purpose.

### Suggestion

**S3 — Tab3 isolation had two latent (not currently triggered) leak paths. — RESOLVED (post-review, 2026-07-22).** AC12 requires the expert tab to show no id/JSON/schema/gap code. (a) `conceptMap` fell back to `shortId(id)` when a referenced node is unresolved (`app.js:799`) — not triggered by the current 5 cases (all references resolve via `globalNodes`), but it was an id-shaped fallback rendered on the isolated tab. (b) Case 5's `system_understanding.text` contained the English word "schema" ("…既有 schema 完整表達…", `back_translation.py:122`) — prose, not a code, but borderline against a strict reading of AC12.
- **Fix applied**: (a) the unresolved fallback now renders the neutral 中文 label `（相關概念）` instead of `shortId(id)`; (b) the P5 gap sentence is now pure 中文 — `系統目前無法用既有的知識結構完整表達此現象。`. The gold baseline (`blood_glucose_case_005.json`), `docs/expert-in-the-loop-plan.md`, and `docs/demo-cases-blood-glucose.md` were synced to the new sentence to keep the exact-string gold assertion green. The four change-scoped suites re-run clean (**19 passed**).

**S4 — `nodeLabelCache` is module-level and never invalidated** (`app.js:509`). Within a session, a label edited/merged after first fetch stays stale in the curation queue. Demo-scope, negligible.

## Requirement and Test Coverage Gaps

- ACs 1–4, 12 (all **frontend** presentation/isolation) have **no automated tests** — the repo has no JS test harness. They rest on manual CP1/CP3 visual acceptance, which TASK_LOG/CHANGE_REPORT both record as **still pending human**. I verified the DOM-construction logic by reading `renderCuration`/`renderExpertDemo`, but cannot certify the rendered visual result.
- Backend ACs 7–11 are well covered (exact-string and per-case assertions; live endpoint tested via `TestClient`).

## Compatibility, Security, and Scope Assessment

- **Backward compatibility**: additive only. New endpoint on a new path; new view appended to `VIEWS`; curation write-path untouched (AC5 confirmed). Rollback is clean per the plan (remove one `include_router` line + one VIEWS entry + revert two frontend files).
- **Security/governance**: no new injection surface — node/edge types are **not** interpolated into Cypher here (the endpoint never writes); type whitelists are reused read-only in the gate. Auth consistent with existing `/admin/*`. Read-only, no secret access, offline-deterministic (zero tokens).
- **Contract**: `GET /admin/expert-demo/cases` is documented accurately in `api_contract.md` (read-only, auth, computed fields, result enum). The plan's CP2 (contract checkpoint) was folded into the「先繼續」authorization per CHANGE_REPORT — a human should confirm that authorization covered the contract addition.

## Unreviewed Areas and Residual Risk

- Did not run full `make test` or `make eval` myself; relied on the change's reports plus a re-run of the four change-scoped suites (19 passed, reproduced).
- Did not visually run the app (CP1/CP3) — frontend presentation/isolation ACs remain human-verifiable only. Residual risk concentrated there.
- The pre-existing idempotent-pipeline failure was not reproduced on a pristine volume; attribution accepted on inspection + corroborating memory note.

## Human Disposition Required

The reviewer does not approve, fix, merge, or release this change. Recommended human actions before merge: (1) decide disposition of **M1** (accept known flake vs. defer a separate test fix); (2) confirm **L2** out-of-scope edits are intended to land here; (3) complete the pending **CP1/CP3** visual acceptance of the 審訂 and 審閱 pages, since ACs 1–4/12 have no automated coverage; (4) confirm the「先繼續」authorization was understood to cover the API-contract addition (CP2).

## Post-Review Remediation Log

- **2026-07-22 — S3 addressed** (see finding above): two AC12 isolation edits + gold/doc string sync; 19 change-scoped tests re-run green. Files touched after the reviewed tip `bc666dc`: `frontend/app.js`, `backend/app/graph/back_translation.py`, `data/sample/expert_demo/gold/blood_glucose_case_005.json`, `docs/expert-in-the-loop-plan.md`, `docs/demo-cases-blood-glucose.md`. These are **not yet committed** — the reviewed diff stat (31 files, +2005/−40) still reflects tip `bc666dc`.
- **S4** (`nodeLabelCache` staleness) and **M1** (pre-existing idempotent-pipeline flake): accepted as-is per the reviewer's demo-scope / known-flake rationale; no code change.
