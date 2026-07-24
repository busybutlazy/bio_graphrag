# Implementation Plan: unified-two-gate-review (Phase 1 — walking skeleton)

## Objective

Prove the merged **group-level two-gate governance** end-to-end on seeded demo data: a proposed
*statement* (a group of nodes+edges) is reviewed as one unit through the **Schema gate**
(`engineer_gate`, incl. pattern completeness) and the **Expert gate** (human approve/reject via the
`back_translation` no-JSON lens); approving writes all member nodes/edges to the approved graph and
appends an audit row; the `status='approved'` invariant is provable (group invisible to retrieval before
approval, visible after). This is the walking skeleton for the [[unified-two-gate-restructure]] (grill
decisions D1–D7); the rest is an explicit roadmap below, not this slice.

## In Scope (Phase 1)

- A minimal **proposal-group** representation on `curation_items` (grill D7).
- Service: assemble a group into a `{proposed_nodes, proposed_edges}` proposal; run `engineer_gate` +
  `back_translation` on it; transactional **approve_group / reject_group**.
- API: `GET /admin/review/groups` (+ per-group computed schema gate + understanding) and
  `POST /admin/review/groups/{group_id}/approve|reject`.
- Seed **one** demo proposal group (Case 1, from `data/sample/expert_demo/cases.json`) as `proposed`
  grouped `curation_items`.
- A minimal **Review** frontend view listing groups with three tabs (提案 / schema gate / 專家 lens) +
  approve/reject, reusing existing `renderExpertDemo` tab code + `renderCuration` action code.
- Verification of the invariant end-to-end.

## Out of Scope (deferred to later phases — see Roadmap)

- All 7 cases incl. the form/meaning rejection cases as seed (D3); the Ingestion page + LLM-extract ↔
  hand-made **toggle** and hand-made group create (D1); the `back_translation` **third outcome** for
  schema-valid-non-pattern items (D5); retiring the standalone Expert Review screen + `/admin/expert-demo`
  endpoint (D1); gold/backlog repurpose (D2); per-group staging in the real LLM extract path.
- Any `schema/` node/edge **type** change. Real golden seed / real pipeline.

## Current-State Evidence

- **Repository state:** on `main`; working tree carries the uncommitted `expert-gate-integrity` change
  (12 modified + 2 new source files + `changes/`), plus unrelated `docs/agent-guideline.md` self-heal.
  **Commit disposition (approval point):** recommend committing the working whole as the branch baseline
  first (grill "commit" path A — surgical extraction was found disproportionate), so this restructure
  supersedes the standalone persistence in *its own* diff on a clean base.
- **Relevant symbols (observed):**
  - `backend/app/curation/service.py`: `create_item` (per-element, item_type node|edge), `approve_item`
    (writes one payload to Neo4j via `load_neo4j.write_nodes/edges` + `_log_change('approve')`),
    `reject_item`, `list_items` (returns payload + `schema_check`), `_log_change` (audit).
  - LLM extract + seed stage **per element**: `ingestion/pipeline/load_postgres.py` loops
    `candidate["nodes"]`/`["edges"]` → one `curation_items` row each with per-element `schema_check`
    (`ingestion/pipeline/schema_checker.py`).
  - `backend/app/graph/engineer_gate.py::evaluate(proposal)` and
    `back_translation.py::render_understanding(proposal, ctx)` — both take `{proposed_nodes,
    proposed_edges}`; this is exactly a *group* shape.
  - `data/sample/expert_demo/cases.json`: each case already has `proposal.{proposed_nodes,
    proposed_edges}` — a ready-made group.
  - Frontend `frontend/app.js`: `VIEWS` (l.136) has `ingest`/`curation`/`expert`; `renderCuration`
    (l.528, incl. `schema_check` badge + create form), `renderExpertDemo` (l.680, 3-tab lens),
    `api.get/post`.
  - `curation_items` DDL: `ingestion/pipeline/schema.sql` (+ idempotent `ensure_schema`).
- **Baseline tests / commands:** `make test` currently **132 passed, 1 failed** — the failure is the
  documented, unrelated `test_pipeline_run_is_idempotent` flake (non-pristine volume). `make up`,
  `make seed`, `make health` per Makefile. `backend/tests` is **not** volume-mounted → rebuild image for
  test edits.

