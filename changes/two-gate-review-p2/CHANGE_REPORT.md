# Change Report: two-gate-review-p2

Covers P2 (D5 third outcome + rejection/gap demo groups) **and** the post-review remediation of
`REVIEW_REPORT.md`. On `feat/two-gate-review`, baseline `fc3d579`. Not yet committed.

## Completed

### P2 core (T1–T4)
- **D5** — `back_translation.render_understanding` no-pattern fall-through splits three ways: flagged
  (`possible_schema_gap`) → P5 gap; unflagged schema-valid → **P0 plain summary** (`is_gap=False`);
  pattern → P1–P4. `engineer_gate` follows `is_gap`, so unflagged non-pattern groups now `pass`.
- **Seed** — `review_groups.json` demo groups covering every outcome; gap flag threaded via `schema_check`
  reuse (`stage_demo_review_group` → `list_groups`), no migration.
- **Frontend** — no change needed for the base view (H2 gate-disable already present).

### Post-review remediation
- **H1 (High) — isolate + reset** (owner decision). The meaning-reject group is now fully
  **demo-namespaced** (`hormone:demo_insulin`, `physiological_variable:demo_blood_glucose`, a new RE) —
  labels still read 胰島素/血糖 so the teaching is unchanged, but an accidental approve writes only a
  self-contained demo island and **cannot** touch flagship insulin/blood_glucose retrieval (verified: real
  `blood_glucose` 200, `demo_blood_glucose` 404 pre-approval). Added `scripts/reset_demo_review.py` +
  `make demo-reset`, which deprecates demo-origin (`proposed_by='demo'`) approvals and returns them to the
  queue — verified end-to-end (approve → 200 → reset → 404 + re-queued).
- **M1 (Medium)** — `testability` decoupled from `is_gap`: now `not is_gap AND pattern complete`, so an
  incomplete pattern no longer shows `testability ✓` beside `pattern_validation ✕` (verified: form-reject
  `testability=BAD`). Regression test added.
- **M2 (Medium)** — the merged Review 專家審閱 tab now shows a **banner** for a non-`pass` group
  ("未通過 Schema gate … 只能退回" / "schema gap … 只能退回或記為 gap") above the honest post-D5 summary,
  with 核准 disabled — a deliberate, recorded divergence from the (P4-retired) expert-demo screen's hide.
- **S1** — this CHANGE_REPORT added. **S2** — new `group:demo_plain_addition` (胰島 PART_OF 胰臟) exercises
  the P0/approvable outcome live (verified: `pass`, plain summary, approvable).
- **Seed-convergence bug** (found in verification) — the convergent delete now drops **all** still-proposed
  demo items before re-staging, so *content* changes to a group take effect (previously `ON CONFLICT DO
  NOTHING` kept stale items; the meaning-reject briefly mis-listed as `fail_pattern`). Fixed + re-verified.

### Re-review follow-up (2026-07-24)
- Independent re-review passed (every High/Medium resolved; H1 verified end-to-end). Its one new **Low**
  finding — the reset script mutated the graph without an audit row — is **fixed**: `reset_demo_review.py`
  now appends a `graph_change_logs` row (`action='delete'`, `actor='demo-reset'`) per deleted node/edge, so
  even the demo-reset utility is auditable. Verified live (delete rows present after a reset).

## Not Completed (recorded)
- **L1** (approved D5 tradeoff): the gate can no longer auto-discover a gap — gaps are now self-declared via
  the flag. Relevant when P3/P5 groups arrive without a curator setting it. No code change; documented.
- **L2** (approved): `schema_check` reuse for the gap hint conflates provenance; `group_meta` column is the
  clean upgrade if it generalizes. No change.
- Frontend rendering remains **manual-only** (no FE harness) — the M2 banner + isolation labels need a
  human browser pass.
- Roadmap P3–P5 unchanged.

## Files Changed
- `backend/app/graph/back_translation.py` (D5), `backend/app/graph/engineer_gate.py` (M1),
  `backend/app/curation/service.py` (D5 flag surfacing), `ingestion/pipeline/load_postgres.py` (flag
  threading + convergent delete), `data/sample/expert_demo/review_groups.json` (5 groups; H1 isolation +
  S2), `frontend/app.js` (M2 banner), `Makefile` + `scripts/reset_demo_review.py` (H1 reset),
  `backend/tests/unit/{test_back_translation,test_engineer_gate}.py`, `backend/tests/integration/test_review_groups.py`.
- **Not part of this change** (unstaged): `docs/agent-guideline.md`.

## Observable Behavior Change
- Review queue shows five groups spanning all outcomes: approve (P1) / plain-addition (P0, approvable) /
  form-reject (fail_pattern) / meaning-reject (pass, wrong biology — isolated) / schema-gap
  (needs_schema_extension). All proposed ids 404 pre-approval.
- Gate `testability` no longer contradicts `pattern_validation`. Non-`pass` groups show a banner in the
  expert tab. `make demo-reset` undoes demo approvals.

## Contract / Dependency / Migration
- None. No migration (gap flag via `schema_check`). New script + make target are additive.

## Verification
`make test` → **154 passed, 1 failed** (documented unrelated idempotent flake); ruff/format/mypy clean;
live: 5-outcome queue, M1 fix, H1 isolation (real bg intact / demo bg 404), demo-reset round-trip.
Frontend M2 banner/isolation labels: **manual browser check still owed**.

## Rollback
Revert the listed files; delete the script + make target. No migration. `make demo-reset` cleans any demo
approval; real curated knowledge was never mutated (isolation).

## Handoff
Independent `REVIEW_REPORT.md` performed; findings addressed here. Recommend a re-review of the H1
isolation + reset and a browser pass of the M2 banner before commit.
