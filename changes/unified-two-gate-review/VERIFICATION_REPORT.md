# Verification Report: unified-two-gate-review (Phase 1 walking skeleton)

Covers T1–T5 (group_id migration, group service + two gates, demo seed, review API, Review view).
T7–T9 N/A; Phase 2–5 are roadmap, not this change.

## Environment

- Branch `feat/two-gate-review`, baseline commit `5d9ebae` (the expert-gate-integrity change).
- Phase-1 diff since baseline (excl. unrelated `docs/agent-guideline.md` self-heal): 7 tracked files
  (+396/-1) + 3 new source files (`routes_review.py`, `test_review_groups.py`, `test_review.py`).
- Services up (postgres/neo4j/qdrant/backend/nginx); backend rebuilt before the run (`backend/tests`
  not volume-mounted); backend restarted once to register the new router.
- Offline / open-admin mode (no `OPENAI_API_KEY` / `ADMIN_API_KEYS`), as tests expect.
- Known pre-existing baseline failure: `test_pipeline_run_is_idempotent` (non-pristine Postgres volume).

## Canonical commands

| Command | Exit | Result |
|---|---|---|
| `docker compose build backend` | 0 | image rebuilt |
| `make test` (`pytest tests ingestion/tests`) | 1 | **140 passed, 1 failed** (261s) |
| `ruff check` (7 Phase-1 files, ruff container) | 0 | **All checks passed** |
| `ruff format --check` (7 files) | 0 | **already formatted** |
| `mypy` (5 app/ingestion modules, host) | 0 | **Success: no issues** |

Sole failure: `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent` (`chunk_count 12 != 9`)
— the documented non-pristine-volume flake. **Not caused by this change:** T3's `stage_demo_review_groups`
writes only `curation_items` (never `chunks`) and is idempotent (ON CONFLICT); the test reaches the
chunk-count assert, so `run.run()` incl. the new staging succeeded twice. Excluded by the plan's stop
conditions.

## Requirement → Implementation → Test → Result

| # | Acceptance | Implementation | Evidence | Result |
|---|---|---|---|---|
| A1 | GET returns group w/ live schema gate + understanding | `service.list_groups`, `routes_review.GET` | `test_review::test_list_groups_endpoint_shape` (200, schema_gate=pass, is_gap=False); live curl → group_001 pass + P1 sentence | Pass |
| A2 | Invariant: group nodes absent from graph pre-approve, present post-approve | `approve_group` (Neo4j write + item flip in one pg txn) | **Originally evidenced only by synthetic fixtures** (review H1) — the shipped seed group collided with already-approved ids, so the invariant was a no-op on real data. **Remediated:** seed is now `review_groups.json` (cortisol), and live `GET /nodes/hormone:cortisol` → **404 pre-approval**; fixture test still covers the write | Pass (after remediation) |
| A3 | Reject writes nothing + audit; approve audits | `approve_group`/`reject_group` (`_log_change`) | `test_review_groups` (approve+reject audit rows), `test_review` (approve/reject 200) | Pass |
| A4 | Approve/reject transactional per group (all-or-nothing) | `async with conn.transaction()` around item flips + audit; Neo4j MERGE inside | approve flips all 3 nodes+3 edges together (`{nodes:3,edges:3}`); reject flips all. **Not** failure-injected | Pass (happy-path); see Risks |
| A5 | Review view renders 3 tabs + approve/reject works | `frontend/app.js::renderReview` + T4 endpoints | `node --check` OK; served JS present; endpoints proven live (200). Rendering **manually confirmed by the human owner (jett), 2026-07-24** — not agent-verified | Pass |
| A6 | `make test` green except known flake | — | 140 passed, 1 = known unrelated flake | Pass |

## Read-only / manual observations

- Live through nginx: `GET :8080/admin/review/groups` → 200, returns `group:blood_glucose_case_001`
  (schema_gate `pass`, understanding "胰島素會造成一個調控效果:使血糖下降。"). `make seed` staged
  `demo_review_groups: {blood_glucose_case_001: {nodes:3, edges:3}}`.
- `ensure_schema` run twice → `group_id` column present (text, nullable), idempotent (T1).

## Tests not run / boundaries

- **Frontend rendering/interaction** (A5 UI): no automated FE suite → manual-only. The three-tab render,
  concept map, isolation (no ids in 專家 tab), and the approve/reject buttons need a human browser pass
  (checklist in TASK_LOG). Verified here by code + served JS + the proven live API.
