# Implementation Plan: group-review-gap-outcome

## Objective

Add the **third dispose outcome** to group Review — **record-as-gap** — reconnecting the schema-gap
capability that P4 removed with the standalone `審閱` screen. When the Schema gate says
`needs_schema_extension` (the expert judges the current schema cannot express the proposal's real
meaning), the reviewer can record it as a typed **schema gap** (plain-language taxonomy →
`schema_gap_type`) instead of only 核准/退回. This fixes the P3 banner that already promises
"只能退回**或記為 gap**" but has no button behind it, and makes the seeded `demo_schema_gap` group a
working end-to-end demo.

Owner decisions (2026-08-03): (D1) persist as a **new `schema_gap` curation_items status + a
`graph_change_logs` audit row** (no new table, no migration); (D2) offer the gap action **only for
`needs_schema_extension`** groups.

## In Scope

1. Backend: `service.record_group_gap(group_id, reviewer, reason, schema_gap_type)` — enforcing;
   sets the group's proposed items to `status='schema_gap'`, appends one `graph_change_logs` row
   (`action='schema_gap'`), writes nothing to Neo4j.
2. Backend: `SchemaGapRequest` schema + `POST /admin/review/groups/{group_id}/gap`
   (`{"error":{code,message}}` contract, like the other group endpoints).
3. Backend: validate `schema_gap_type` against the 6-value taxonomy whitelist (from
   `docs/schema-gap-policy.md`).
4. Frontend: reintroduce the plain-language gap taxonomy (`GAP_OPTIONS`) and add a **記為 gap**
   action in `reviewActions`, shown only when `schema_gate.result === 'needs_schema_extension'`;
   pick a gap type → POST `/gap` → remove from queue. Cache-bust `index.html`.
5. `make demo-reset` also returns demo-origin `schema_gap` items to `proposed`, so the
   `demo_schema_gap` group stays re-demoable.
6. Docs: document the new endpoint in `docs/api_contract.md`; note the schema-gap-policy reconnection.

## Out of Scope

