## What & why

Phase 4 of the two-gate governance restructure — a **cleanup**. The `審閱` (expert-demo) screen was
the early prototype of the two-gate presentation; the unified `群組審閱` (Review) built in P1–P3
superseded it, and the two were visibly redundant. This retires the prototype so the nav collapses to
the intended two-page spine — **propose (收錄) + dispose (群組審閱)** — while keeping the two-gate
**engine** and the gold regression net intact. Follows P1 (#10), P2 (#11), P3 (#12).

## Changes

- **Backend:** delete `routes_expert_demo.py` + `schemas/expert_demo.py`, unregister the router in
  `main.py`, remove `service.record_expert_review`. `GET /admin/expert-demo/cases` and
  `POST /admin/expert-demo/reviews` now **404** (deliberate removal of a demo-only surface with no
  consumer besides the retired screen).
- **Frontend:** remove the `審閱` VIEWS entry, `renderExpertDemo`, `GAP_OPTIONS`, `EXPERT_STORE`, and
  six now-dead `.ex-*` CSS rules; nav is now `問答 / 圖譜 / 典藏 / 收錄 / 群組審閱 / 評估`.
- **Tests:** delete the two retired-surface tests. One of them also pinned an **engine** property —
  case 007's back-translation (form-valid but biologically *wrong* direction, rendered faithfully so a
  domain expert can reject it, the marquee governance demo). That pin is **preserved** as
  `tests/unit/test_back_translation.py::test_case7_form_valid_but_wrong_biology_is_rendered_faithfully`.
- **Fixtures kept:** `data/sample/expert_demo/cases.json` + `gold/` remain the shared fixture for the
  engine + gold tests — "retire" excludes the fixture data (deleting it would break kept tests).
- **Docs:** strip `/admin/expert-demo/*` from `api_contract.md`; sync `README.md` (governance
  walkthrough + screens table rewritten onto `收錄`/`群組審閱`) and add retirement notes to the
  expert-in-the-loop plan/workflow + demo-cases docs.

## Review & verification

- **Supervised-auto** execution of plan revision 2; **two independent review rounds**
  (`changes/two-gate-review-p4/REVIEW_REPORT.md`). Round 1 found B1 (docs still advertised the deleted
  endpoints — README is the front door), H1 (a deleted test also pinned the case-007 engine property),
  M1 (schema-gap capture removed), + Low/Suggestion; all **remediated**. Round 2 confirmed every
  finding resolved (no Blocking/High), raising only report-hygiene items, also fixed.
  Dispositions in `CHANGE_REPORT.md`.
- Full offline suite **163 passed** (`docker compose run --rm -e OPENAI_API_KEY= backend pytest tests
  ingestion/tests`); ruff 0.15.21 check + format clean; `mypy backend/app ingestion scripts` clean
  (77 files); `node --check` OK; endpoints 404 / group Review 200.

## Known limitations / owed (disclosed)

- **Schema-gap capture removed with no replacement:** `GAP_OPTIONS` was the only UI producing the
  "無法表達 / record-as-gap" expert outcome; group Review offers only 核准/退回. A **third
  group-Review outcome** (record-as-gap) that re-connects `schema_gap_backlog.json` +
  `docs/schema-gap-policy.md`, and fixes the P3 banner still promising "只能退回或記為 gap", is a
  **follow-up change**.
- **Human browser pass** of the six remaining tabs is owed (frontend has no test harness; served
  bytes + router logic verified, rendering not). Also eyeball pre-existing N3 (`app.js` uses
  `ex-case-body` with no CSS rule — predates P4).
- CI runs `make eval` + a fresh-volume suite on this PR (not exercised locally; no retrieval change).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
