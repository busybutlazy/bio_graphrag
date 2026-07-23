# Review Report: expert-gate-integrity (whole change)

## Review Context

- **Diff base and scope:** working tree vs `main` (change is uncommitted). Attributable diff:
  12 tracked files modified + 2 new source files (`backend/app/schemas/expert_demo.py`,
  `backend/tests/integration/test_expert_review_log.py`) + change artifacts. Covers
  **T1/T5/T6 (G5 rejection cases + tests), T2/T3/T4 (G2 persistence + endpoint + frontend + M1),
  and T10 (README/docs)**. T7–T9 deferred by human decision.
- **Artifacts reviewed:** IMPLEMENTATION_PLAN.md (rev 1, approved), TASK_LOG.md, VERIFICATION_REPORT.md
  (whole-change), CHANGE_REPORT.md (batch-scoped), prior REVIEW_REPORT.md (batch-scoped, non-independent),
  full diff, `engineer_gate.py`, `back_translation.py` mechanism, `service.py`, `routes_expert_demo.py`,
  `schemas/expert_demo.py`, `frontend/app.js`, `cases.json`, `api_contract.md`, `schema.sql`.
- **Independence disclosure:** this review session performed **no implementation** (read-only inspection
  only). However, all artifacts were produced by the same agent workflow, and the earlier
  `REVIEW_REPORT.md` was explicitly **non-independent** (same session as the batch implementation). This
  report supersedes it. A human owner (or a second independent reviewer) should still confirm before
  acceptance. I **independently re-executed the affected backend suites this session** (29 passed — see
  Completion Claim Assessment) and confirmed the marquee gate logic by tracing the code; I did not re-run
  the full `make test` (the unrelated pre-existing flake lives outside the affected suites).

## Completion Claim Assessment

The core completion claims are **substantiated by the code**, not merely by matching assertions:

- **Case 6 → `fail_pattern` (form rejection):** verified mechanically. Its `RegulatoryEffect` has a
  `HAS_EFFECT` in-edge but no `ON_VARIABLE` out-edge, so `engineer_gate._pattern_check`
  (`engineer_gate.py:46`) returns a failure, and `_decide` ranks `fail_pattern` above the other
  failing codes. Correct.
- **Case 7 → `pass` + non-gap understanding + expert `rejected` (meaning rejection):** verified. The
  proposal is a complete three-part `INCREASES` shape → all form checks pass; `render_understanding`
  yields a P1 non-gap sentence; the seeded `expert_review.status="rejected"` carries the biology reason.
  This genuinely demonstrates "valid form ≠ correct meaning". Correct.
- **G2 persistence:** `record_expert_review` reuses `_log_change` to append exactly one
  `graph_change_logs` row; `POST /admin/expert-demo/reviews` is admin-gated, Postgres-only,
  parameterized (no injection), and never touches Neo4j / approved graph / `curation_items`. The
  `graph_change_logs` DDL has **no CHECK constraint** on `action`/`target_type`, so the new
  `expert_review`/`expert_demo_case` values insert cleanly. Correct and safe.
- **Docs/contract:** `api_contract.md`, `expert-in-the-loop-plan.md`, and README accurately describe the
  delivered endpoint (enum, 201 body, side effect, actor). Verified against code.

No Blocking or High defects found. The findings below concern **report integrity, plan-deviation
sign-off, and an unexecuted verification surface** — not correctness of the gate or persistence logic.

## Findings

### Blocking

None.

### High

None.

### Medium

**M1 — CHANGE_REPORT.md does not describe the delivered change (report integrity).**
- Evidence: `CHANGE_REPORT.md` is titled "(batch T1/T5/T6)", lists only cases 6/7 + three test files
  under "Completed", explicitly files **T2/T3/T4** and **T10** under "Not Completed (by design — later
  tasks)", states "Contract / Dependency / Migration Impact: **None in this batch**", and closes "Ready
  for independent review-change." But the working tree **does** contain fully-implemented T2/T3/T4/T10:
  a new public write endpoint (`routes_expert_demo.py`), a Postgres write (`service.py`), a request
  schema, frontend wiring (`app.js`), the contract change (`api_contract.md`), and README/docs.
