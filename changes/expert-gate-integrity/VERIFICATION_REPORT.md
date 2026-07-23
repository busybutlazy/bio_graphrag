# Verification Report: expert-gate-integrity (whole change)

Supersedes the earlier batch-scoped report. Covers all implemented tasks: T1, T5, T6 (G5),
T2, T3, T4 (G2 + M1), T10 (docs/README). T7–T9 deferred by human decision.

## Environment

- Branch `main`; services all Up (`docker compose ps`: nginx, backend, neo4j, postgres, qdrant).
- Backend image rebuilt immediately before the run (`docker compose build backend`) — required because
  `./backend/tests` is not volume-mounted (only `./backend/app` is).
- No `OPENAI_API_KEY` / `ADMIN_API_KEYS` (offline + open-admin demo mode, as tests expect).
- Attributable diff (excl. unrelated skill-forge self-heal of `docs/agent-guideline.md`): 12 tracked
  files + 2 new source files + change artifacts — all within intended scope
  (`backend/app`, `backend/tests`, `frontend`, `data/sample/expert_demo`, `docs`, `README.md`).
- Known pre-existing baseline failure: `test_pipeline_run_is_idempotent` (memory:
  known-flaky-idempotent-pipeline-test).

## Canonical commands

| Command | Exit | Result |
|---|---|---|
| `docker compose build backend` | 0 | image rebuilt |
| `make test` (`pytest tests ingestion/tests`) | 1 | **132 passed, 1 failed** (294.6s) |
| `ruff check` (delivered files, via `ghcr.io/astral-sh/ruff` container, repo config) | 0 | **All checks passed** |
| `ruff format --check` (delivered files) | 0 | **7 files already formatted** |
| `mypy backend/app/{api/routes_expert_demo,curation/service,schemas/expert_demo}.py` (host) | 0 | **Success: no issues** |

The single failure is `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`
(`chunk_count 12 != 9`) — residual extract-test chunks on a non-pristine Postgres volume. **Not caused
by this change:** the change touches no `ingestion/` file (see diff), the expert-demo data is not loaded
by the seed/chunk pipeline, and the surplus is +3 while only 2 cases were added. Excluded by the approved
plan's stop conditions.

## Requirement → Implementation → Test → Result

| # | Requirement | Implementation | Test / Evidence | Result |
|---|---|---|---|---|
| G5-A | Demo shows a **form** rejection | Case 6 (`fail_pattern`) | `test_engineer_gate.py::test_case6_incomplete_pattern_fails`; `test_expert_demo.py` (c6) | Pass |
| G5-B (data/gate) | **Meaning** rejection: form-valid, biology wrong | Case 7 (gate `pass`, expert `rejected`) | `test_engineer_gate.py::test_case7_wrong_biology_still_passes_form_gate`; `test_expert_demo.py` (c7) | Pass |
| G5-B (UI) | Seeded rejection reflected by default; form-reject not shown misleading gap (M1) | `paintExpert`/`expertVerdict` in `frontend/app.js` | Code inspection + `node --check` + served-JS; **no browser run** | **Pending manual** (checklist below) |
| G5-C | Suite green with new cases | count 5→7; gold-scope | `make test` 132 passed | Pass |
| G2-A | Expert review persists one audit row | `service.record_expert_review` + `POST /admin/expert-demo/reviews` | `test_expert_review_log.py` (2); `test_expert_demo.py::test_post_review_validates_and_records`; live curl 201 + `DELETE 1` | Pass |
| G2-A | Invalid decision → 422; no graph/curation write | `ExpertReviewRequest` Literal; audit-only service | api test 422; service only calls `_log_change` | Pass |
| G2-B | Frontend persists via endpoint | `buildReviewForm` submit → `api.post` | endpoint proven via nginx (201/422); submit-button wiring **not** browser-run | **Pending manual** (checklist below) |
| Doc-A | Contract + plan/workflow/demo-cases reconciled | `api_contract.md` (T3), plan/workflow/demo-cases (T10) | grep: no stale `[ ]`/"尚未實作"; 7-row table; refs resolve | Pass |
| README-A | Thesis block + six-step walkthrough | `README.md` "The one idea" | describes real endpoints/screens; cited endpoint + cases exist | Pass |

