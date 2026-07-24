# Implementation Plan: expert-gate-integrity

## Objective

Make the expert-in-the-loop governance demo *provably* real, in service of the project's
portfolio thesis (auditable human-curation governance):

1. **G5** — add two rejection cases so the demo visibly shows a gate saying "no": one
   **form-rejection** (engineer gate) and one **meaning-rejection** (expert gate rejects a
   form-valid but biologically wrong proposal). Extend gate/renderer/gold test coverage to match.
2. **G2** — persist expert reviews to Postgres (reusing `graph_change_logs`) so the "auditable"
   claim is backed by real append-only records, not ephemeral `sessionStorage`.
3. **Doc reconciliation** — bring `docs/expert-in-the-loop-plan.md` (and companions) in line with
   the already-merged implementation and the deliberate reversal of its read-only design.
4. **README thesis + six-step demo walkthrough** — *only after* the code above runs and is verified.

Ride-along cleanups (G3/G4/G6) are optional and separately gated (see Tasks).

## In Scope

- New demo cases 6 (form-reject) & 7 (meaning-reject) in `data/sample/expert_demo/cases.json`.
- Test updates: `test_engineer_gate.py`, `test_expert_demo.py`, `test_gold_examples.py` (case-count
  and gold-per-case invariants), plus assertions for the new rejection behaviors.
- New write endpoint `POST /admin/expert-demo/reviews` + a service function reusing `_log_change`.
- Frontend: expert tab posts reviews to the backend (in addition to / instead of `sessionStorage`).
- `docs/api_contract.md` update for the new endpoint (read-only → read + additive write).
- Reconciliation edits to `docs/expert-in-the-loop-plan.md`, `docs/expert-in-the-loop-workflow.md`,
  `docs/demo-cases-blood-glucose.md`.
- README thesis block + six-step walkthrough (final task, gated on verification).

## Out of Scope

- Any change to `schema/` node/edge types or `graph_change_logs` **table structure** (no migration).
- Touching approved-graph retrieval, curation approval logic, or the `status='approved'` invariant.
- Real-pipeline integration, expert accounts/multi-user auth, LLM polishing layer.
- **G1** (document `trigger_direction`) — intentionally deferred until real-pipeline work.
- Restoring/committing the unrelated `docs/agent-guideline.md` deletion (see Human Decisions).

## Current-State Evidence

- **Repository state:** branch `main`. Worktree has ONE unexplained change: `docs/agent-guideline.md`
  is **deleted** (`git status` → `D`), whereas the session-start snapshot showed it modified. Not
  caused by this planning; left untouched. No other pending edits.
- **Relevant files and symbols (observed):**
  - `data/sample/expert_demo/cases.json` — 5 cases; per-case shape confirmed (proposal{proposed_nodes,
    proposed_edges, references_existing, confidence, applied_rule_ids, uncertain_points,
    possible_over_inference, possible_schema_gap}, did_not_understand_as[], expert_review{status,
    notes, schema_gap_type, reviewed_by, reviewed_at}, gold{promote, gold_id}).
  - `backend/app/graph/engineer_gate.py::evaluate` / `_pattern_check` / `_decide` — an RE missing
    ON_VARIABLE + direction returns `fail_pattern` (see `test_incomplete_regulatory_effect`).
  - `backend/app/graph/back_translation.py::render_understanding` — schema-valid proposal with
    INCREASES yields a valid P1 sentence (handles a wrong-but-valid case with no code change).
  - `backend/app/api/routes_expert_demo.py` — read-only `GET /admin/expert-demo/cases`; router is
    `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`.
  - `backend/app/curation/service.py::_log_change` — inserts into `graph_change_logs`; accepts
    action/target_type/target_id/actor/reason/curation_item_id/before_state/after_state.
  - `ingestion/pipeline/schema.sql:50` — `graph_change_logs` columns cover the need; `curation_item_id`
    is a nullable FK → expert-demo rows use NULL. **No schema migration required.**
  - `frontend/app.js` — expert tab: `EXPERT_STORE` (l.678), decision radios (l.831),
    `sessionStorage.setItem(EXPERT_STORE(c.id), …)` (l.839).
  - `docs/api_contract.md:203-210` — documents the endpoint as **read-only, no writes**.
