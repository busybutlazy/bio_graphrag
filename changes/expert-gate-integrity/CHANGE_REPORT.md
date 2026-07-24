# Change Report: expert-gate-integrity (whole change)

Supersedes the earlier batch-scoped report. Covers the **entire delivered change**: G5 rejection cases
(T1/T5/T6), G2 persistence + endpoint + frontend + M1 fix (T2/T3/T4), and docs/README (T10). T7–T9
(G3/G4/G6) deferred by human decision.

## Completed

### G5 — the gate visibly rejects (T1/T5/T6)
- `data/sample/expert_demo/cases.json`: added **Case 6** (form-reject: incomplete RegulatoryEffect →
  engineer gate `fail_pattern`; `expert_review.status="not_reviewed"`) and **Case 7** (meaning-reject:
  "胰島素會降低血糖" mis-extracted as `INCREASES` → passes the engineer gate but `expert_review.status=
  "rejected"`). Case 7 is the marquee "valid form ≠ correct biology" artifact.
- Tests: `test_engineer_gate.py` (c6 `fail_pattern`, c7 `pass`); `test_expert_demo.py` (count 5→7, c6/c7
  gate, c7 `is_gap` + pinned "使血糖上升" text + expert `rejected`); `test_gold_examples.py` gold-net
  rescoped to `gold.promote==true` (excludes rejection cases).

### G2 — expert reviews persist as auditable records (T2/T3/T4)
- `backend/app/curation/service.py`: `record_expert_review(...)` reuses `_log_change` to append one
  `graph_change_logs` row (`action='expert_review'`, `target_type='expert_demo_case'`,
  `after_state={decision, schema_gap_type}`); `_log_change` now returns its `change_id` (additive).
- `backend/app/schemas/expert_demo.py`: `ExpertReviewRequest` (Literal `decision`, length bounds).
- `backend/app/api/routes_expert_demo.py`: new **`POST /admin/expert-demo/reviews`** (201, admin-gated,
  `actor='demo-viewer'`). Writes only Postgres audit rows — never Neo4j, approved graph, or curation_items.
- `frontend/app.js`: expert tab **送出審查** button POSTs the review; seeded authoritative verdict shown
  read-only by default; **M1 fix** — form-rejected (`fail_*`) cases show a "returned at engineer gate"
  notice instead of the misleading P5 gap sentence.
- Tests: `test_expert_review_log.py` (2 — one-row audit + schema_gap decision); `test_expert_demo.py`
  POST 201/422.

### Docs/README (T10)
- `README.md`: "The one idea" thesis block (governance spine + real-expert career-transition framing) +
  six-step governance walkthrough.
- `docs/api_contract.md`: documents the new POST (request, 201 body, audit-only side effect).
- `docs/expert-in-the-loop-plan.md`: status "尚未實作"→"已實作"; roadmap `[x]`; 2026-07-23 update note
  (§五.4 read-only→append-only-write reversal, G5 cases, M1, deferred items).
- `docs/expert-in-the-loop-workflow.md`, `docs/demo-cases-blood-glucose.md`: cases 6/7 + persistence.

## Not Completed (deferred by decision)
- **T7/T8/T9 (G3/G4/G6)**: Tab3-isolation comment; pin gate verdicts in gold; drop unreachable
  `fail_testability`. Deferred.
- **G1** (document `trigger_direction`): deferred until real-pipeline work.

## Files Changed
- Modified: `backend/app/api/routes_expert_demo.py`, `backend/app/curation/service.py`,
  `backend/tests/api/test_expert_demo.py`, `backend/tests/gold/test_gold_examples.py`,
  `backend/tests/unit/test_engineer_gate.py`, `data/sample/expert_demo/cases.json`,
  `docs/api_contract.md`, `docs/demo-cases-blood-glucose.md`, `docs/expert-in-the-loop-plan.md`,
  `docs/expert-in-the-loop-workflow.md`, `frontend/app.js`, `README.md`.
- Added: `backend/app/schemas/expert_demo.py`, `backend/tests/integration/test_expert_review_log.py`,
  `changes/expert-gate-integrity/*`.
- **Not part of this change** (leave unstaged): `docs/agent-guideline.md` (skill-forge self-heal).

## Observable Behavior Change
- `GET /admin/expert-demo/cases` returns **7** cases (2 new rejection cases).
- **New** `POST /admin/expert-demo/reviews` — the expert-demo surface is now read + append-only audit
  write (was read-only). Every expert-gate decision becomes a `graph_change_logs` row.
- Expert tab: authoritative verdict shown by default; form-rejected cases no longer show the misleading
  gap sentence.
- Unchanged: existing 5 cases, retrieval, curation, auth, `status='approved'` invariant.

## Contract / Dependency / Migration Impact
- **Contract:** ADDS `POST /admin/expert-demo/reviews` (admin-gated, additive). The expert-demo surface
  changed from read-only to read + write — **explicitly approved** (plan Human Decisions #2), documented
  in `api_contract.md`. **Enum deviation:** endpoint uses `agree|doubt|cannot` (frontend-consistent), not
  the plan's literal `{approve, doubt, schema_gap}` — pending explicit human sign-off (review L3).
- **Dependency:** none. **Migration:** none (reuses `graph_change_logs`; no DDL change).

## Verification (see VERIFICATION_REPORT.md)
- `make test` → 132 passed, 1 failed (the documented, unrelated pre-existing idempotent-pipeline flake).
- ruff check + ruff format --check + mypy → clean on delivered code.
- Live end-to-end through nginx: GET→7, POST valid→201+change_id, invalid→422, one audit row written.
- **Frontend rendering: manual verification pending** (no FE harness; browser click-through to be done
  by the human — see VERIFICATION_REPORT hotspot #1).

## Deviations
- Endpoint decision enum reconciled to frontend vocabulary (L3, pending sign-off).
- Rebuilt backend image for test runs (`backend/tests` not volume-mounted).

## Limitations / Remaining Work / Risks
- Frontend UI acceptance (seeded-rejection-by-default, M1 notice, submit UX) not yet executed in a browser.
- Idempotent-pipeline flake "not a regression" argued from diff, not a pristine-volume run.

## Rollback
Per-file; no migration or persisted-state to undo (audit rows are append-only demo data, deletable by
`action='expert_review'`). Revert the 12 modified + 2 new source files.

## Handoff
Whole-change REVIEW_REPORT.md already written (findings addressed here + in VERIFICATION_REPORT). Awaiting
human manual UI verification, enum sign-off (L3), and acceptance.
