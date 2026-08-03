# Implementation Plan: two-gate-review-p3

## Objective

P3 of the unified two-gate governance restructure: build the **propose** side. Merge the two
existing propose surfaces (`解析` LLM-extract + `審訂` hand-made form) into one **Ingestion**
page with a **[LLM 抽取] ↔ [人工建構]** toggle, and make the **hand-made path produce a
`group_id` proposal group** (a nodes+edges *statement*) that flows into the existing P2 group
**Review** queue and can be approved end-to-end. This closes the propose→dispose loop for the
hand-made path.

Approved decisions (human, 2026-08-01, via plan-change AskUserQuestion):
- **Scope = A2** — UI merge + hand-made path wired through to group Review. LLM-extract
  per-group staging stays **P5** (extract still stages ungrouped per-item; unchanged here).
- **Grouping model = statement builder** — one submission = 1+ concepts + 0+ relations sharing
  one `group_id`, matching D7 (statement-level review) and the `{proposed_nodes, proposed_edges}`
  shape both gates already consume.
- **Nav consolidation = hide legacy per-item queue, keep endpoints** — remove the `審訂` per-item
  approve/reject queue UI (superseded by group Review); keep `/admin/curation/*` endpoints intact;
  `審閱` (expert-demo) retires in **P4**, not here.

## In Scope

1. Backend: `service.create_group(...)` — stage a multi-element hand-made group as `proposed`
   `curation_items` sharing a `group_id`, each element validated against the type whitelists.
2. Backend: `POST /admin/curation/groups` endpoint (admin-gated, `{"error":{code,message}}`
   contract) + `CurationGroupCreate` schema with request limits.
3. Frontend: rework the `解析` tab into an **Ingestion** page hosting the
   `[LLM 抽取] ↔ [人工建構]` toggle; the LLM sub-view is the current renderIngest content
   unchanged; the hand-made sub-view is a **statement builder** posting to the new endpoint.
4. Frontend: remove the `審訂` (`curation`) tab from nav (legacy per-item queue UI retired).
5. Docs: add the new endpoint to `docs/api_contract.md`.
6. Backend tests for the new endpoint + guard behavior; `make test` green.

## Out of Scope

- LLM-extract per-group staging (extract path keeps staging ungrouped per-item) — **P5**.
- Retiring `/admin/expert-demo/*` + the `審閱` tab — **P4**.
- Removing/renaming `/admin/curation/*` single-item endpoints or `create_item` — kept for
  compatibility and existing tests.
- Any change to the group **Review** dispose logic (`approve_group`/`reject_group`/`list_groups`)
  beyond consuming the newly-grouped hand-made items — the P2 surface is reused as-is.
- Auth model, retrieval, schema migrations.

## Current-State Evidence