## Read-only / manual observations (distinct from automated tests)

- Live end-to-end through nginx (`:8080`): `GET /admin/expert-demo/cases` → 7; `POST .../reviews` valid
  → `201 {change_id, status:"recorded"}`; invalid decision → `422`; exactly one `graph_change_logs`
  row written then deleted (`DELETE 1`).
- `node --check frontend/app.js` → syntax OK; served `/app/app.js` contains the new code.

## Tests not run / mock boundaries

- **Lint / type-check** (`ruff`, `mypy`): **now run and passing** (review L5) — `ruff check` + `ruff
  format --check` via the official ruff container against the repo's `pyproject.toml`, and `mypy` on the
  delivered app modules on host. All clean. (ruff is not on host nor in the backend image, hence the
  ephemeral ruff container.)
- **`make eval`** (22 golden questions): **not run** — this change does not touch the retrieval pipeline,
  eval data, or thresholds. Out of scope; recommend CI/normal eval unaffected.
- **Frontend rendering/interaction**: no automated FE suite exists → the verdict banner, form-reject
  notice (M1), and submit UX are **manual-only**, verified by code inspection + served JS + the API
  contract they call, not a rendered browser session.
- No new mocks introduced. Offline path unchanged.

## Known risks / human review hotspots

1. **Frontend visual/interaction (highest)** — recommend a manual click-through of the 審閱 tab, esp.
   cases 5/6/7, confirming: Case 6 shows the "returned at engineer gate" notice (not the P5 gap), Case 7
   shows the red "已退回" verdict by default, and 送出審查 records + reports a change_id.
2. **Idempotent-pipeline flake** — "not a regression" argued from the diff + docs, not a fresh
   pristine-volume run. Optional confirmation: `docker compose down -v && make seed && make test`
   (destructive to dev volumes).
3. **Contract surface** — expert-demo went read-only → read + append-only write; reviewer should confirm
   the additive, admin-gated, audit-only design is acceptable (already documented in `api_contract.md`).
4. **Enum deviation** — endpoint decision enum is `agree|doubt|cannot` (frontend-consistent), not the
   plan's literal `{approve, doubt, schema_gap}`.

## Manual verification checklist (frontend — pending human, review M2)

The expert tab render/interaction has no automated test. Human to confirm at `http://localhost:8080/`
(審閱 → click a case → 專家審閱 sub-tab):

1. **Case 6** (腎上腺素會影響血糖 / "未過" badge): shows "此提案在工程師 gate 因形式問題被退回…不進入
   專家審查"; does **NOT** show the "系統目前無法用既有的知識結構完整表達" gap sentence. → [ ]
2. **Case 7** (胰島素會降低血糖濃度): **red** "領域專家已退回…" banner by default; understanding reads
   "…使血糖上升". → [ ]
3. **Case 5** (甲狀腺素… / "需補 schema"): still reaches the expert; shows the gap sentence + a neutral
   "領域專家:此現象現行系統無法完整表達" banner. → [ ]
4. **送出審查** on a pass/gap case: message becomes "已記錄稽核 change:…". → [ ]

Mark each `[x]` when confirmed; any mismatch is a finding.

## Post-review fixes applied (this pass)

After the whole-change review, the deterministic remediations were applied and re-verified: **L5**
lint/type-check now run and pass (table above); **S1** clarifying comment on the GET-only contract test;
**S2** pinned Case 7's rendered "使血糖上升" text. These touched **test/comment code only** (no runtime
change); affected suites re-run green (18 passed). **M1** (whole-change CHANGE_REPORT) regenerated.

## Summary

**PASS on all automated + endpoint evidence; frontend UI verification PENDING a human browser check.**
`make test` → 132 passed (sole failure = documented unrelated flake); ruff/format/mypy clean; live
endpoint checks green (GET→7, POST 201/422, one audit row). The only unexecuted acceptance surface is the
frontend render/interaction (G5-B UI, G2-B) — see the checklist above. Open non-blocking item: enum
deviation sign-off (L3). Not an approval — awaiting human manual UI check + acceptance.
