# Task Log: two-gate-review-p2

- Plan revision: 1 (Approved) — user (jett), 2026-07-24. Mode: one-task-at-a-time.
- Baseline: `feat/two-gate-review` @ `fc3d579`; `make test` 146 passed + 1 known unrelated flake.

## T1 + T2 — D5 third back-translation outcome + gate coverage

- Boundary/paths: `backend/app/graph/back_translation.py`, `backend/tests/unit/{test_back_translation,test_engineer_gate}.py`.
- Precheck: verified `cases.json` case 5 carries `possible_schema_gap=True` (0 edges) → stays a gap under
  D5; case 6 flips gap→summary but result stays `fail_pattern` and its understanding isn't shown (M1
  guard), and no test asserts its `is_gap`. No regression.
- Change: `render_understanding` P5 fall-through split — `possible_schema_gap` true → P5 gap
  (`is_gap=True`); else a new `P0`/`plain_summary` (`is_gap=False`) naming the concepts in 白話 (labels
  only, isolation-safe). `engineer_gate` needs **no** code change — it keys off the renderer's `is_gap`,
  so an unflagged no-pattern group now yields `pass` instead of `needs_schema_extension`.
- Tests added: `test_d5_flagged_no_pattern_is_a_gap`, `test_d5_unflagged_no_pattern_is_a_plain_summary_not_a_gap`;
  gate `test_d5_unflagged_no_pattern_passes_gate`, `test_d5_flagged_gap_still_needs_schema_extension`.
- Verify: `pytest test_back_translation test_engineer_gate test_gold_examples test_expert_demo` → **26 passed**
  (D5 + full 7-case regression). ruff check + format clean; `mypy back_translation.py` → Success.
- Deviations: T1 and T2 done together (T2 was no-code-change, tests only, as the plan predicted).
- Result: Pass — **checkpoint: stop for human before T3 (seed the three new groups).**

## T3 — seed the three new groups + thread the gap flag

- Boundary/paths: `data/sample/expert_demo/review_groups.json`, `ingestion/pipeline/load_postgres.py`,
  `backend/app/curation/service.py`, `backend/tests/integration/test_review_groups.py`.
- Change:
  - `review_groups.json`: added `group:demo_reject_form` (new hormone + incomplete RE → fail_pattern),
    `group:demo_reject_meaning` (new wrong RE **referencing** existing insulin+blood_glucose, never
    re-proposing them → gate pass, human rejects), `group:demo_schema_gap` (`possible_schema_gap:true`,
    no pattern). All new ids; verified 404 pre-approval.
  - `stage_demo_review_group`: new `possible_schema_gap` param → stashes `group_possible_schema_gap`
    into each member's `schema_check` (no migration, per approved decision).
  - `list_groups`: surfaces `possible_schema_gap` on the proposal if any member carries the hint → drives
    D5 renderer + the enforcing gate.
- Tests: `test_seeded_gap_flag_flows_to_gate_and_lens` (flagged → gap + needs_schema_extension),
  `test_seeded_unflagged_no_pattern_is_plain_summary_and_passes_gate` (unflagged → summary + pass).
- Verify: `pytest test_review_groups.py` → **12 passed**. Live `make seed` + `GET /admin/review/groups`
  shows the four-outcome spectrum (pass / fail_pattern / pass / needs_schema_extension); all four proposed
  node ids → **404** pre-approval (no collision). ruff/format/mypy clean.
- Deviations: None. Idempotent + convergent seed (stale groups retired on re-seed).
- Result: Pass.

## T4 — frontend check (no code change)

- Verified `renderReview.reviewActions` gates on `schema_gate.result === 'pass'` (from the a23d9ac
  remediation): form-reject + gap → 核准 disabled; meaning-reject + cortisol → enabled. Plain-summary
  understanding renders as text; D5 removed the false-gap so the M1 concern does not recur in the merged
  view. No JS change required.
- Verification: `node --check frontend/app.js` OK (unchanged). **Rendering/interaction manual-only** — a
  human should click through the four groups in 群組審閱 (esp. the disabled 核准 on form-reject/gap and
  the meaning-reject that passes the gate but should be rejected). No FE harness.
- Result: Pass (no change) — **P2 tasks (T1–T4) code-complete → hand to change-wide verify-change.**

## Post-review remediation (2026-07-24)

Findings from `REVIEW_REPORT.md`. Owner decisions: **H1 → isolate + reset**; M1/M2/S1/S2 taken.
- **H1:** meaning-reject group re-namespaced to demo-only ids (labels 胰島素/血糖 unchanged) → an approve
  can't pollute flagship retrieval; added `scripts/reset_demo_review.py` + `make demo-reset` (deprecates
  demo-origin approvals, re-queues them). Verified: real bg 200 / demo bg 404; reset round-trip works.
- **M1:** `engineer_gate` testability = `not is_gap AND pattern complete` (no longer contradicts
  pattern_validation). Regression test added.
- **M2:** merged Review expert tab shows a banner for non-`pass` groups (deliberate divergence, recorded).
- **S1:** `CHANGE_REPORT.md` added. **S2:** `group:demo_plain_addition` demos the P0/approvable outcome.
- **Seed-convergence bug** (found in verification): convergent delete now drops all still-proposed demo
  items before re-staging, so content changes converge. Fixed + re-verified.
- **L1/L2:** recorded, no code (approved tradeoffs).
- Re-verified: `make test` 154 passed + 1 known flake; ruff/format/mypy clean; live 5-outcome queue +
  demo-reset. **Frontend M2 banner / isolation labels: browser check still owed.**
