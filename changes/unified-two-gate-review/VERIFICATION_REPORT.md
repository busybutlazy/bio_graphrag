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
| A2 | Invariant: group nodes absent from graph pre-approve, present post-approve | `approve_group` (Neo4j write + item flip in one pg txn) | `test_review_groups::test_approve_group_writes_all_and_audits` (node status `None` → `approved`) | Pass |
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

## Summary

**PASS.** `make test` 140 passed (sole failure = documented unrelated flake); ruff/format/mypy clean; the
group-level two-gate walking skeleton is proven end-to-end through nginx (migration → group service with
both gates → seeded real data → live API), including the approve invariant. **A5 (frontend rendering) was
manually confirmed OK by the human owner (jett) on 2026-07-24** — recorded as a human sign-off, not an
automated result; no FE regression test exists to protect it.

Remaining open (non-blocking, disclosed): A4 not fault-injected; real-extract grouping deferred (Phase 5);
no automated FE coverage. Independent `review-change` was **not** run for Phase 1 — the owner elected to
commit directly. No implementation modified during verification.