- Repository state: on `main` at `fe4da9e` (P2 merged, PR #11). Clean except untracked
  `docs/implementation-audit-2026-07-31.md` (unrelated, left alone). **A new branch off `main`
  is required before any commit** (governance: no commits on main).
- Relevant files and symbols:
  - `backend/app/curation/service.py` — `create_item` (single, `proposed_by='human'`, no
    group_id, no graph log at propose time); `_validate_curation_payload` (422 on non-whitelist
    type — the injection guard); `list_groups` (filters `group_id IS NOT NULL AND
    status='proposed'`, **proposed_by-agnostic**, computes `evaluate_schema_gate` +
    `render_understanding` **live**, surfaces `possible_schema_gap` from members'
    `schema_check.group_possible_schema_gap`); `approve_group` (B1 guard rejects 409 if any
    member id already approved).
  - `ingestion/pipeline/load_postgres.py::stage_demo_review_group` — the model for grouped
    staging (shared `group_id`, per-item `schema_check`, item_id `curation:{group_id}:{elem_id}`,
    gap flag stashed in `schema_check`). This is the seed-only precedent; the new method is its
    API-driven sibling living in `service.py`.
  - `backend/app/api/routes_review.py` — `_as_api_error` + `{"error":{code,message}}` pattern to
    mirror for the new endpoint.
  - `backend/app/api/routes_curation.py` — legacy single-item routes (raise HTTPException →
    `{"detail"}`); left unchanged.
  - `backend/app/schemas/curation.py` — `CurationItemCreate`, `ApproveRejectRequest`.
  - `frontend/app.js` — nav `VIEWS` (line ~137); `renderIngest` (~line 476-onwards, options/
    preview/run); `renderCuration` (~529, propose form + legacy per-item queue).
  - `docs/api_contract.md` §3 (Admin/Curation) + §(203+) group-review endpoints.
- Existing behavior and baseline tests: `make test` = 154 passed, 1 known unrelated
  idempotent-pipeline flake (documented). `backend/tests/integration/test_review_groups.py`
  covers list/approve/reject; `test_curation.py` covers single-item create/approve.

## Acceptance Criteria

1. `POST /admin/curation/groups` with `{proposed_nodes:[…], proposed_edges:[…], reason}` stages
   one group; **GET `/admin/review/groups` then lists it** with a live Schema gate + expert lens.
2. Approving that group via `POST /admin/review/groups/{id}/approve` writes its nodes/edges into
   the approved graph (round-trip verified); the **B1 guard** returns `409` if a proposed node id
   already exists as approved.
3. Validation (all `422`, contract `{"error":{code,message}}`): element `type` not in whitelist;
   empty group (0 nodes and 0 edges); element count over the configured cap.
4. `possible_schema_gap: true` → the listed group carries the flag and the gate branches to
   `needs_schema_extension` (D5), matching the seeded schema-gap group's behavior.
5. Frontend: the Ingestion page shows a working `[LLM 抽取] ↔ [人工建構]` toggle; the LLM
   sub-view behaves exactly as today; the hand-made statement builder submits a group and, on
   success, that group is visible in `群組審閱`.
6. The `審訂` tab is gone from nav; `/admin/curation/*` endpoints still respond (existing
   `test_curation.py` stays green).
7. `make test` green (+ the one known flake); ruff + format + mypy clean.

## Contract, Schema, Dependency, and Migration Impact

- **Contract:** *additive* — new `POST /admin/curation/groups`. No existing endpoint's
  request/response/error shape changes. `docs/api_contract.md` updated in the same change.
- **Schema/DB:** none. `group_id` column already exists (P1 `_MIGRATION_ADD_GROUP_ID`). New rows
  only.
- **Dependency:** none.
- **Migration:** none.

## Execution Policy

- Plan revision: 2 (Conditionally Approved — 5 conditions folded in)
- Risk level: **medium** (new write endpoint touching the type-whitelist injection guard; no
  migration, no contract break, additive only)
- Automation mode: **one-task-at-a-time** (recommended — T1 touches the injection-guard path and
  T2/T3 need a human browser pass; supervised-auto buys little here)
- Auto-approved task IDs (`supervised-auto` only): n/a
- Approved file/path scope: `backend/app/curation/service.py`, `backend/app/schemas/curation.py`,
  `backend/app/api/routes_curation.py`, `frontend/app.js`, `docs/api_contract.md`,
  `backend/tests/integration/test_review_groups.py` (+ `test_curation.py` if needed),
  `changes/two-gate-review-p3/*`.
- Human checkpoints: after T1 (backend + tests green) before frontend; browser pass of the
  Ingestion page + statement builder after T2/T3.
- Mandatory stop conditions: any need to alter an approved contract/endpoint shape, a DB
  migration, a new dependency, unexplained worktree changes, or a failing required test.
- Commit/push permission: **No unless separately approved after review.**

## Tasks

### Task 1 — Backend: grouped hand-made propose endpoint

- Files/symbols: `service.create_group()` (new); `CurationGroupCreate` (new,
  `schemas/curation.py`); `POST /admin/curation/groups` (new, `routes_curation.py`, using an
  `_as_api_error`-style `CurationError → APIError` map so it emits `{"error":{code,message}}`).
- Implementation:
  - `create_group(proposed_nodes, proposed_edges, reason, possible_schema_gap=False,
    proposed_by='human') -> dict`: generate `group_id = f"group:{proposed_by}:{uuid4()}"`;
    `_validate_curation_payload` each element (422 on bad type/id — reuses the injection guard);
    require ≥1 element total (else 422); in one transaction insert each with shared `group_id`,
    `status='proposed'`, `action='create'`, item_id `curation:{group_id}:{elem_id}`, and
    `schema_check = {"group_possible_schema_gap": true}` when flagged else `{}` (mirrors the demo
    flag mechanism; the *live* gate in `list_groups` does the real evaluation). No
    graph_change_logs row at propose time — consistent with existing `create_item` (logging
    happens on approve/reject). Return `{group_id, nodes, edges}`.
  - **Duplicate-id guard (condition 3):** before insert, reject `422` if any element id repeats
    within the submission — across the *combined* node+edge id set (node/node, edge/edge, and
    node↔edge collision), since item_id is `curation:{group_id}:{elem_id}` and a repeat would
    otherwise hit a PK collision mid-transaction. Explicit up-front check with a clear message.
  - **Fixed element cap (condition 1):** named module constant `MAX_GROUP_ELEMENTS = 20`; the
    schema validator caps `len(nodes)+len(edges)` at it → 422. Not an ad-hoc literal.
  - `CurationGroupCreate`: `proposed_nodes: list[dict] = []`, `proposed_edges: list[dict] = []`,
    `reason: str | None = None`, `possible_schema_gap: bool = False`; validator enforces
    `MAX_GROUP_ELEMENTS` → 422.
- Tests and container command (`backend/tests/integration/test_review_groups.py`):
  round-trip (create_group → list_groups shows it with gate → approve_group writes to graph);
  bad type → 422; empty group → 422; over-cap (21 elements) → 422; **duplicate id within group
  (condition 3)** → 422 and nothing staged; `possible_schema_gap` → listed flag +
  `needs_schema_extension`; **B1**: a group whose node id equals an approved id → approve 409;
  **transaction atomicity (condition 2):** inject a failure on the Nth element insert (e.g.
  monkeypatch/last-element PK clash) and assert the whole group rolled back — zero rows for that
  `group_id` in `curation_items`; **admin-auth (condition 4):** with `ADMIN_API_KEYS` configured,
  `POST /admin/curation/groups` without / with a wrong `X-API-Key` → 401/403, with a valid key →
  201 (mirrors how other `/admin/*` auth is asserted in the suite).
  Run: `docker compose run --rm backend pytest tests/integration/test_review_groups.py -x`.
- Stop/handoff: backend green before touching the frontend.

### Task 2 — Frontend: Ingestion page + toggle + statement builder

- Files/symbols: `frontend/app.js` — rework `renderIngest` into an Ingestion page whose header
  hosts a `[LLM 抽取] ↔ [人工建構]` toggle; extract the current renderIngest body into an
  `paintExtract(host)` sub-view (behaviour unchanged); add `paintHandmade(host)` — a statement
  builder with add/remove **concept** rows (type/label/desc/id) + **relation** rows
  (type/source/target/id), a `possible_schema_gap` checkbox, a reason field, and a submit that
  POSTs `/admin/curation/groups`. On success: success notice + link/hint to `群組審閱`.
- Implementation: reuse existing form primitives (`E`, `field`, `NODE_TYPES`, `REL_TYPES`,
  `nodeTypeLabel`, `phraseRelation`). Client-side guard: block submit if 0 elements or any row
  missing `id`. Keep the `解析` label or rename the tab to `收錄`/Ingestion (label only).
- Tests and container command: no FE harness — **manual browser pass** (documented as owed, per
  project norm). Backend contract exercised by T1 tests.
- Stop/handoff: hand to human for a browser check of both sub-views.

### Task 3 — Nav consolidation + contract doc

- Files/symbols: `frontend/app.js` `VIEWS` — remove the `curation` (`審訂`) entry (and
  `renderCuration` if now unreferenced); leave `review`, `expert`, `eval` untouched.
  `docs/api_contract.md` — add `POST /admin/curation/groups` (request/response/errors, noting it
  follows the `{"error":{code,message}}` contract and feeds `GET /admin/review/groups`).
- Implementation: pure removal + doc addition; `/admin/curation/*` endpoints stay.
- Tests and container command: `make test` full run green (+ known flake); ruff/format/mypy.
- Stop/handoff: produce verification + change reports.

## Verification Strategy

- Normal: create_group → list_groups → approve round-trip (graph node/edge present, `status`
  approved).
- Boundary: empty group; single-node group (0 edges); over-cap; group referencing an existing
  approved node as an edge endpoint (referenced, not re-proposed) resolves its label.
- Failure: non-whitelist type → 422; malformed payload (no id) → 422; approve a group reusing an
  approved id → 409 (B1).
- Compatibility: `test_curation.py` (single-item path) stays green; `list_groups` still returns
  the seeded demo groups alongside the new hand-made one.
- Security: the injection guard (`_validate_curation_payload`) runs on every element at create
  time — a type outside the whitelist can never reach Cypher label interpolation on approval.
- Commands (Docker only): `docker compose run --rm backend pytest tests/integration/test_review_groups.py tests/integration/test_curation.py -x`; then `make test`; ruff via
  `ghcr.io/astral-sh/ruff:latest` + mypy per project norm.

### Flake policy (condition 5)

Exactly **one** known-flaky test is tolerated: `test_pipeline_run_is_idempotent`
(idempotent-pipeline; fails only on a non-pristine Postgres volume — documented, pre-existing,
not a regression). Ruling on a `make test` result:

- Green, or the *only* failure is that named test → **pass** (record "154+ passed, 1 known
  flake").
- Any *other* failure, or that test failing for a *different* reason (assertion/stack unrelated to
  leftover extract chunks) → **treated as a real regression; stop and fix**, never waved through.
- Before invoking the flake exemption: confirm the failing test name and that its failure trace
  matches the known cause; a `docker compose down -v` + re-run must make it green. If re-run on a
  clean volume still fails → not the known flake.

### Manual browser checklist (condition 5)

No FE harness, so T2/T3 hand off to a human browser pass at `http://localhost:8080/app/`. Owed
checklist:

1. Ingestion page shows the `[LLM 抽取] ↔ [人工建構]` toggle; switching repaints the correct
   sub-view without stale DOM.
2. LLM 抽取 sub-view = unchanged: source select, strategy pills, params, preview (no token spend),
   run (owner-gated) all behave as before.
3. 人工建構: add/remove concept rows and relation rows; type dropdowns populated
   (NODE_TYPES/REL_TYPES); submit with 0 elements or a missing id is blocked client-side with a
   clear message.
4. A valid statement (≥1 concept + its relation) submits → success notice; the group then appears
   in `群組審閱` with its Schema gate + expert lens; approving it round-trips into the graph.
5. `possible_schema_gap` checkbox → the group shows the schema-gap banner/`needs_schema_extension`
   in Review; 核准 disabled per H2.
6. The `審訂` tab is gone from nav; `問答/圖譜/典藏/收錄(Ingestion)/群組審閱/審閱/評估` all still
   route without console errors.
7. Extract-still-ungrouped disclosure note is visible on the LLM sub-view (P5 honesty).

## Risks and Unknowns

- **Extract path still ungrouped (accepted, P5):** LLM-extracted items won't appear in group
  Review yet. UX wart — the Ingestion page will note extract staging is per-item pending P5, so
  the disconnect is disclosed, not hidden.
- **Statement builder UX** is new hand-written JS with no test harness — relies on the human
  browser pass; keep it minimal (reuse existing primitives).
- **group_id uniqueness:** uuid-based, collision-free; item_id `curation:{group_id}:{elem_id}`
  inherits that uniqueness.
- **Dangling edge endpoints:** an edge referencing a node neither proposed-in-group nor approved
  will show a humanized id in the lens (no crash). Left as-is (YAGNI); could add a soft warning
  later.

## Rollback

Revert the listed files. No migration, no data backfill. Any group staged during testing is
`proposed` only (invisible to retrieval); `make demo-reset` clears demo approvals; hand-made test
groups can be rejected or deleted by id. `/admin/curation/*` and the group Review surface are
untouched by a revert.

## Human Decisions and Approval

- Decisions required: three scope decisions **resolved** (recorded above).
- Status: **Conditionally Approved** (human, 2026-08-01) — approval contingent on the five
  conditions below, now folded into the plan (revision 2):
  1. **Fixed element cap** → `MAX_GROUP_ELEMENTS = 20` named constant (Task 1).
  2. **Transaction-atomicity test** → fault-injected mid-group insert asserts full rollback (Task 1
     tests).
  3. **Intra-group duplicate-id validation** → 422 up front, combined node+edge id set (Task 1).
  4. **Admin-auth test** → `require_admin` on the new endpoint asserted 401/403 vs 201 (Task 1
     tests).
  5. **Manual browser checklist + flake policy** → both defined under Verification Strategy.
- Approved plan revision: **2** (conditions incorporated)
- Approved risk level and automation mode: **medium**, **one-task-at-a-time**
- Approved by/date: human, 2026-08-01
- Approval evidence: conditional approval given in-session; conditions 1–5 addressed in this
  revision. Material further changes would re-invalidate approval.