- **Existing behavior and baseline tests:**
  - `backend/tests/unit/test_engineer_gate.py` — cases 1–4 pass, case 5 → `needs_schema_extension`,
    plus negative unit cases. Hard-codes the 4 passing case ids.
  - `backend/tests/api/test_expert_demo.py:9` — `assert len(cases) == 5` (WILL break on new cases).
  - `backend/tests/gold/test_gold_examples.py::test_every_case_has_a_gold_file` — asserts gold ids ==
    ALL case ids (WILL break unless rejection cases get gold or the invariant is scoped to promoted cases).
  - Known baseline flake unrelated to this change: `test_pipeline_run_is_idempotent` on a
    non-pristine Postgres volume (recorded in memory; pre-existing, not a regression).
  - Canonical commands (Makefile): `make test` (`docker compose run --rm backend pytest tests
    ingestion/tests`), `make up`, `make seed`, `make lint`, `make format`, `make eval`, `make health`.

## Acceptance Criteria (observable)

- **G5-A (form-reject):** `GET /admin/expert-demo/cases` returns a case whose `engineer_gate.result`
  is `fail_pattern` (or `fail_schema`); its Tab2 shows the failing check with a reason.
- **G5-B (meaning-reject):** a case whose `engineer_gate.result == "pass"` and whose
  `system_understanding.is_gap == false` (form is fine) but whose seeded `expert_review.status ==
  "rejected"` with a biology reason; the expert tab reflects the rejected decision by default.
- **G5-C:** `make test` passes with the updated count / gold-scope assertions; new gate assertions
  cover cases 6 & 7.
- **G2-A:** `POST /admin/expert-demo/reviews` with `{case_id, decision, schema_gap_type?, notes}`
  inserts exactly one `graph_change_logs` row (`action='expert_review'`, `target_id=case_id`,
  `actor` set, `reason=notes`, `after_state` carrying the decision); verified by an integration test
  mirroring `test_curation.py`'s log assertion. Endpoint stays admin-gated and never writes Neo4j /
  approved graph / curation_items.
- **G2-B:** the expert tab, on submit, calls the endpoint (network write occurs); demo still works
  offline/no-key like the rest of `/admin/*`.
- **Doc-A:** `docs/api_contract.md` documents the new write endpoint and drops the "no writes"
  absolute for this route; `docs/expert-in-the-loop-plan.md` roadmap marked done and §五.4 read-only
  reversal noted; new cases documented in `docs/demo-cases-blood-glucose.md`.
- **README-A (final):** README has a thesis block (governance spine + career-transition framing) and
  a six-step demo walkthrough that matches the actually-runnable demo.

## Contract, Schema, Dependency, and Migration Impact

- **Contract:** ADDS `POST /admin/expert-demo/reviews` (admin-gated). Additive, not breaking, but it
  changes the documented "read-only, no writes" property of the expert-demo surface → **approval point**.
- **Schema/DB:** none. Reuses `graph_change_logs` as-is; no migration, no new table.
- **Dependencies:** none.
- **Data:** append-only audit rows only. No mutation of approved graph, curation, or chunks.

## Execution Policy

- **Plan revision:** 1 (Draft).
- **Risk level:** **medium** overall. Rationale: additive admin-gated write endpoint + Postgres write +
  contract-doc change (medium); demo-data + tests + docs (low). No migration, no auth change, no
  approved-graph mutation, no irreversible op.
- **Automation mode (proposed):** hybrid, human to confirm —
  - `supervised-auto` eligible (low-risk, data/tests/docs only): **T1, T5, T6** and optional **T7–T9**.
  - `one-task-at-a-time` (medium, touches DB write + public contract + frontend): **T2, T3, T4**.
- **Auto-approved task IDs (`supervised-auto` only):** T1, T5, T6 (and T7–T9 if opted in) — pending
  explicit human approval of the mode.
- **Approved file/path scope:** `data/sample/expert_demo/**`, `backend/app/api/routes_expert_demo.py`,
  `backend/app/graph/**` (G6 only), `backend/tests/**`, `frontend/app.js`, `docs/**`, `README.md`.
  No writes outside these paths.
- **Human checkpoints:** before T2 (endpoint/contract), before T4 (frontend write wiring), before T10
  (README — must confirm the demo actually ran).
- **Mandatory stop conditions:** any need to add a `schema/` type, alter `graph_change_logs` structure,
  touch retrieval/curation approval, add a dependency, or if `make test` fails for reasons other than
  the known pre-existing idempotent-pipeline flake. Also stop if asked to resolve the
  `agent-guideline.md` deletion inside this change.
- **Commit/push permission:** **No unless separately approved after review.**

