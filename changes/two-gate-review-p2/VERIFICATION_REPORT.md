# Verification Report: two-gate-review-p2

Covers T1–T4: D5 third back-translation outcome + gate behavior, three new non-colliding demo groups with
the gap-flag threading, and the frontend check (no change). P3–P5 are roadmap.

## Environment

- Branch `feat/two-gate-review`, baseline `fc3d579` (Phase-1 + remediation). Services up; backend rebuilt
  before the run (`backend/tests` not volume-mounted); restarted once for the live probe.
- P2 diff since baseline (excl. unrelated `docs/agent-guideline.md`): 7 tracked files (+310/−13) + the
  `changes/two-gate-review-p2/` artifacts. No new source module; **no migration** (gap flag via
  `schema_check` reuse, per the approved decision).
- Offline / open-admin mode. Known pre-existing baseline failure: `test_pipeline_run_is_idempotent`.

## Canonical commands

| Command | Exit | Result |
|---|---|---|
| `docker compose build backend` | 0 | rebuilt |
| `make test` (`pytest tests ingestion/tests`) | 1 | **153 passed, 1 failed** (243s) |
| `ruff check` (6 P2 files) | 0 | All checks passed |
| `ruff format --check` (6 files) | 0 | already formatted |
| `mypy` (3 app/ingestion modules) | 0 | Success: no issues |
| `python -c json.load(review_groups.json)` | 0 | valid |

Sole failure: `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent` (`chunk_count 12 != 9`)
— the documented non-pristine-volume flake. P2 touches no chunk pipeline (`stage_demo_review_groups`
writes only `curation_items`), so it cannot cause it. Excluded by the plan's stop conditions.

## Requirement → Implementation → Test → Result

| # | Acceptance | Implementation | Evidence | Result |
|---|---|---|---|---|
| A1 | Renderer: flagged→gap; unflagged no-pattern→plain summary (not gap); P1–P4 unchanged | `back_translation.render_understanding` split | `test_back_translation::test_d5_flagged_no_pattern_is_a_gap`, `test_d5_unflagged_no_pattern_is_a_plain_summary_not_a_gap`; case1–5 tests + gold + expert_demo all green | Pass |
| A2 | Queue lists 4 groups with pass / fail_pattern / pass / needs_schema_extension | `review_groups.json` + `stage_demo_review_groups` + `list_groups` flag | Live `GET /admin/review/groups`: cortisol=pass, reject_form=fail_pattern, reject_meaning=pass, schema_gap=needs_schema_extension | Pass |
| A3 | Enforcing gate: approve form-reject/gap → 409; cortisol → 200; meaning-reject passes gate | `approve_group` (H2, from Phase-1 remediation) + gate results | gate results above; enforcing 409 covered by `test_approve_refuses_when_schema_gate_fails` | Pass |
| A4 | No collision — every proposed member id 404 pre-approval | new ids; meaning-reject references (never re-proposes) existing nodes | Live `GET /nodes/<id>` → 404 for cortisol, somatostatin, thyroxine, insulin_increases_blood_glucose | Pass |
| A5 | `make test` green except known flake; ruff/format/mypy clean | — | 153 passed, 1 known flake; gates clean | Pass |
| D5 gate | unflagged no-pattern → gate pass (was needs_schema_extension); flagged → needs_schema_extension | `engineer_gate` follows renderer `is_gap` (no code change) | `test_engineer_gate::test_d5_unflagged_no_pattern_passes_gate`, `test_d5_flagged_gap_still_needs_schema_extension` | Pass |

## Read-only / manual observations

- Live four-outcome queue (through nginx) and the four 404 pre-approval probes — captured during T3,
  re-confirmed here. `make seed` staged `{cortisol:0/0 (idempotent), reject_form:2/1, reject_meaning:1/3,
  schema_gap:3/0}`.
- 7-case regression: cases 1–5 render unchanged (case 5 stays P5 via its `possible_schema_gap` flag);
  case 6 flips gap→plain-summary but its `fail_pattern` result is unchanged and its understanding is not
  shown (M1 guard) — no observable regression.

## Tests not run / boundaries

- **Frontend rendering/interaction** (T4): no automated FE suite → **manual-only**. `renderReview`
  needed no change (H2 gate-disable already in place, D5 removed the false gap). A human should click the
  four groups in 群組審閱 — the disabled 核准 on form-reject/gap, and the meaning-reject that passes the
  gate but should be rejected.
- The **plain-summary render path is not exercised by the four demo groups** in the UI (form-reject is
  fail_pattern→gate-tab; others match patterns or are flagged gaps) — it is covered by unit/integration
  tests, and will surface in the UI once P3 hand-made / P5 real-extract groups arrive.
- `make eval` not run (retrieval untouched).

## Known risks / review hotspots

1. **Meaning-reject writes a wrong fact IF approved** — by design: the schema gate *can't* catch reversed
   biology, so H2 leaves 核准 enabled and the human is the safeguard. Worth an adversarial look: is the
   "human rejects" framing airtight, and is accidental approval acceptably reversible (re-seed + curation
   delete)?
2. **Frontend UI (manual)** — the one unexecuted surface, same as prior phases.
3. **`schema_check` reuse for the gap flag** — a seed hint stored in a computed-results column; contained
   to the demo seeder, `group_meta` column remains the clean upgrade if it generalizes.
4. **Idempotent flake** — "not a regression" argued from the diff, not a pristine-volume run.

## Post-review remediation (2026-07-24, findings from REVIEW_REPORT.md)

Owner decisions: H1 → **isolate + reset**; M1/M2/S1/S2 taken. Applied and re-verified:

| Finding | Fix | Evidence |
|---|---|---|
| **H1 (High)** | meaning-reject fully demo-namespaced (labels unchanged) so an approve can't touch flagship retrieval; `scripts/reset_demo_review.py` + `make demo-reset` | live: real `blood_glucose` 200 / `demo_blood_glucose` 404; reset round-trip: approve→200→reset→404 + re-queued |
| **M1 (Medium)** | `testability = not is_gap AND pattern complete` — no longer contradicts `pattern_validation` | live form-reject `testability=BAD`; `test_incomplete_pattern_is_not_testable` |
| **M2 (Medium)** | expert tab shows a "未通過 Schema gate / schema gap" banner above the summary for non-`pass` groups (deliberate, recorded divergence) | code; **browser check owed** |
| **S1** | `CHANGE_REPORT.md` added | — |
| **S2** | `group:demo_plain_addition` demos the P0/approvable outcome live | live: `pass` + plain summary + approvable |
| Seed-convergence bug (found here) | convergent delete drops all still-proposed demo items before re-staging | live: 5 groups list with correct outcomes after content change |
| **L1/L2** | recorded, no code (approved D5 tradeoff / `schema_check` reuse) | CHANGE_REPORT |

Re-verified: `make test` → **154 passed, 1 failed** (same known flake); ruff/format/mypy clean; live
5-outcome queue. Frontend M2 banner + isolation labels are **manual-only** — browser pass still owed.

## Summary

**PASS on all automated + endpoint evidence; frontend rendering PENDING a human browser check.** `make
test` 153 passed (sole failure = documented unrelated flake); ruff/format/mypy clean; the Review queue now
demonstrates all four gate outcomes on real, non-colliding data (all proposed ids 404 pre-approval), and
D5 closes the generalized false-gap bug with the 7-case regression intact. No implementation modified
during verification. Not an approval — hand to `review-change` / human acceptance.
