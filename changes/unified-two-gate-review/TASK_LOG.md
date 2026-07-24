# Task Log: unified-two-gate-review (Phase 1)

- Plan revision: 1 (Approved)
- Approval evidence: IMPLEMENTATION_PLAN.md §Human Decisions — user (jett) 2026-07-24; one-task-at-a-time.
- Risk level: HIGH
- Automation mode: one-task-at-a-time
- Baseline: committed the working `expert-gate-integrity` change as branch baseline on `feat/two-gate-review`
  (`5d9ebae`), excluding the unrelated `docs/agent-guideline.md` self-heal. Tree clean apart from that file
  + the untracked `changes/unified-two-gate-review/` plan dir. Known pre-existing flake:
  `test_pipeline_run_is_idempotent` (non-pristine volume).

## T1 — add `group_id` to `curation_items` (migration)

- Boundary and allowed paths: `ingestion/pipeline/{schema.sql, load_postgres.py}` only.
- Files changed:
  - `ingestion/pipeline/schema.sql`: added `group_id TEXT,` to the `curation_items` CREATE TABLE.
  - `ingestion/pipeline/load_postgres.py`: added `_MIGRATION_ADD_GROUP_ID`
    (`ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS group_id TEXT;`) executed in `ensure_schema`,
    mirroring the existing `_MIGRATION_ADD_SCHEMA_CHECK` precedent.
- Tests added: none (schema migration; verified by column-existence check + regression).
- Container commands and results:
  - Ran `ensure_schema` twice in the backend container (idempotency), then queried
    `information_schema.columns` → `group_id -> {'data_type': 'text', 'is_nullable': 'YES'}`. Exit 0.
  - Regression: `docker compose run --rm backend pytest tests/integration/test_curation.py -q` →
    **5 passed** (0). Additive nullable column, existing per-element flow unaffected.
- Acceptance criteria demonstrated: A-precondition for group review — `curation_items` can carry a
  `group_id`; idempotent for fresh + existing DBs; backward-compatible (NULL = legacy item).
- Tests not run and why: `ruff`/`mypy` not in backend image (host-only); the changes are SQL + a string
  constant — deferred to full verify/CI. No frontend/backend-app logic touched.
- Deviations: None.
- Result: Pass — **checkpoint: stop for human before T2.**

## T2 — group assembly + two gates + transactional approve/reject (service)

- Boundary and allowed paths: `backend/app/curation/service.py`, `backend/tests/integration/**`.
- Files changed:
  - `service.py`: imports `engineer_gate.evaluate` (as `evaluate_schema_gate`) + `back_translation`;
    added `_proposal_from_items` (assemble grouped items → `{proposed_nodes, proposed_edges}`, **stripping
    the curation `status` key** so payloads pass `extraction_output_schema` additionalProperties:false),
    `list_groups` (schema_gate + understanding computed live, cross-group ctx), `approve_group`
    (Neo4j write of all members + item flips + one `approve` audit row, inside one pg transaction so a
    Neo4j failure aborts the commit; Neo4j writes are idempotent MERGEs), `reject_group` (item flips +
    `reject` audit, no Neo4j).
  - Added `backend/tests/integration/test_review_groups.py` (4 tests).
- Container commands and results:
  - `docker compose run --rm backend pytest tests/integration/test_review_groups.py -q` → **4 passed**.
    Covers: list assembly (schema_gate=pass, understanding non-gap), approve writes all 3 nodes+3 edges +
    invariant (Neo4j node absent before approve, `approved` after) + audit row, reject writes nothing +
    audit, missing group → 404.
  - Regression: `pytest tests/integration/test_curation.py -q` → **5 passed** (shared service intact).
  - `ruff check` + `ruff format --check` (ruff container) → clean. `mypy backend/app/curation/service.py`
    (host) → **Success: no issues** (added list annotations).
- Acceptance criteria demonstrated: A1 (assembly + live gates), A2 (invariant via approve), A3 (audit rows
  on approve+reject), A4 (per-group pg-transactional flips). A5/A6 pending later tasks/full verify.
- Tests not run and why: mypy not in backend image → run on host. Full `make test` deferred to change-wide
  verify.
- Deviations: cross-DB atomicity is bounded — Neo4j writes are idempotent MERGEs inside the pg transaction;
  a Neo4j-success-then-pg-commit-fail window remains (same risk class as existing `approve_item`, actually
  tighter). Documented in the function docstring.
- Result: Pass — **checkpoint: stop for human before T3 (seed).**

## T3 — seed one demo proposal group

- Boundary and allowed paths: `ingestion/pipeline/{load_postgres.py, run.py}`.
- Files changed:
  - `load_postgres.py`: import `parse_source`; added `stage_demo_review_group` (stage a candidate
    {nodes,edges} as proposed curation_items sharing a group-scoped `item_id` + `group_id` +
    per-element `schema_check`, `proposed_by='demo'`, idempotent ON CONFLICT) and
    `stage_demo_review_groups` (read `data/sample/expert_demo/cases.json`, stage selected cases as
    one group each, `group_id=group:<case_id>`).
  - `run.py`: after `upsert_chunks`, seed `["blood_glucose_case_001"]` and record it in job stats.