## Tasks

### Task 1 (T1) — Add cases 6 (form-reject) & 7 (meaning-reject) to cases.json
- Files/symbols: `data/sample/expert_demo/cases.json`.
- Implementation: Case 6 `blood_glucose_case_006` — a RegulatoryEffect present with `HAS_EFFECT` but
  **missing `ON_VARIABLE` + direction edge** (schema-valid shape, incomplete pattern → `fail_pattern`);
  `expert_review.status` = `"not_reviewed"` (form fails, never reaches expert), `gold.promote=false`.
  Case 7 `blood_glucose_case_007` — source "胰島素會提高血糖濃度", a full three-part proposal with
  `INCREASES` (id `regulatory_effect:insulin_increases_blood_glucose`) → engineer gate **pass**, renderer
  valid; `expert_review.status="rejected"`, notes explaining insulin *lowers* glucose (reversed
  direction = over/incorrect inference), `gold.promote=false`.
- Tests and container command: none yet (behavior asserted in T5/T6). `make test` still green after
  count/gold-scope updates land (order: do T5/T6 alongside).
- Stop/handoff: report the two case payloads for review before wiring assertions.

### Task 2 (T2) — Add write service function reusing `_log_change`  *(one-task-at-a-time)*
- Files/symbols: `backend/app/curation/service.py` (or a small `expert_review` service module) — a
  `record_expert_review(case_id, decision, schema_gap_type, notes, actor)` that calls `_log_change`
  with `action='expert_review'`, `target_type='expert_demo_case'`, `target_id=case_id`,
  `after_state={decision, schema_gap_type}`.
- Tests and container command: `backend/tests/integration/test_expert_review_log.py` asserting one row
  written with expected fields (mirror `test_curation.py:64`). `make test`.
- Stop/handoff: stop after green; do not wire the endpoint yet.

### Task 3 (T3) — Add `POST /admin/expert-demo/reviews` endpoint + contract doc  *(one-task-at-a-time)*
- Files/symbols: `backend/app/api/routes_expert_demo.py` (add POST on existing admin router), request
  schema in `backend/app/schemas/`; `docs/api_contract.md:203-210`.
- Implementation: validate `{case_id, decision, schema_gap_type?, notes?}` (Pydantic; decision ∈
  {approve, doubt, schema_gap}); call T2 service; return the created change_id. Keep `require_admin`.
- Tests and container command: `backend/tests/api/test_expert_demo.py` — POST returns 200 + persists;
  invalid decision → 422; still read-only-safe on GET. `make test`.
- Stop/handoff: stop after green + contract doc updated.

### Task 4 (T4) — Wire frontend expert tab to persist via the endpoint  *(one-task-at-a-time)*
- Files/symbols: `frontend/app.js` (expert submit handler around l.839; reuse existing `api.post`).
- Implementation: on submit, POST to `/admin/expert-demo/reviews`; keep local echo. Ensure seeded
  `expert_review.status` (incl. `rejected`) pre-selects the radio so Case 7's rejection shows by default
  (verify current default-selection logic; adjust if it ignores the seeded status).
- Tests and container command: manual UI check via `make up` + browser at `:8080` (no automated FE
  suite exists). Record steps in verification.
- Stop/handoff: stop after the network write is confirmed.

### Task 5 (T5) — Engineer-gate + api coverage for cases 6 & 7
- Files/symbols: `backend/tests/unit/test_engineer_gate.py`, `backend/tests/api/test_expert_demo.py`.
- Implementation: assert case 6 → `fail_pattern`, case 7 → `pass`; update `assert len(cases) == 5` → 7;
  assert case 7 `system_understanding.is_gap is False`.
- Tests and container command: `make test`.

### Task 6 (T6) — Fix gold-per-case invariant for non-promoted cases
- Files/symbols: `backend/tests/gold/test_gold_examples.py`.
- Implementation: scope `test_every_case_has_a_gold_file` to cases with `gold.promote == true` (or
  `expert_review.status == 'approved'`), so rejection cases are correctly excluded from the gold net.
- Tests and container command: `make test`.

### Task 7 (T7, optional ride-along — G4)
- Add `engineer_gate.result` to each gold file and assert it in `test_gold_examples.py`, pinning gate
  verdicts for cases 2/3/4 (currently unpinned).

### Task 8 (T8, optional ride-along — G6)
- In `engineer_gate.py`, drop or reorder the unreachable `fail_testability` verdict (testability fails
  only when `needs_schema_extension` already wins in `_decide`). Add a code comment if kept.