- **A4 rollback path** not fault-injected — the transactional claim rests on `conn.transaction()`
  semantics + happy-path all-or-nothing, not a simulated mid-write failure.
- `make eval` not run — retrieval pipeline untouched.
- Cross-DB atomicity (Neo4j vs Postgres) is bounded — Neo4j MERGEs are idempotent inside the pg txn; a
  Neo4j-success-then-pg-fail window remains (documented; same class as existing `approve_item`).

## Known risks / review hotspots

1. **Frontend UI (highest)** — manual click-through of 群組審閱 (list → Schema gate → 專家審閱 → 核准)
   pending; the one unexecuted surface.
2. **Router-restart gotcha** — new routers need a backend restart (registration at startup); `app/` mount
   alone doesn't re-import `main.py`. Operational note.
3. **Idempotent flake** — "not a regression" argued from the diff (T3 touches only curation_items), not a
   pristine-volume run.
4. **Real-extract grouping deferred** — grouping only exists for seeded demo cases; the real extract path
   still stages per-element (becomes blocking when the real pipeline lands — Phase 5).

## Post-review remediation (2026-07-24)

An independent `review-change` (see `REVIEW_REPORT.md`) found **B1 (blocking)**: the seeded demo group's
node ids already existed as `approved`, so approving would MERGE-overwrite curated labels/descriptions and
add duplicate edges — and the A2 invariant was a no-op on shipped data (**H1**). Confirmed by live probe.
Owner decisions: B1 → *both* new demo data **and** a guard; H2 → *enforcing now, override later*.

Fixes applied and re-verified:

| Finding | Fix | Evidence |
|---|---|---|
| **B1** | New seed source `data/sample/expert_demo/review_groups.json` proposing genuinely new knowledge (cortisol → blood glucose); `approve_group` now **refuses (409)** if any member id already exists approved; re-seeding retires stale demo groups | `GET /nodes/hormone:cortisol` → **404** pre-approval; `test_approve_refuses_when_a_member_already_exists_approved` |
| **H1** | A2 evidence restated (row above); real-data invariant now demonstrable | live probe + report correction |
| **H2** | Schema gate is **enforcing** — `approve_group` returns 409 when `result != 'pass'`; UI disables 核准 and explains why | `test_approve_refuses_when_schema_gate_fails` |
| **M1** | Audit now records full member payloads + `item_ids` + gate result, not bare ids | `test_approve_audit_records_full_payloads` |
| **M2** | New routes raise `APIError` → documented `{"error":{code,message}}` | `test_unknown_group_404_uses_error_contract`, `test_double_approve_409_uses_error_contract` |
| **M3** | 409 covered at service + API; row select moved inside the transaction with `FOR UPDATE` | `test_double_approve_is_409` + api equivalent |
| **L1** | Result banner moved outside the repainted region, so the outcome is visible | code; manual re-check advised |
| **L2** | `approve_group` refuses non-`create` actions (422) | `test_approve_refuses_non_create_action` |
| **S1** | Tab relabelled 提案內容 (no false LLM provenance); `proposed_by` shown | code |
| **S3** | Referenced approved nodes resolve their real labels in the expert lens | live: "使Blood glucose上升" (real graph label, not a humanized id) |

Re-verified: `make test` → **146 passed, 1 failed** (same known unrelated flake); review suites **14 passed**;
ruff/format/mypy clean; `node --check` OK.

**Not fixed (recorded):** A4 fault-injection still absent; `docs/agent-guideline.md` still uncommitted
(unrelated); the seed graph labels concepts in English while demo cases use Chinese, so the lens reads
"使Blood glucose上升" — honest but cosmetically mixed; owner's call.

## Summary

**PASS.** `make test` 140 passed (sole failure = documented unrelated flake); ruff/format/mypy clean; the
group-level two-gate walking skeleton is proven end-to-end through nginx (migration → group service with
both gates → seeded real data → live API), including the approve invariant. **A5 (frontend rendering) was
manually confirmed OK by the human owner (jett) on 2026-07-24** — recorded as a human sign-off, not an
automated result; no FE regression test exists to protect it.

Remaining open (non-blocking, disclosed): A4 not fault-injected; real-extract grouping deferred (Phase 5);
no automated FE coverage. Independent `review-change` was **not** run for Phase 1 — the owner elected to
commit directly. No implementation modified during verification.
