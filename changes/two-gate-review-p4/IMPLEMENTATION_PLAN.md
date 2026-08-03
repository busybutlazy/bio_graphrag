# Implementation Plan: two-gate-review-p4

## Objective

Retire the standalone **`審閱` (expert-demo) screen + `/admin/expert-demo/*` endpoints** — the early
prototype of the two-gate presentation that the unified `群組審閱` (group Review, P1–P3) has
superseded. After P4 the nav is the intended two-page spine: **收錄 (Ingestion) + 群組審閱 (Review)**,
plus the browse/eval tabs. The two-gate **engine** (`engineer_gate`, `back_translation`) and its
regression nets are kept — only the redundant demo surface goes.

Owner decision (2026-08-03): retire/delete (not repurpose as "guided examples").

## In Scope

1. Backend: delete `routes_expert_demo.py`, unregister its router in `main.py`, delete
   `schemas/expert_demo.py` (`ExpertReviewRequest`), remove `service.record_expert_review`.
2. Backend tests: delete `tests/api/test_expert_demo.py` and
   `tests/integration/test_expert_review_log.py` (they test only the retired surface).
3. Frontend: remove the `expert`/`審閱` VIEWS entry, `renderExpertDemo`, and its private helpers
   (`GAP_OPTIONS`, `EXPERT_STORE`, and the function-local `EXPERT_STATUS`/`expertVerdict`).
4. Docs: remove the `GET/POST /admin/expert-demo/*` sections from `docs/api_contract.md`; add a
   one-line retirement note in `docs/expert-in-the-loop-plan.md`.
5. Cache-bust `frontend/index.html` (`?v=`), per [[public-domain-cdn-cache]].

## Out of Scope

- **`data/sample/expert_demo/cases.json` is KEPT** — see Current-State Evidence: it is a shared test
  fixture for the engine/gold suites, not only the endpoint's data. Deleting it would break tests
  that P4 must keep green. It simply stops being a served demo dataset and becomes a pure fixture.
- `data/sample/expert_demo/gold/` and `schema_gap_backlog.json` — kept (gold regression + backlog).
- Renaming the `data/sample/expert_demo/` directory (now a slightly legacy name) — churn, not now.
- The open decision on the **fate of gold + schema-gap backlog** ("guided examples" mode) — remains
  open, tracked in [[unified-two-gate-restructure]] decision #3; P4 keeps them as-is.
- The extract→unified-review work (a separate later change).
- Any change to the group Review, the two-gate engine, or retrieval.

## Current-State Evidence

- Repository state: `main` is at `fe4da9e`; P3 is committed on `feat/two-gate-review-p3`
  (`e69981d` + `504fde4`), **not merged**. **Decision needed (below):** branch P4 off `main` (clean,
  but P4's frontend removal will conflict trivially with P3's `app.js`/`api_contract.md` at merge) or
  off the P3 branch (stacked). Recommended: branch off `main` after P3's PR merges; if P4 starts
  before that, stack on `feat/two-gate-review-p3`.
- Backend refs (grep, `backend/app`): `main.py:11` import + `:67` `include_router`;
  `routes_expert_demo.py` (`GET /expert-demo/cases`, `POST /expert-demo/reviews`);
  `schemas/expert_demo.py::ExpertReviewRequest`; `service.py:83-105 record_expert_review`
  (writes one `graph_change_logs` row, `action='expert_review'`, `target_type='expert_demo_case'`;
  **never** touches Neo4j / approved graph / curation_items). Only `routes_expert_demo` imports
  `ExpertReviewRequest` and calls `record_expert_review`.
- Frontend refs (`frontend/app.js`): VIEWS entry `id:'expert'` (line ~147); `GAP_OPTIONS` (~516),
  `EXPERT_STORE` (~524), `renderExpertDemo` (~526) with local `EXPERT_STATUS`/`expertVerdict`. No
  other view references them.
- **cases.json is a shared fixture** — read by `tests/unit/test_back_translation.py`,
  `tests/unit/test_engineer_gate.py`, and `tests/gold/test_gold_examples.py` (which also reads
  `gold/`). These test the **engine + gold regression** that group Review relies on and MUST stay
  green. Only `tests/api/test_expert_demo.py` and `tests/integration/test_expert_review_log.py` test
  the retired surface.
- `make seed` loads `review_groups.json` (not `cases.json`) via
  `load_postgres.stage_demo_review_groups` — seed is unaffected.
- Baseline: full offline suite `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests
  ingestion/tests` = **167 passed** on P3's tip (the `.env` OPENAI key is credit-exhausted → offline
  is the documented posture). Removing the 2 test files lowers the count by their tests, not by a
  regression.

## Acceptance Criteria

1. `GET /admin/expert-demo/cases` and `POST /admin/expert-demo/reviews` return **404** (routes gone);
   `routes_expert_demo.py`, `schemas/expert_demo.py`, `service.record_expert_review`, and the 2 test
   files no longer exist; `grep -rn "expert_demo\|record_expert_review\|ExpertReview" backend/app`
   returns nothing (comments aside).
2. Engine + gold suites **still pass** (`test_back_translation`, `test_engineer_gate`,
   `test_gold_examples`) — `cases.json`/`gold/` kept.
3. Frontend: the `審閱` tab is gone; nav = `問答 / 圖譜 / 典藏 / 收錄 / 群組審閱 / 評估`;
   `grep "renderExpertDemo\|GAP_OPTIONS\|EXPERT_STORE\|id: 'expert'"` returns nothing;
   `node --check frontend/app.js` clean; `index.html` `?v=` bumped.