- Impact: the artifact designated as the change report materially **undercounts** the change — most
  importantly it disclaims the contract change and DB write that are actually present. A human relying on
  CHANGE_REPORT.md (rather than TASK_LOG/VERIFICATION_REPORT, which *are* whole-change) would review the
  wrong, smaller scope and could miss the read-only→read+write surface change entirely.
- Remediation direction (do not implement here): regenerate CHANGE_REPORT.md for the whole delivered
  change so it matches TASK_LOG/VERIFICATION_REPORT scope, including the endpoint, the DB write, and the
  contract impact.

**M2 — Entire T4 frontend surface marked "Pass" but never executed in a browser (verification gap).**
- Evidence: VERIFICATION_REPORT rows G5-B(UI) and G2-B are stamped "Pass"; TASK_LOG T4 and the report
  both disclose the UI was verified only by `node --check`, served-JS grep, and the API contract it
  calls — "visual/interaction rendering is manual-only … not a rendered browser session." The new
  `paintExpert` early-return, the `expertVerdict` banner, the seeded-rejection-by-default behavior
  (acceptance G5-B), and the submit UX have **no** executed proof.
- Impact: any runtime error in the render path would surface only in the browser. Code inspection found
  the closure scope sound and null-guards present (`expertVerdict` guards falsy `review`; every case
  carries a computed `engineer_gate`), so residual risk is **low-to-moderate**, but a "Pass" verdict on
  an unexecuted acceptance clause is a mild overclaim. The report's own Hotspot #1 discloses this, which
  mitigates but does not remove it.
- Remediation direction: before acceptance, do a manual click-through of the 審閱 tab for cases 5/6/7
  (Case 6 shows the "returned at engineer gate" notice, not the P5 gap; Case 7 shows the red verdict by
  default; 送出審查 returns a `change_id`), and re-mark the UI acceptance rows as "verified manually" or
  "pending" rather than a flat automated "Pass".

### Low

**L3 — Endpoint decision enum deviates from the approved plan; needs explicit human sign-off.**
- Evidence: approved plan acceptance **G2-A** and Task T3 specify `decision ∈ {approve, doubt,
  schema_gap}`; the implementation (`schemas/expert_demo.py:14`, `api_contract.md`) uses
  `agree | doubt | cannot`. Disclosed in TASK_LOG T3 ("DEVIATION (disclosed)") and VERIFICATION_REPORT
  Hotspot #4. The plan states "Material plan changes invalidate this approval."
- Impact: the accepted values of a **public request contract** differ from what was approved. The change
  is well-justified (matches the existing frontend radios `agree/doubt/cannot`) and internally
  consistent (frontend, schema, docs, tests all agree), so it is not a correctness defect — but it is a
  contract-surface deviation that the plan's own rule says requires re-approval.