## Acceptance Criteria (observable)

- **A1:** `GET /admin/review/groups` returns the seeded Case-1 group as one item with `schema_gate`
  (`engineer_gate` result=`pass`) and `understanding` (`back_translation` P1 sentence) computed live.
- **A2:** Before approval, the group's nodes are **not** returned by `GET /neighbors` / `/query` graph
  expansion (status≠approved); `POST .../approve` then writes them and they **are** returned. Invariant
  demonstrated by an integration test.
- **A3:** `POST .../{id}/reject` marks all member items rejected, writes nothing to Neo4j, appends a
  `reject` audit row. Approve appends an `approve` audit row (actor + reason).
- **A4:** Approve/reject is transactional — partial failure writes nothing (all-or-nothing per group).
- **A5:** Review view renders the group's three tabs and approve/reject works against the endpoint.
- **A6:** `make test` green except the known unrelated flake.

## Contract, Schema, Dependency, and Migration Impact

- **Schema/DB migration (HIGH-RISK approval point):** add `group_id TEXT NULL` to `curation_items`
  (idempotent DDL in `schema.sql` + `ensure_schema`; NULL = existing ungrouped items, backward-compatible).
  *Alternative considered:* a separate `proposal_groups` table — heavier; recommend the nullable column.
- **Contract:** ADDS `GET /admin/review/groups`, `POST /admin/review/groups/{id}/approve|reject`
  (admin-gated). Additive; existing `/admin/curation/*` untouched this phase.
- **Dependencies:** none.
- **Data:** approve writes approved nodes/edges (same as existing curation approve) + audit rows.

## Execution Policy

- **Plan revision:** 1 (Draft).
- **Risk level:** **HIGH** (schema migration + new write contract + graph-mutating group approval +
  data-model change).
- **Automation mode:** **one-task-at-a-time** (no supervised-auto). Human checkpoint before every task;
  mandatory checkpoint before T1 (migration) and T3 (seed) and T5 (graph-writing approve path).
- **Approved path scope:** `ingestion/pipeline/**`, `backend/app/curation/**`, `backend/app/api/**`,
  `backend/app/schemas/**`, `backend/tests/**`, `frontend/**`, `docs/api_contract.md`.
- **Mandatory stop conditions:** any need to change a `schema/` type; any retrieval/approved-invariant
  change beyond the additive read path; dependency add; `make test` failing for reasons other than the
  known idempotent flake; scope creep into deferred phases.
- **Commit/push:** **No unless separately approved after review.**

## Tasks

### T1 — Add `group_id` to `curation_items` (migration)  *(checkpoint)*
- Files: `ingestion/pipeline/schema.sql`, `ingestion/pipeline/load_postgres.py` (`ensure_schema`).
- Implementation: idempotent `ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS group_id TEXT;`.
- Tests/verify: `make up` + a query asserting the column exists; existing curation tests still pass.

### T2 — Group assembly + gate/lens + transactional approve/reject (service)
- Files: `backend/app/curation/service.py` (new `list_groups`, `approve_group`, `reject_group`; reuse
  `_log_change`, `load_neo4j`, `engineer_gate.evaluate`, `back_translation.render_understanding`).
- Implementation: `list_groups` → group `curation_items` by `group_id`, assemble
  `{proposed_nodes: [node payloads], proposed_edges: [edge payloads]}`, attach `engineer_gate` +
  `understanding`. `approve_group(group_id, reviewer, reason)` → within one transaction, write all member
  nodes/edges to Neo4j, set each item `approved`, append one `approve` audit row (target = group_id).
  `reject_group` symmetric, no Neo4j write.
- Tests: `backend/tests/integration/test_review_groups.py` — assemble shape, approve writes all + audit,
  reject writes none + audit, transactional all-or-nothing.

### T3 — Seed one demo proposal group  *(checkpoint)*
- Files: `ingestion/pipeline/load_postgres.py` (or a small seed helper), reads
  `data/sample/expert_demo/cases.json` Case 1.