4. `docs/api_contract.md` no longer documents `/admin/expert-demo/*`.
5. Full offline suite green; ruff 0.15.21 check+format clean; `mypy backend/app ingestion scripts`
   clean.

## Contract, Schema, Dependency, and Migration Impact

- **Contract:** *removal* — `/admin/expert-demo/cases` + `/admin/expert-demo/reviews` are deleted.
  Deliberate deprecation of a demo-only surface with no consumer besides the retired screen. This is
  an approved scope item (owner chose retire), but note it as the one **stop-condition-adjacent**
  point: removing published endpoints. No other endpoint changes.
- **Schema/DB:** none. `graph_change_logs` is generic; removing the only writer of
  `action='expert_review'` needs no migration; any existing such rows remain valid history.
- **Dependency / Migration:** none.

## Execution Policy

- Plan revision: 2 (Approved — supervised-auto)
- Risk level: **medium** (removes published endpoints + a screen; mechanical, well-fenced by tests;
  no migration/dependency)
- Automation mode: **supervised-auto** (owner-approved 2026-08-03).
- Auto-approved task IDs (`supervised-auto`): **T1, T2** — execute continuously within the approved
  path scope below, stopping only at the mandatory stop conditions or the T1→T2 checkpoint if the
  suite is not green.
- Approved file/path scope: `backend/app/main.py`, `backend/app/api/routes_expert_demo.py` (delete),
  `backend/app/schemas/expert_demo.py` (delete), `backend/app/curation/service.py`,
  `backend/tests/api/test_expert_demo.py` (delete), `backend/tests/integration/test_expert_review_log.py`
  (delete), `frontend/app.js`, `frontend/index.html`, `docs/api_contract.md`,
  `docs/expert-in-the-loop-plan.md`, `changes/two-gate-review-p4/*`.
- Human checkpoints: after T1 (backend+docs, suite green) before T2; browser pass of the nav after T2.
- Mandatory stop conditions: any need to touch the two-gate engine, `cases.json`/`gold/`, a
  migration, a dependency, or endpoints beyond `/admin/expert-demo/*`; unexplained worktree changes;
  a failing engine/gold test.
- Commit/push permission: **No unless separately approved after review.**

## Tasks

### Task 1 — Backend + docs removal

- Files: delete `routes_expert_demo.py`, `schemas/expert_demo.py`,
  `tests/api/test_expert_demo.py`, `tests/integration/test_expert_review_log.py`; edit `main.py`
  (drop the import + `include_router`); edit `service.py` (remove `record_expert_review`); edit
  `docs/api_contract.md` (remove the two expert-demo sections) + `docs/expert-in-the-loop-plan.md`
  (one-line retirement note).
- Verify: `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests` green
  (engine + gold pass; the 2 deleted test files simply gone); after a backend restart,
  `curl /admin/expert-demo/cases` → 404. ruff + mypy clean. `grep` for backend refs is empty.
- Stop/handoff: backend green before the frontend.

### Task 2 — Frontend removal + cache-bust

- Files: `frontend/app.js` (remove the `expert` VIEWS entry + `renderExpertDemo` + `GAP_OPTIONS` +
  `EXPERT_STORE`), `frontend/index.html` (bump `?v=`).
- Verify: `node --check frontend/app.js`; `grep` for the removed symbols is empty; served nav (via
  nginx) shows no `審閱`. Owed: human browser pass that every remaining tab still routes with no
  console error, and the `#expert` hash falls back to `chat`.
- Stop/handoff: produce verification + change reports.

## Verification Strategy

- Normal: full offline suite green; engine/gold tests explicitly pass.
- Failure/contract: `curl` both retired endpoints → 404 (after restart).
- Compatibility: `make seed` still works (loads `review_groups.json`, not `cases.json`); group
  Review + Ingestion unaffected.
- Security: no auth surface changes; one fewer admin route.
- Dead-code: `grep` sweeps confirm no dangling refs to the removed symbols in either language.
- Commands (Docker only): `pytest tests ingestion/tests`; ruff `ghcr.io/astral-sh/ruff:0.15.21`;
  `mypy backend/app ingestion scripts`; `node --check`.

## Risks and Unknowns

- **Branch/stacking** (above): P4 vs the unmerged P3 branch. If P4 stacks on P3, a later P3 squash-
  merge needs a rebase. Recommended: merge P3 first, branch P4 off `main`.
- **cases.json coupling** (resolved): kept as a fixture; if a future change wants the
  `expert_demo/` name gone, that's a separate rename touching 3 test imports.
- Frontend has **no test harness** — nav removal is verified by `node --check` + grep + a human pass.

## Rollback

`git revert` the change (or delete the branch). No migration, no data deletion (`cases.json`/`gold/`
never removed). Re-adding the router + screen restores the demo surface verbatim.

## Human Decisions and Approval

- Decisions — RESOLVED (owner, 2026-08-03):
  1. **cases.json STAYS** as a test fixture (it still backs `test_back_translation` /
     `test_engineer_gate` / `test_gold_examples`). "Retire" = remove screen + endpoints +
     `record_expert_review`, NOT the fixture data.
  2. **Branch base = `main`** — P3 merged (PR #12, `c64163b`); P4 branched off `main` as
     `feat/two-gate-review-p4`.
  3. Risk **medium**, mode **supervised-auto** approved.
- Status: **Approved (revision 2) — supervised-auto**
- Approved by/date: owner, 2026-08-03
- Approval evidence: recorded in-session; the three decisions above are the approval. Material
  further changes re-invalidate approval.
