# Verification Report: two-gate-review-p4

> **/verify-change re-run (2026-08-03) — reproduced.** The supervised-auto run's checks reproduced:
> ruff 0.15.21 check + format clean; `mypy backend/app ingestion scripts` clean (77 files);
> `node --check` OK; endpoints `GET /admin/expert-demo/cases` + `POST .../reviews` → **404 / 404**,
> `GET /admin/review/groups` → **200**.
>
> **Post-review remediation (`REVIEW_REPORT.md`, 2026-08-03).** After that pass, an independent
> review found B1 (docs still advertised the deleted endpoints), H1 (a deleted test also pinned an
> engine property), M1 (schema-gap capture removed), L2 (dead CSS) + Low/Suggestion. Remediated:
> README + workflow/demo-cases/plan docs synced; the case-007 back-translation pin re-added as
> `tests/unit/test_back_translation.py::test_case7_form_valid_but_wrong_biology_is_rendered_faithfully`;
> 6 dead `.ex-*` CSS rules removed; disclosures added (see `CHANGE_REPORT.md`). Post-remediation:
> full offline suite **163 passed** (exit 0); `test_back_translation` = 9 passed; ruff+mypy+node
> clean. **CI has not run** (uncommitted); `make eval` not run (no retrieval change). Correction to
> the body below: the deleted `test_expert_demo.py` was NOT "only the retired surface" — one of its
> tests pinned the engine's case-007 rendering, now preserved.

## Result

- Overall: **Pass** (automated backend/lint/type + endpoint checks all green; one owed item is a
  human browser pass of the nav — frontend has no test harness).
- Environment: branch `feat/two-gate-review-p4` (uncommitted working tree vs `main` @ `c64163b`,
  P3 merged). Docker/Compose; ruff `ghcr.io/astral-sh/ruff:0.15.21` (CI-pinned); mypy 1.15.0 host.
  Offline posture (`-e OPENAI_API_KEY=`) per project design (the host `.env` key is credit-exhausted).
- Diff scope (post-remediation): 4 files deleted (`routes_expert_demo.py`, `schemas/expert_demo.py`,
  `tests/api/test_expert_demo.py`, `tests/integration/test_expert_review_log.py`); **11 modified**
  (`main.py`, `curation/service.py`, `tests/unit/test_back_translation.py`, `README.md`,
  `docs/api_contract.md`, `docs/expert-in-the-loop-plan.md`, `docs/expert-in-the-loop-workflow.md`,
  `docs/demo-cases-blood-glucose.md`, `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`);
  `changes/two-gate-review-p4/` added. 15 files, +42/−621.

## Requirement Traceability

| Acceptance criterion | Implementation | Test / observation | Result |
|---|---|---|---|
| AC1 expert-demo endpoints 404; routes/schema/service/tests removed; no backend refs | deleted files + `main.py`/`service.py` edits | `curl` both → **404**; `grep -rn "expert_demo\|record_expert_review\|ExpertReview" backend/app` → none | Pass |
| AC2 engine + gold suites still pass (cases.json kept) | `cases.json`/`gold/` untouched | full suite **163 passed** incl. `test_back_translation` (9, with the re-added case-007 pin) / `test_engineer_gate` / `test_gold_examples` | Pass |
| AC3 `審閱` tab gone; nav correct; no dangling FE refs; node --check; `?v=` bumped | `app.js` VIEWS + block removal; `index.html` bump | served nav = `問答/圖譜/典藏/收錄/群組審閱/評估`; `grep` removed symbols → no code refs; `node --check` OK; `?v=20260803-3` | Pass |
| AC4 api_contract no longer documents /admin/expert-demo/* | `api_contract.md` edit | `grep expert-demo docs/api_contract.md` → none | Pass |
| AC5 full suite + lint/type green | — | **163 passed**; ruff check exit 0 + format clean; mypy 77 files clean | Pass |
| Group Review / Ingestion unaffected | not touched | `GET /admin/review/groups` → **200** | Pass |

## Commands Executed

| Command | Exit | Result |
|---|---:|---|
| `ruff 0.15.21 check backend/app backend/tests ingestion scripts` | 0 | All checks passed |
| `ruff 0.15.21 format --check …` | 0 | 99 files already formatted |
| `mypy backend/app ingestion scripts` | 0 | no issues in 77 source files (was 79; −2 deleted) |
| rebuild `docker compose build backend` | 0 | image built (deleted tests dropped) |
| `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests` | 0 | **163 passed** (167 − 5 deleted-surface tests + 1 re-added case-007 engine pin) |
| `node --check frontend/app.js` | 0 | OK |
| `curl /admin/expert-demo/cases` / `.../reviews` (after restart) | — | **404 / 404** |
| `curl /admin/review/groups` | — | **200** |

## Tests Added or Modified

**Added (remediation, review H1):** `tests/unit/test_back_translation.py::test_case7_form_valid_but_wrong_biology_is_rendered_faithfully`
— re-pins case 007's rendered direction phrase (a property a deleted test carried). Deleted
`tests/api/test_expert_demo.py` and `tests/integration/test_expert_review_log.py`:
`test_expert_review_log.py` + two of the three tests in `test_expert_demo.py` covered only the
retired surface; the third pinned the case-007 engine property, now preserved by the added test. The
other engine/gold tests that share `cases.json` are unchanged and pass.

## Tests Not Run

| Check | Reason | Consequence |
|---|---|---|
| Frontend nav visual/interaction | No FE test harness | Owed human browser pass (nav routes, `#expert` hash → chat fallback, no console errors); functional removal proven by `node --check` + grep + served nav |
| `make eval` | Out of scope; no retrieval/eval change | none |
| Bare `make test` with host `.env` key | key credit-exhausted → online path fails at seed/test | ran offline equivalent (documented posture) |

## Manual Verification and Mock Boundaries

No mocks. Endpoint 404s observed against the live nginx→backend stack after a backend restart.
`cases.json`/`gold/` deliberately retained as engine/gold test fixtures (deleting them would break
kept tests — the reason "retire" excludes the fixture data).

## Known Risks, Blockers, and Human Review Hotspots

- **Contract removal:** `/admin/expert-demo/*` deleted — deliberate deprecation of a demo-only
  surface with no consumer besides the retired screen. Confirm no external caller relies on it.
- **Owed browser pass** of the nav (hotspot): frontend manual-only.
- **`data/sample/expert_demo/` dir name** is now slightly legacy (holds `cases.json`, `gold/`,
  `schema_gap_backlog.json`, and the seed's `review_groups.json`); renaming is out of scope.
- Environment: host `.env` `OPENAI_API_KEY` exhausted — verification used offline posture.

## Unsupported Claims

- No claim of frontend *visual* correctness beyond parse/serve/nav-labels — the human browser pass
  is owed. No performance/security-scan claims (this change only removes surface).