- Container commands and results:
  - `make seed` → `status: success`, `stats.demo_review_groups: {blood_glucose_case_001: {nodes:3,
    edges:3}}`.
  - Verify via `service.list_groups()` in container → `group:blood_glucose_case_001`: 3 nodes / 3 edges,
    `schema_gate=pass`, `understanding.is_gap=False` / text "胰島素會造成一個調控效果:使血糖下降。",
    `proposed_by=demo`.
  - `ruff check` + `ruff format --check` → clean; `mypy` (host) → **Success**.
- Acceptance criteria demonstrated: T3 precondition for A1 — a seeded proposed group is listed with a
  live passing schema gate + correct P1 understanding. Idempotent (group-scoped item_ids + ON CONFLICT).
- Tests not run and why: no dedicated unit test added (seed path verified live end-to-end; the group
  service logic is covered by T2's `test_review_groups`). Full `make test` deferred to change-wide verify.
- Deviations: None. Phase-1 scope = Case 1 only (rest is P2).
- Result: Pass — **checkpoint: stop for human before T4 (API + contract).**

## T4 — review endpoints (API + contract)

- Boundary and allowed paths: `backend/app/api/routes_review.py` (new), `backend/app/main.py`,
  `docs/api_contract.md`, `backend/tests/api/test_review.py` (new). Reused `ApproveRejectRequest`
  from `schemas/curation.py` (no new schema).
- Files changed:
  - `routes_review.py`: admin router — `GET /admin/review/groups` → `service.list_groups`;
    `POST /admin/review/groups/{id}/approve|reject` → `service.approve_group/reject_group`, mapping
    `CurationError` → `HTTPException` (mirrors curation routes).
  - `main.py`: import + `include_router(review_router)`.
  - `api_contract.md`: documented the three review endpoints (shape, 201/200 bodies, side effects,
    404/409).
  - `test_review.py`: 4 tests (list shape, approve 200, reject 200, unknown → 404).
- Container commands and results:
  - `docker compose run --rm backend pytest tests/api/test_review.py -q` → **4 passed**.
  - Restarted backend (`docker compose up -d backend`) to load the new router; live
    `curl :8080/admin/review/groups` → returns `group:blood_glucose_case_001` (schema_gate `pass`,
    understanding "胰島素會造成一個調控效果:使血糖下降。") through nginx.
  - `ruff check` + `ruff format --check` → clean; `mypy routes_review.py main.py` → **Success**.
- Acceptance criteria demonstrated: A1 (GET returns group + live gates), A3 (approve/reject 200 + audit
  via service), boundary (unknown → 404). Full invariant (A2) covered by T2.
- Tests not run and why: mypy on host; full `make test` deferred to change-wide verify.
- Deviations: the long-running nginx-fronted backend needed a restart to register the new router (router
  registration is at startup; `app/` volume mount alone doesn't re-import). Noted for future router adds.
- Result: Pass — **checkpoint: stop for human before T5 (frontend Review view).**

## T5 — minimal Review frontend view

- Boundary and allowed paths: `frontend/app.js` only (reused existing `.ex-*`/`.btn` CSS — no CSS change).
- Files changed: `frontend/app.js` — added a `review` VIEWS entry (label 群組審閱; the old `expert`
  view stays until P4) + `renderReview`: lists groups from `GET /admin/review/groups`; per group three
  tabs (AI 提案 raw / Schema gate checks / 專家審閱 = understanding + concept map, no id/JSON —
  isolation preserved); 核准並寫入 / 退回 buttons POST to the T4 approve/reject endpoints and refresh.
  Reused module helpers `E/clear/typeColor/nodeTypeLabel/phraseRelation/forceLayout/svgEl`.
- Container/commands and results:
  - `node --check frontend/app.js` → OK.
  - Served JS (`curl :8080/app/app.js`) contains `renderReview` / 群組審閱 / `admin/review/groups`
    (9 matches) — frontend is live-mounted, no rebuild.
  - Endpoint sanity: `GET :8080/admin/review/groups` → 200 (the endpoints renderReview calls are proven
    live in T4).
- Acceptance criteria demonstrated: A5 wiring — the three-tab Review view is served and calls the proven
  endpoints. **Visual/interaction rendering is manual-only** (no FE harness) — needs a human browser
  click-through (checklist below).
- Tests not run and why: no automated FE suite exists; verified by syntax + served JS + the live API it
  calls, not a rendered browser session.
- Deviations: None. `expert` view intentionally retained this phase (retired in P4).
- Result: Pass — **Phase 1 tasks (T1–T5) complete → hand to change-wide verify-change.**

## Manual UI checklist — **CONFIRMED OK by human owner (jett), 2026-07-24**

Human ran the click-through and reported the Review view working. Recorded as a human sign-off (no
automated FE coverage protects it). Original checklist:

At `http://localhost:8080/` → 群組審閱 tab:
1. Left list shows one group whose text is "胰島素會造成一個調控效果:使血糖下降。" with a 通過 badge. → [ ]
2. Schema gate tab: overall 通過 + per-check ✓ rows. → [ ]
3. 專家審閱 tab: the understanding sentence + a concept map, **no ids/JSON**. → [ ]
4. Click 核准並寫入 → message "已核准並寫入知識圖譜(nodes 3 / edges 3)"; group leaves the list. Then
   the 圖譜/typeahead should find `hormone:insulin` as approved. (Or 退回 on a re-seed → "已退回".) → [ ]

(Re-seed a fresh group with `make seed` if you consumed it.)
