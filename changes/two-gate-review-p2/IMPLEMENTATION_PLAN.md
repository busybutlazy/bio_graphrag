# Implementation Plan: two-gate-review-p2 (rejection + gap groups, third back-translation outcome)

Phase 2 of [[unified-two-gate-restructure]]. Builds on the committed Phase-1 walking skeleton
(`fc3d579` on `feat/two-gate-review`).

## Objective

Make the merged Review queue demonstrate **every gate outcome on real, non-colliding seeded data**, and
teach the expert lens to tell "schema-valid but unusual" from "genuinely inexpressible":

1. Seed three purpose-built groups (no collision with the approved graph) — a **form-reject**, a
   **meaning-reject**, and a **genuine schema-gap** — alongside the existing approve-able cortisol group.
2. **D5 — third back-translation outcome:** a group with no matching pattern renders a **plain structured
   summary** (not a false "系統無法表達"); the gap sentence fires **only** when an explicit
   `possible_schema_gap` flag is set.

## In Scope

- `back_translation.render_understanding`: split the P5 fall-through into (a) flagged gap → P5 sentence,
  (b) unflagged no-pattern → plain structured summary; read `possible_schema_gap` from the proposal.
- Thread `possible_schema_gap` from the seed through `list_groups` into the proposal (storage decision
  below).
- Add 3 groups to `data/sample/expert_demo/review_groups.json` (ids all **absent** from the approved seed;
  existing nodes only *referenced* by edges, never re-proposed).
- Unit tests for the three renderer outcomes; integration coverage that the three new groups list with the
  expected `schema_gate.result` (fail_pattern / pass / needs_schema_extension) and `understanding`.

## Out of Scope

- Retiring the standalone expert-demo screen/endpoint (P4); Ingestion propose toggle (P3); gold/backlog
  repurpose (P5); real-extract per-group staging (P5). No `schema/` type change. No new migration if the
  storage decision below reuses `schema_check`.

## Current-State Evidence

- `back_translation.py:132-138` — the P5 fall-through currently returns a gap for **any** no-pattern
  proposal (the M1 bug, generalized). `render_understanding(proposal, ctx)` already receives the whole
  proposal dict, so a `possible_schema_gap` key can drive the split.
- `engineer_gate.evaluate` keys `back_translation_available` (→ `needs_schema_extension`) off
  `render_understanding(...)["is_gap"]` — so once the renderer only sets `is_gap` for flagged gaps, the
  gate automatically stops treating plain non-pattern groups as schema-extension cases. **No engineer_gate
  code change needed** — but its behavior changes, so it needs test coverage.
- `service.list_groups` assembles the proposal from item payloads (stripping `status`); it does not carry
  any group-level flag today. `service.approve_group` already **enforces** the gate (H2) — a
  `needs_schema_extension` gap group is non-`pass`, so 核准 is refused + UI-disabled. Good.
- `stage_demo_review_group` writes per-item `schema_check` JSONB; `review_groups.json` is the demo seed
  source (post-B1).