### Task 9 (T9, optional ride-along — G3)
- Add a one-line comment in `routes_expert_demo.py` noting Tab3 isolation is presentational (the full
  proposal is returned over the wire), not an access boundary.

### Task 10 (T10) — README thesis block + six-step walkthrough  *(after verification; checkpoint)*
- Files/symbols: `README.md`, and reconciliation edits to `docs/expert-in-the-loop-plan.md`
  (roadmap done, §五.4 reversal), `docs/expert-in-the-loop-workflow.md`, `docs/demo-cases-blood-glucose.md`.
- Implementation: thesis sentence (LLM proposes / human disposes / unapproved provably invisible) +
  career-transition framing; six-step demo path (query → ingest → prove-invisible → engineer gate →
  expert gate → approve → re-query → audit row). Must describe only what actually runs.
- Stop/handoff: requires human confirmation the demo ran (checkpoint) before writing.

## Verification Strategy

- Normal: cases 1–5 unchanged behavior; case 7 gate pass + valid understanding; POST persists.
- Boundary: case 6 incomplete pattern → `fail_pattern`; POST with unknown `decision` → 422.
- Failure: POST when DB unavailable → surfaces the standard `{error:{code,message}}` contract.
- Compatibility: `GET /admin/expert-demo/cases` shape unchanged except 2 more cases; offline/no-key
  path still works; admin auth unchanged.
- Security: endpoint stays behind `require_admin`; writes only append-only audit rows; no Cypher/label
  interpolation, no approved-graph or curation mutation.
- Commands: `make test` (unit + api + integration + gold), `make lint`, `make up`+`make health` for the
  endpoint, manual browser check for T4. Report exit codes, pass/fail counts, and the known
  idempotent-pipeline flake explicitly.

## Risks and Unknowns

- **R1 (worktree):** `docs/agent-guideline.md` deletion is unexplained and outside scope — must be
  resolved by the human before/independently of implementation; not touched here.
- **R2 (frontend default-selection):** current expert tab may not pre-select from seeded
  `expert_review.status`; T4 verifies and adjusts. Unknown until read at implementation time.
- **R3 (multi-viewer writes):** append-only log intentionally accepts many rows; author-canonical vs
  viewer rows are distinguished by `actor` (e.g. `expert:<name>` vs `demo-viewer`). No session scoping.
- **R4 (contract perception):** turning a "read-only" surface into read+write is the main reviewer
  hotspot; mitigated by additive, admin-gated, audit-only design and doc update.

## Rollback

- Per-task and self-contained. T1/T5/T6 revert by restoring the JSON/test files. T2–T4 revert by
  removing the service fn, the POST route + schema + contract lines, and the frontend post call; no
  migration to undo (rows in `graph_change_logs` are append-only demo data, safely deletable by
  `action='expert_review'` if desired). T10 is docs-only.

## Human Decisions and Approval

- **Decisions (resolved 2026-07-23):**
  1. Automation mode — **APPROVED (hybrid)**: `supervised-auto` for T1/T5/T6; `one-task-at-a-time`
     for T2/T3/T4.
  2. Endpoint `POST /admin/expert-demo/reviews {case_id, decision, schema_gap_type?, notes?}` and
     read+write surface — **APPROVED**.
  2a. **Enum deviation (review L3) — PENDING explicit human sign-off.** Implemented `decision ∈
     {agree, doubt, cannot}` (matches the existing frontend radios), not the plan's literal
     `{approve, doubt, schema_gap}`. Internally consistent (frontend/schema/docs/tests agree); the
     plan states "Material plan changes invalidate approval," so this contract-surface change needs an
     explicit confirm-or-revert from the human owner.
  3. G3/G4/G6 ride-alongs (T7–T9) — **DEFERRED** (not part of this change; revisit later).
  4. `docs/agent-guideline.md` deletion — resolved separately via `git restore` (recovered committed
     0.7.0); user to re-run external skill-forge for 0.8.3. Out of this change's scope.
- Status: **Approved**
- Approved plan revision: 1
- Approved risk level and automation mode: medium; hybrid (supervised-auto T1/T5/T6, one-task-at-a-time
  T2/T3/T4). T7–T9 deferred.
- Approved by/date: user (jett), 2026-07-23
- Approval evidence: recorded by user in-session; decisions 1–4 above. Material plan changes invalidate
  this approval.
