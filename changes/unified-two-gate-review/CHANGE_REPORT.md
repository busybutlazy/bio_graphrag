# Change Report: unified-two-gate-review (Phase 1 walking skeleton + post-review remediation)

Covers the Phase-1 commit (`01a08a1`) **and** the remediation applied after the independent review
(`REVIEW_REPORT.md`). Phases P2–P5 remain roadmap.

## Completed

### Phase 1 — group-level two-gate review (T1–T5)
- **T1** `curation_items.group_id` (nullable, idempotent DDL in `schema.sql` + `ensure_schema`).
- **T2** `service.list_groups` assembles grouped items into a `{proposed_nodes, proposed_edges}`
  proposal — the shape `engineer_gate` and `back_translation` already expect — and attaches both a live
  Schema gate and the expert-lens understanding. `approve_group` / `reject_group` act on the whole
  statement, transactionally, with an audit row.
- **T3** demo proposal group seeded by `make seed`.
- **T4** `GET /admin/review/groups`, `POST /admin/review/groups/{id}/approve|reject` (admin-gated),
  documented in `docs/api_contract.md`.
- **T5** 群組審閱 frontend view: three tabs (提案內容 / Schema gate / 專家審閱) + approve/reject.

### Post-review remediation
- **B1 (blocking)** — the original seed group reused ids already `approved`, so approving would have
  silently MERGE-overwritten curated labels/descriptions and added duplicate edges, and the invariant was
  a no-op. Fixed **both** ways per owner decision: (a) new seed source
  `data/sample/expert_demo/review_groups.json` proposing genuinely new knowledge (cortisol raises blood
  glucose; no id collides), plus convergent retirement of stale demo groups on re-seed; (b)
  `approve_group` refuses (409) when any member id already exists approved.
- **H2** — Schema gate is now **enforcing**: `approve_group` returns 409 unless `result == 'pass'`, and
  the UI disables 核准 with an explanation. (Audited engineer override deferred — "enforcing now,
  override later".)
- **M1** audit records full payloads + `item_ids` + gate result. **M2** new routes use the documented
  `{"error":{code,message}}` contract. **M3** 409 covered; row select moved inside the transaction with
  `FOR UPDATE`. **L1** result banner survives the repaint. **L2** non-`create` actions refused (422).
  **S1** tab relabelled 提案內容. **S3** referenced approved nodes resolve real labels in the lens.

## Not Completed (deferred / recorded)
- **A4 fault-injection** (simulated mid-write rollback) — still not tested; transactionality evidenced on
  the happy path plus `FOR UPDATE`.
- **Roadmap P2–P5**: all 7 cases incl. rejection cases as seeded groups; Ingestion propose toggle; the
  third back-translation outcome; retiring the standalone expert-demo screen/endpoint; gold/backlog
  repurpose; per-group staging in the real extract path.
- Cross-DB atomicity remains bounded (Neo4j MERGE idempotent inside the pg transaction).

## Files Changed (remediation, on top of `01a08a1`)
- Added: `data/sample/expert_demo/review_groups.json`, `changes/unified-two-gate-review/CHANGE_REPORT.md`.
- Modified: `backend/app/curation/service.py`, `backend/app/api/routes_review.py`,
  `backend/tests/integration/test_review_groups.py`, `backend/tests/api/test_review.py`,
  `ingestion/pipeline/load_postgres.py`, `ingestion/pipeline/run.py`, `frontend/app.js`,
  `docs/api_contract.md`, `changes/unified-two-gate-review/{VERIFICATION_REPORT,TASK_LOG}.md`.
- **Not part of this change** (leave unstaged): `docs/agent-guideline.md` (skill-forge self-heal).

## Observable Behavior Change
- New review surface: `GET /admin/review/groups`, `POST .../{id}/approve|reject`; 群組審閱 UI view.
- The seeded demo group is now genuinely new knowledge — **invisible to retrieval until approved**
  (`GET /nodes/hormone:cortisol` → 404 pre-approval), which is the governance headline.
- Approval refuses malformed groups, non-`create` actions, and anything that would overwrite existing
  approved knowledge. Errors on the new routes use `{"error":{code,message}}`.
- Unchanged: `/admin/curation/*`, `/admin/expert-demo/*`, retrieval, auth, the `status='approved'` invariant.

## Contract / Dependency / Migration Impact
- **Migration:** additive nullable `group_id`; idempotent; existing per-element curation untouched.
- **Contract:** additive endpoints; approve gained documented 409/422 refusal semantics.
- **Dependencies:** none.

## Deviations
- Plan T4 named `backend/app/schemas/review.py`; implementation reuses
  `app.schemas.curation.ApproveRejectRequest` (identical shape — no new DTO). Logged per review S2.
- New routes intentionally diverge from `/admin/curation/*`'s `{"detail"}` error shape to follow CLAUDE.md.

## Verification
`make test` → **146 passed, 1 failed** (documented unrelated `test_pipeline_run_is_idempotent` flake);
review suites 14 passed; ruff/format/mypy clean; `node --check` OK; live probes through nginx. Frontend
rendering was manually confirmed by the owner pre-remediation; **the L1/H2/S1 UI changes made after that
pass have not been re-checked in a browser.**

## Rollback
Revert the remediation files and the Phase-1 commit. The `group_id` column is additive/nullable. No demo
approval was executed against the live graph, so no curated knowledge was mutated at any point.

## Handoff
Independent review already performed (`REVIEW_REPORT.md`) and its findings addressed here. Recommend a
short re-review of the remediation (esp. B1/H2 guards) plus a browser re-check of the UI changes.