- The 7 `cases.json` cases mostly collide with the approved seed (why we author new groups); they remain
  the standalone expert-demo, unchanged this phase. Verified: with D5, none of the 7 regress — the only
  no-pattern case (5) carries `possible_schema_gap: true` and stays a gap; case 6 is `fail_pattern`
  (unchanged, and its understanding isn't shown per the M1 guard).
- Baseline: `make test` 146 passed + 1 known unrelated flake.

## Acceptance Criteria

- **A1:** renderer — a proposal with `possible_schema_gap: true` and no pattern → `is_gap=True`, P5 text;
  a schema-valid no-pattern proposal **without** the flag → `is_gap=False`, a plain summary naming the
  node/edge content; existing P1–P4 unchanged.
- **A2:** `GET /admin/review/groups` lists 4 groups — cortisol (`pass`), form-reject (`fail_pattern`),
  meaning-reject (`pass`), gap (`needs_schema_extension`) — each with the expected understanding.
- **A3:** enforcing gate holds — approving the form-reject or gap group → 409; approving cortisol → 200;
  the meaning-reject passes the gate (approve would succeed) but is the one a human rejects.
- **A4:** no collision — every proposed member id in the new groups is absent from the approved graph
  (`make seed` then `GET /nodes/<id>` → 404 for each proposed node pre-approval).
- **A5:** `make test` green except the known flake; ruff/format/mypy clean.

## Contract, Schema, Dependency, Migration Impact

- **Storage decision (needs approval):** thread `possible_schema_gap` **without a migration** by having
  `stage_demo_review_group` merge `{"group_possible_schema_gap": true}` into each member's `schema_check`
  JSONB for a gap group, and `list_groups` set `proposal["possible_schema_gap"]` if any member carries it.
  *Alternative:* a nullable `group_meta JSONB` column (a clean migration like `group_id`, but higher risk
  and more than this demo needs). **Recommend the no-migration reuse.**
- **Contract:** none — endpoint shapes unchanged (an understanding may now be a summary instead of a gap).
- **Dependencies/Migration:** none (with the recommended storage choice).

## Execution Policy

- **Plan revision:** 1 (Draft). **Risk:** **medium** — changes shared `back_translation` (also used by the
  live expert-demo screen) + gate behavior; seed data; no migration.
- **Automation mode:** **one-task-at-a-time** (touches a shared pure function whose output feeds the gate).
- **Approved paths:** `backend/app/graph/back_translation.py`, `backend/app/curation/service.py`,
  `ingestion/pipeline/load_postgres.py`, `data/sample/expert_demo/review_groups.json`, `backend/tests/**`,
  `frontend/app.js` (only if the plain-summary render needs a tweak).
- **Stop conditions:** any need for a migration beyond the storage decision; a `schema/` type change; any of
  the 7 `cases.json` cases regressing; `make test` failing for other than the known flake.
- **Commit/push:** only after review + explicit approval.

## Tasks

### T1 — D5 third outcome in `back_translation.render_understanding`  *(checkpoint)*
- Split the P5 fall-through: if `proposal.get("possible_schema_gap")` → P5 gap (`is_gap=True`); else a new
  outcome `{pattern:"P0", rule_id:"plain_summary", is_gap:False, text: "本提案新增:<類型+label 列表>;關係:
  <src —type→ tgt 列表>。"}` built from the proposal via `lbl()` + `nodeTypeLabel`-equivalent.
- Tests `tests/unit/test_back_translation.py`: flagged-gap → gap; unflagged no-pattern → summary
  (`is_gap False`); P1–P4 unchanged; **regression:** all 7 `cases.json` render as before (case 5 gap, case
  6 fail-path unchanged).

### T2 — gate behavior coverage (no code change expected)
- `tests/unit/test_engineer_gate.py`: a schema-valid no-pattern **unflagged** proposal → `result == pass`
  (was `needs_schema_extension`); a **flagged** one → `needs_schema_extension`. Confirms D5 flows through
  the gate. If evaluate needs a tweak to read the flag, do it here and stop.

### T3 — seed the three new groups + thread the flag  *(checkpoint)*
- `review_groups.json`: add `group:demo_reject_form` (new hormone + incomplete RE → fail_pattern),
  `group:demo_reject_meaning` (new wrong RE referencing existing insulin+blood_glucose, form-valid),
  `group:demo_schema_gap` (new thyroxine/adrenaline/metabolic_rate, no pattern, `possible_schema_gap:true`).
- `stage_demo_review_group` / `stage_demo_review_groups`: accept + persist the gap flag (schema_check reuse);
  `list_groups`: surface `possible_schema_gap` on the proposal.
- Integration test (`test_review_groups.py`): the four seeded groups list with expected gate results;
  each proposed node id 404 pre-approval; approving form-reject/gap → 409, cortisol → 200.

### T4 — frontend check (likely no change)
- Confirm the expert tab renders a plain summary as ordinary understanding text and that 核准 stays disabled
  for `fail_pattern`/`needs_schema_extension` (H2 already does this). Adjust only if the summary needs
  styling. Manual-only (no FE harness) — disclose.

## Verification Strategy

- Unit: the three renderer outcomes + 7-case regression; gate pass/needs_schema_extension by flag.
- Integration: 4-group listing, gate results, no-collision 404s, enforcing-gate 409/200.
- Container: `make test`, ruff/format/mypy, `make seed` + live `curl` of the queue and `/nodes/<id>`.
- Manual: browser pass of 群組審閱 across the four outcomes (esp. the disabled 核准 on form-reject/gap).

## Risks and Unknowns

- **R1:** `back_translation` is shared with the live expert-demo screen — mitigated by the 7-case
  regression test; only the *unflagged no-pattern* path changes, which no current case hits except via the
  M1-guarded case 6.
- **R2:** the meaning-reject group writes a biologically wrong RE if approved — that is the point (the
  expert must reject it); it references, never re-proposes, existing nodes, so no overwrite and the B1
  guard still passes.
- **R3:** `schema_check` reuse for the gap flag conflates a seed hint with computed schema results — low,
  contained to the demo seeder; the `group_meta` column remains the clean upgrade if it ever generalizes.

## Rollback

Revert the renderer split, the seed groups, and the flag threading. No migration (recommended path). Demo
groups are idempotent seed; no approval executed against the graph during development.

## Human Decisions and Approval

- **Decisions required:** (1) storage of `possible_schema_gap` — reuse `schema_check` (recommended) vs a
  `group_meta` migration; (2) confirm the three new groups' shapes above; (3) automation mode
  (one-task-at-a-time proposed); (4) accept the P2 scope (P3–P5 remain roadmap).
- Status: **Approved** (revision 1) — user (jett), 2026-07-24.
- Approved decisions: (1) gap flag via `schema_check` reuse (no migration); (2) three group shapes as
  specified; (3) one-task-at-a-time; (4) P2 scope accepted, P3–P5 roadmap.
- Approval evidence: user "Approve 4 decisions" in-session.
