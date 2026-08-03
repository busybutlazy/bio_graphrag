# Task Log: two-gate-review-p4

Plan revision **2** (Approved, supervised-auto, medium). Branch `feat/two-gate-review-p4` off `main`
(`c64163b`, P3 merged via PR #12). Baseline: full offline suite 167 passed on P3 tip. Approved tasks
T1, T2. Decisions: cases.json KEPT (test fixture); off main; supervised-auto.

## Task 1 — Backend + docs removal (in progress)

Remove: `routes_expert_demo.py`, `schemas/expert_demo.py`, `service.record_expert_review`, the two
retired-surface tests; unregister router in `main.py`; strip expert-demo from `api_contract.md`; add
a retirement note in `expert-in-the-loop-plan.md`. cases.json/gold KEPT.

**T1 done.** Deleted `backend/app/api/routes_expert_demo.py`, `backend/app/schemas/expert_demo.py`,
`backend/tests/api/test_expert_demo.py`, `backend/tests/integration/test_expert_review_log.py`;
removed the import + `include_router` in `main.py`; removed `record_expert_review` from `service.py`;
removed the two `/admin/expert-demo/*` sections from `api_contract.md`; added a retirement note in
`expert-in-the-loop-plan.md`. `grep` for backend refs → none. ruff clean; mypy 77 files clean.
Rebuilt image; full offline suite **162 passed** (167−5 deleted; engine/gold still pass on the kept
`cases.json` fixture). After restart: `GET /admin/expert-demo/cases` + `POST .../reviews` → **404**;
`GET /admin/review/groups` → **200**.

## Task 2 — Frontend removal + cache-bust — done

Removed from `frontend/app.js`: the `expert`/`審閱` VIEWS entry, the EXPERT REVIEW comment block,
`GAP_OPTIONS`, `EXPERT_STORE`, and `renderExpertDemo` (with its local `EXPERT_STATUS`/`expertVerdict`);
updated one stale comment in `renderReview` that referenced the retired screen. Bumped
`frontend/index.html` `?v=20260803-3`. `node --check` OK; `grep` for removed symbols → no code refs;
served nav = `問答 / 圖譜 / 典藏 / 收錄 / 群組審閱 / 評估` (no `審閱`).

## Verification (evidence-only)
ruff 0.15.21 check exit 0 + format clean (99 files); `mypy backend/app ingestion scripts` success
(77 files); full offline suite **162 passed** (exit 0); `node --check` OK; expert-demo 404 / review
200. No implementation edits during verification.

## Stop
All approved tasks complete + full verification passed. Handing to review/human. **Not committed.**