- A full **schema-gap backlog management** lifecycle (accept/reject a gap, `proposed_schema_change`,
  a backlog table/UI, the `gap_id/raised_by_case/...` structure in `docs/schema-gap-policy.md`) — the
  live backlog here is the append-only `graph_change_logs` `action='schema_gap'` rows; richer
  management is a separate later change (roadmap decision #3).
- `data/sample/expert_demo/schema_gap_backlog.json` — stays as legacy sample data; not read/written
  by this change.
- Broadening gap eligibility to `pass` or `fail_schema` groups (D2 fixed to `needs_schema_extension`).
- Any change to approve/reject, the two-gate engine, retrieval, or the propose side.

## Current-State Evidence

- Repo state: `main` at `c64163b`; **P4 is committed + pushed but NOT merged**
  (`feat/two-gate-review-p4`, `a985b2e`+`f43fec8`, PR pending). This change **depends on P4** (it
  re-adds a gap outcome to the *post-P4* group Review; on `main` today `GAP_OPTIONS`/`renderExpertDemo`
  still exist). **Branch = off latest `main` AFTER P4 merges** (owner condition 1) — implementation is
  gated on that; do not start on the current `main` or stack on the P4 branch.
- **`curation_items.status` dependency audit (owner condition 2 — read-only sweep done 2026-08-03):**
  a new `'schema_gap'` value is safe against every reader/writer found —
  - `list_items` (service.py:85) is status-agnostic (optional filter param); `list_groups`
    (service.py:363) filters `status='proposed'`, so a `schema_gap` group **correctly leaves the
    queue**.
  - `approve_group`/`reject_group` (441/532) act only on `[r for r if status=='proposed']`; the
    single-item `approve_item`/`reject_item` (238/275) guard `status != 'proposed'` → 409. So a
    `schema_gap` member can never be approved/rejected/re-recorded. Consistent.
  - No code **enumerates or CHECK-constrains** the status set; `schema.sql:41` is free TEXT default
    `'proposed'`. Frontend uses `g.schema_gate.result`, never item status (the two `r.status` hits are
    HTTP status codes).
  - **One documented interaction:** `load_postgres.py:231` demo convergent-delete only removes
    `proposed_by='demo' AND status='proposed'`, so once the demo group is recorded as `schema_gap`,
    `make seed` alone won't restore it (`stage_demo_review_group` is `ON CONFLICT DO NOTHING`) —
    `make demo-reset` (extended by this change, Task 1) does. This matches how approved demo items
    already behave. Recorded as a known limitation, not a defect.
- `frontend/app.js`: `reviewActions` (~685-722) builds 核准並寫入 + 退回 and POSTs
  `/admin/review/groups/{id}/{approve|reject}`; `paintExpert` (~641) banner already says
  needs_schema_extension → "只能退回或記為 gap" (the promise with no button). The old `GAP_OPTIONS`
  (6 plain-language ⇄ `schema_gap_type` options) was deleted by P4 — re-add it (verbatim from
  `docs/schema-gap-policy.md`).
- `backend/app/curation/service.py`: `reject_group` (the model — `FOR UPDATE`, guard 404/409,
  UPDATE status, `_log_change`, return) ; `list_groups` filters `status='proposed'`, so a
  `schema_gap` group leaves the queue. `curation_items.status` is free **TEXT** (schema.sql:41,
  `DEFAULT 'proposed'`, no CHECK/enum) → a new `schema_gap` value needs **no migration**.
- `backend/app/api/routes_review.py`: `approve`/`reject` endpoints + `_as_api_error`; add `gap`
  alongside. `backend/app/schemas/curation.py`: `ApproveRejectRequest` — add `SchemaGapRequest`.
- `scripts/reset_demo_review.py` / `make demo-reset`: currently resets demo `approved` items
  (DETACH DELETE + set proposed + audit). Extend to also reset demo `schema_gap` items (no Neo4j
  write to undo — just set `proposed`).
- Taxonomy (whitelist): `permissive_effect`, `antagonistic_or_synergistic_interaction`,
  `pathway_or_cascade`, `conditional_effect`, `threshold_effect`, `unknown`.
- Baseline: `main` full offline suite green (P4's 163 on its branch). Offline posture
  (`-e OPENAI_API_KEY=`) — the host `.env` key is credit-exhausted.

## Acceptance Criteria

1. `POST /admin/review/groups/{id}/gap` on a `needs_schema_extension` group with a valid
   `schema_gap_type` → `200 {group_id, status:'schema_gap', schema_gap_type}`; the group's
   `curation_items` become `status='schema_gap'`; one `graph_change_logs` row `action='schema_gap'`,
   `after_state` carries `schema_gap_type` + `item_ids`; **nothing written to Neo4j**; the group no
   longer appears in `GET /admin/review/groups`.
2. Enforcing guards (documented error contract): group not found → 404; no proposed members → 409;
   gate `result != 'needs_schema_extension'` → 409; `schema_gap_type` not in the whitelist → 422;
   **blank `reviewer` → 422** (condition 5).
3. **Atomicity (condition 3):** the `curation_items` status UPDATE and the `graph_change_logs`
   INSERT happen inside **one `async with conn.transaction()`** — a failure of either rolls both back
   (no status flip without its audit row, and vice-versa). Asserted by a fault-injection test.
4. **reviewer/reason (condition 5):** `reviewer` is required and non-empty; `reason` is optional.
   Both are persisted: the audit row carries `actor=reviewer` + `reason=reason`, and the group's
   `curation_items` get `reviewed_by=reviewer, reason=reason, reviewed_at=now()` (mirrors
   `reject_group`). (approve/reject remain lenient about a blank reviewer — unchanged here; a
   consistency tightening across all three is a separate note.)
5. Frontend: for a `needs_schema_extension` group, `reviewActions` shows a **記為 gap** control with
   the 6 plain-language options; recording removes the group from the queue; the banner's
   "記為 gap" promise is now backed by a real action. 核准 stays disabled (gate not pass).
6. `make demo-reset` returns the demo `schema_gap` group to `proposed` (re-demoable).
7. `make test` green; ruff 0.15.21 + mypy clean; `node --check` OK; `api_contract.md` documents the
   endpoint.

## Contract, Schema, Dependency, and Migration Impact

- **Contract:** *additive* — new `POST /admin/review/groups/{group_id}/gap`. No existing endpoint
  changes. Documented in `api_contract.md`.
- **Schema/DB:** none. New `curation_items.status` value `'schema_gap'` (free TEXT, no migration);
  `graph_change_logs.action='schema_gap'` (generic TEXT).
- **Dependency / Migration:** none.

## Execution Policy

- Plan revision: 2 (Conditionally Approved — 6 conditions folded in)
- Risk level: **medium** (new enforcing write endpoint + new status; no migration/dependency;
  frontend needs a browser pass)
- Automation mode: **one-task-at-a-time** (recommended), or supervised-auto for T1→T3 if preferred.
- **Start gate (condition 1):** implementation begins only after **P4 is merged**; branch off the
  **latest `main`** then. Do not start on the pre-P4 `main` or stack on the P4 branch.
- Approved file/path scope: `backend/app/curation/service.py`, `backend/app/schemas/curation.py`,
  `backend/app/api/routes_review.py`, `backend/tests/{integration/test_review_groups.py,api/test_curation_groups.py}`,
  `frontend/app.js`, `frontend/index.html`, `scripts/reset_demo_review.py`, `docs/api_contract.md`,
  `changes/group-review-gap-outcome/*`.
- Human checkpoints: after T1 (backend green) before T2; browser pass after T2/T3.
- Mandatory stop conditions: any need for a migration, a dependency, changes to approve/reject or the
  engine, endpoints beyond the new one, or a failing suite.
- Commit/push permission: **No unless separately approved after review.**

## Tasks

### Task 1 — Backend: gap endpoint + service + demo-reset

- `service.record_group_gap(group_id, reviewer, reason, schema_gap_type)`: mirror `reject_group`.
  **All mutations in ONE `async with conn.transaction()`** (condition 3): `SELECT … FOR UPDATE` →
  guards → the `UPDATE curation_items SET status='schema_gap', reviewed_by=reviewer, reason=reason,
  reviewed_at=now() WHERE group_id=$1 AND status='proposed'` and the single
  `_log_change(action='schema_gap', target_type='proposal_group', after_state={schema_gap_type,
  item_ids})` are inside the same block — either both commit or both roll back.
  Guards in order: 404 not found; 409 no `proposed` members; 422 blank `reviewer` (condition 5);
  409 if `evaluate_schema_gate(_proposal_from_items(proposed))['result'] != 'needs_schema_extension'`;
  422 if `schema_gap_type` not in the whitelist. Returns `{group_id, status:'schema_gap',
  schema_gap_type}`.
- `SchemaGapRequest(reviewer: str, reason: str | None = None, schema_gap_type: str)`;
  `POST /admin/review/groups/{group_id}/gap` in `routes_review.py` via `_as_api_error`.
- Extend `reset_demo_review.py`: also `UPDATE curation_items SET status='proposed', reviewed_by=NULL,
  reason=NULL, reviewed_at=NULL WHERE proposed_by='demo' AND status='schema_gap'` (+ an audit note),
  so `make demo-reset` re-arms the gap demo.
- Tests (`test_review_groups.py`), condition 4 explicit:
  - happy path — status flips to `schema_gap`, **exactly ONE** `graph_change_logs` row for the group
    (audit uniqueness), `after_state.schema_gap_type` correct, **no Neo4j write**, group leaves
    `list_groups`;
  - **double-record** — record twice → 2nd → 409 (no proposed members);
  - **partial-proposed members** — a group with one member already non-`proposed` → only the
    `proposed` members flip, the pre-existing one is untouched, still one audit row;
  - **audit uniqueness** — assert `count(*) == 1` for `action='schema_gap', target_id=group_id`;
  - **atomicity** (condition 3) — fault-inject after the UPDATE / before/at the INSERT and assert
    neither the status change nor an audit row persists;
  - guards — 409 on a `pass` group, 422 bad `schema_gap_type`, 422 blank reviewer, 404 unknown group.
- Run: `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_review_groups.py -x`.

### Task 2 — Frontend: 記為 gap action

- Re-add `GAP_OPTIONS` (module const). In `reviewActions`, when `g.schema_gate.result ===
  'needs_schema_extension'`, render a gap-type `<select>` (plain-language labels) + a **記為 gap**
  button that POSTs `/admin/review/groups/{id}/gap` with `{reviewer, reason, schema_gap_type}`;
  on success flash + drop the group from the queue (same pattern as approve/reject). Bump
  `index.html` `?v=`.
- Verify: `node --check`; **manual browser pass (owed, condition 6)** on the `demo_schema_gap` group —
  (a) **success:** pick a gap type → 記為 gap → flash confirms, group leaves the queue;
  (b) **API failure:** force an error (e.g. a group whose gate isn't needs_schema_extension, or stop
      the backend) → error flash shown, the gap/退回 buttons re-enable (no dead state);
  (c) **double-click:** rapid double-click on 記為 gap fires **one** request (buttons disable on the
      first click) — no duplicate audit row;
  (d) **post-refresh:** after recording, reload the page → the group does **not** reappear in the
      queue (status persisted server-side, not just hidden client-side).

### Task 3 — Docs + full verification

- `api_contract.md`: document `POST /admin/review/groups/{group_id}/gap` (request, side-effects, the
  four guards, the taxonomy). Note the schema-gap-policy reconnection.
- `make test` green; ruff/format/mypy; `node --check`; produce verification + change reports.

## Verification Strategy

- Normal: record-gap round-trip (status→schema_gap, audit row present, absent from queue, Neo4j
  untouched); demo-reset re-arms it.
- Boundary/failure: 409 on pass/other gate results; 422 bad gap_type; 404 unknown group; 409 no
  proposed (double-record).
- Compatibility: approve/reject unchanged and green; `list_groups` still lists only proposed.
- Security: `schema_gap_type` validated against a whitelist (no free-text into audit semantics);
  admin-gated like the other group routes.
- Commands (Docker only): targeted pytest, then `make test`; ruff `ghcr.io/astral-sh/ruff:0.15.21`;
  `mypy backend/app ingestion scripts`; `node --check`.

## Risks and Unknowns

- **Branch base** (above): depends on P4; recommend merging P4 first, base off `main`.
- **No backlog VIEW yet:** a recorded gap is auditable (graph_change_logs) but not shown in any UI —
  intentional (backlog management is a separate change); disclose in the change report.
- **schema_gap_backlog.json stays orphaned** — legacy sample; a future backlog change decides its fate.
- Frontend manual-only (no harness) — browser pass owed.

## Rollback

Revert the listed files. No migration. Demo groups recorded as `schema_gap` during testing are
returned to `proposed` by `make demo-reset`; no approved-graph or retrieval impact (gap never writes
Neo4j).

## Human Decisions and Approval

- Decisions: (D1) persistence = new `schema_gap` status + audit row — **RESOLVED**; (D2) eligibility
  = `needs_schema_extension` only — **RESOLVED**.
- Status: **Conditionally Approved** (owner, 2026-08-03) — contingent on the six conditions, now
  folded in (revision 2):
  1. **P4 merged first, branch off latest `main`** → start-gate in Execution Policy.
  2. **`curation_items.status` dependency audit** → done + recorded in Current-State Evidence
     (new `schema_gap` value proven safe; one demo-reseed interaction documented).
  3. **status UPDATE + audit INSERT in one transaction** → Acceptance #3 + Task 1 + atomicity test.
  4. **double-record / partial-proposed / audit-uniqueness tests** → Task 1 test list.
  5. **reviewer/reason validation + audit persistence** → Acceptance #4, reviewer non-empty→422,
     both persisted in the audit row + `curation_items`.
  6. **browser verification covers success / API failure / double-click / post-refresh** → Task 2.
- Approved plan revision: **2**; risk **medium**; mode **one-task-at-a-time** (unless owner elects
  supervised-auto).
- Approved by/date: owner, 2026-08-03 (conditional).
- Approval evidence: conditional approval in-session; conditions 1–6 addressed in this revision.
  **Implementation is gated on P4 merging first (condition 1).** Material further changes re-invalidate.