- Remediation direction: obtain explicit human confirmation of the `agree|doubt|cannot` enum (and note
  it in the plan's Human Decisions), or align to the approved wording.

**L4 — Unrelated `docs/agent-guideline.md` modification sits in the worktree.**
- Evidence: `git status` shows `M docs/agent-guideline.md`; TASK_LOG and the plan (Out of Scope,
  Human Decisions #4) confirm it is an unrelated skill-forge self-heal, **not** authored by this change.
- Impact: a `git add -A` / `git commit -a` would bundle an unrelated doc change into this commit. No code
  impact. (Carried from the prior review's L1; still unresolved in the tree.)
- Remediation direction: stage this change's paths explicitly at commit time; exclude `agent-guideline.md`.

**L5 — Lint / type-check not run, though the repo's Makefile/CI enforce them.**
- Evidence: TASK_LOG (T2/T3) and VERIFICATION_REPORT state `ruff`/`mypy` are host-only and were **not
  run**; deferred to CI. This change alters a shared signature (`_log_change` `-> None` → `-> str`) and
  adds a new module and endpoint.
- Impact: a style/type violation would fail CI after handoff. The signature change looks type-consistent
  on inspection (str returned and threaded correctly; existing callers ignore it), so risk is low, but
  the canonical quality gates have not been exercised for the delivered code.
- Remediation direction: run `make lint` / `make format` (and mypy) before commit/CI.

### Suggestion

**S1 — Stale test name.** `test_expert_demo_cases_read_only_contract` now covers a surface that also has a
write endpoint; the "read_only" name is slightly misleading. Consider renaming or adding a comment that it
asserts only the GET contract.

**S2 — Pin the new cases' rendered output.** Case 7's understanding sentence ("使血糖上升") and Case 6's
`fail_pattern`-with-gap fallthrough are asserted only via `is_gap`/result. A direct assertion on Case 7's
rendered text (and on how a form-rejected case should be surfaced) would lock the marquee "form vs meaning"
distinction against renderer drift.

## Requirement and Test Coverage Gaps

- **Automated coverage present & adequate for the backend:** `test_engineer_gate.py` (cases 6/7),
  `test_expert_demo.py` (count 5→7, gate results, `is_gap`, expert status, POST 422/201),
  `test_expert_review_log.py` (one-row audit assertion, incl. schema_gap decision),
  `test_gold_examples.py` (gold net rescoped to `promote==true`). These map cleanly to G5-A/B/C and G2-A.
- **Gaps:** (a) no executed frontend test for any T4 behavior — G5-B(UI) and G2-B rest on manual/code-only
  evidence (M2); (b) `make eval` not run (justified — retrieval pipeline untouched); (c) lint/mypy not run
  (L5). The known pre-existing `test_pipeline_run_is_idempotent` flake is unrelated (change touches no
  `ingestion/` file; expert-demo data is not loaded by the seed/chunk pipeline).

## Compatibility, Security, and Scope Assessment

- **Compatibility:** additive. Existing 5 cases, retrieval, curation, auth, and the `status='approved'`
  invariant are untouched. `GET /admin/expert-demo/cases` shape is unchanged except for two more cases.
  `_log_change`'s new return value is ignored by existing callers (`test_curation.py` still passes per
  reports). No migration.
- **Security:** the new endpoint stays behind `require_admin`; writes only append-only
  `graph_change_logs` rows via a parameterized asyncpg insert; `action`/`target_type` are hardcoded
  constants and `case_id` is bound as a parameter — no SQL/Cypher/label interpolation. No approved-graph
  or curation mutation. `case_id` existence is not validated, but for an admin-gated, audit-only demo log
  this is by design (tests use synthetic ids) and not exploitable. Isolation ("強制隔離") is preserved —
  the expert-facing render shows white-language verdict/notes/`reviewed_by`, no id/schema/gap code.
- **Scope:** all edits fall within the approved path scope (`data/sample/expert_demo/**`,
  `backend/app/**`, `backend/tests/**`, `frontend/app.js`, `docs/**`, `README.md`), except the unrelated
  `docs/agent-guideline.md` noise (L4). The read-only→read+write contract change was **explicitly
  approved** in the plan (Human Decisions #2), so it is in-scope though it remains the primary reviewer
  hotspot.

## Unreviewed Areas and Residual Risk

- **Affected backend suites independently re-run this session (29 passed):** `test_engineer_gate`,
  `test_back_translation`, `test_expert_demo` (incl. POST 422/201), `test_gold_examples`,
  `test_expert_review_log`, and `test_curation` (regression on shared `_log_change`) — after rebuilding
  the backend image (tests are not volume-mounted). Gold-net match (`promoted == gold`, 5 each) and case
  status/render coherence were also verified independently. I did **not** re-run the full `make test`;
  the sole reported failure (`test_pipeline_run_is_idempotent`) is the documented pre-existing flake,
  outside the affected suites.
- **Rendered frontend behavior** (M2) — not executed; low-to-moderate residual UI risk.
- **The "idempotent flake is not a regression" claim** is argued from the diff, not a pristine-volume
  before/after run — low residual risk (carried L2 from prior review).
- **Lint/type-check** (L5) — not exercised on the delivered code.

## Human Disposition Required

Recommended disposition: **accept the implementation as functionally correct and safe**, contingent on the
human owner (1) regenerating CHANGE_REPORT.md to whole-change scope (M1), (2) doing/So recording a manual
browser click-through of cases 5/6/7 and downgrading the UI "Pass" claims to manual-verified (M2),
(3) confirming the `agree|doubt|cannot` enum deviation (L3), (4) staging paths explicitly to exclude
`agent-guideline.md` at commit (L4), and (5) running `make lint`/mypy before CI (L5).

The reviewer does not approve, fix, merge, or release this change.