- Implementation: stage Case 1's nodes+edges as `proposed` `curation_items` sharing a `group_id`
  (e.g. `group:blood_glucose_case_001`), each with per-element `schema_check`. Idempotent (ON CONFLICT).
- Tests/verify: after `make seed`, `GET /admin/review/groups` returns the group.

### T4 — Review endpoints (API + contract)
- Files: `backend/app/api/routes_review.py` (new, admin router), `backend/app/schemas/review.py`,
  `docs/api_contract.md`; mount in `main.py`.
- Implementation: `GET /admin/review/groups`; `POST /admin/review/groups/{group_id}/approve|reject`
  (`{reviewer, reason}`). Map `CurationError` to the error contract.
- Tests: `backend/tests/api/test_review.py` — group listing shape, approve 200, reject 200, unknown id
  404/409.

### T5 — Minimal Review frontend view  *(checkpoint)*
- Files: `frontend/app.js` (new `renderReview` + a `VIEWS` entry), `frontend/styles.css` if needed.
- Implementation: list groups; per group three tabs (提案 raw / schema gate / 專家 lens — reuse
  `renderExpertDemo` tab code) + approve/reject buttons calling T4. Keep Tab3 isolation (no JSON/ids).
- Verify: manual browser click-through (no FE harness — disclose manual-only), plus live `curl` of the
  endpoints through nginx.

## Verification Strategy

- Normal: seeded group lists with `pass` schema gate + P1 sentence; approve → nodes appear in
  `/neighbors`; audit row present.
- Boundary/failure: reject writes nothing; unknown group_id → 404; double-approve → 409; transactional
  rollback on simulated write failure.
- Invariant: integration test — nodes absent from retrieval pre-approve, present post-approve.
- Commands: `make test` (unit+integration+api), `make up`+`make health`, `curl` through `:8080`, manual
  UI check. Report the known idempotent flake explicitly.

## Risks and Unknowns

- **R1:** migration touches a shared table — mitigated by nullable, backward-compatible column + idempotent
  DDL; existing per-element curation flow unchanged.
- **R2:** group approval mutates the approved graph — HIGH risk; transactional, admin-gated, same writer as
  existing `approve_item`; checkpoint before T5.
- **R3:** assembling a proposal from per-element rows assumes members share `group_id` and valid
  source/target refs; seed guarantees this — real-extract grouping is **deferred** (becomes blocking when
  the real pipeline lands).

## Rollback

- T1 column is additive/nullable (leave or `DROP COLUMN` — no data loss for existing items). T2–T5 revert
  by removing the new service fns, routes, schema, seed block, and frontend view. Approved demo nodes can
  be re-seeded (`make seed` is idempotent) or removed via existing curation delete.

## Human Decisions and Approval

- **Decisions required:**
  1. **Commit disposition** — commit the working `expert-gate-integrity` whole as the branch baseline
     first (recommended), or another approach.
  2. **Group representation** — `group_id` nullable column (recommended) vs a `proposal_groups` table.
  3. **Phase-1 walking-skeleton scope** — accept this slice (one seeded group, minimal Review view) with
     the rest as roadmap, or broaden.
  4. **Automation mode** — one-task-at-a-time (proposed) confirmed.
- Status: **Approved** (Phase 1, revision 1) — user (jett), 2026-07-24.
- Approved decisions: (1) commit working expert-gate-integrity whole as branch baseline first;
  (2) `group_id` nullable column; (3) walking-skeleton Phase-1 scope with P2–P5 roadmap; (4)
  one-task-at-a-time. First action: baseline commit, then T1.
- Approval evidence: user selected "Approve all as recommended" + "Commit baseline, then T1" in-session.

## Roadmap (subsequent phases — not this plan)

- **P2:** all 7 cases incl. rejection cases as seed groups (D3); `back_translation` third outcome (D5).
- **P3:** Ingestion page — LLM-extract ↔ hand-made **toggle**; hand-made **group** create.
- **P4:** retire standalone Expert Review screen + `/admin/expert-demo` endpoint (D1); fold its tab code
  into Review.
- **P5:** gold as `back_translation` regression + live schema-gap backlog (D2); per-group staging in the
  real extract path.
