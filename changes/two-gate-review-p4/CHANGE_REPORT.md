# Change Report: two-gate-review-p4

Branch `feat/two-gate-review-p4` (off `main` @ `c64163b`, P3 merged via PR #12). Uncommitted.
Supervised-auto execution of plan revision 2 (T1, T2).

## Completed

Retired the standalone `審閱` (expert-demo) prototype — the early two-gate screen that unified
`群組審閱` (P1–P3) superseded.

- **Backend:** deleted `app/api/routes_expert_demo.py` and `app/schemas/expert_demo.py`; removed the
  router import + `include_router` in `app/main.py`; removed `service.record_expert_review`. The two
  `/admin/expert-demo/*` endpoints now 404.
- **Backend tests:** deleted `tests/api/test_expert_demo.py` and
  `tests/integration/test_expert_review_log.py`. `test_expert_review_log.py` and two of the three
  tests in `test_expert_demo.py` covered only the retired surface. The third
  (`test_expert_demo_gate_and_understanding_are_computed_live`) *also* pinned an **engine** property
  — case 007's back-translation (form-valid but biologically WRONG direction rendered faithfully),
  the marquee governance demo. That pin is **preserved**, moved to
  `tests/unit/test_back_translation.py::test_case7_form_valid_but_wrong_biology_is_rendered_faithfully`
  (review H1).
- **Frontend:** removed the `expert`/`審閱` VIEWS entry, `renderExpertDemo`, `GAP_OPTIONS`,
  `EXPERT_STORE`, and the function-local `EXPERT_STATUS`/`expertVerdict`; updated one stale comment in
  `renderReview` that referenced the retired screen; bumped `index.html` `?v=20260803-3`. Nav is now
  the intended spine: `問答 / 圖譜 / 典藏 / 收錄 / 群組審閱 / 評估`.
- **Docs:** removed the two `/admin/expert-demo/*` sections from `docs/api_contract.md`; added a
  retirement note to `docs/expert-in-the-loop-plan.md`. **Post-review (B1), the sync was widened** to
  `README.md` (governance walkthrough steps 2/4/6 + the screens table, rewritten onto `收錄`/`群組審閱`)
  and retirement banners/notes in `docs/expert-in-the-loop-workflow.md` +
  `docs/demo-cases-blood-glucose.md` — see the Review remediation table.

## Not completed / deliberately excluded

- **`data/sample/expert_demo/cases.json`, `gold/`, `schema_gap_backlog.json` KEPT.** `cases.json` is a
  shared fixture for `test_back_translation` / `test_engineer_gate` / `test_gold_examples` (the
  two-gate engine + gold regression that group Review relies on); deleting it would break kept tests.
  "Retire" therefore means remove screen + endpoints + `record_expert_review`, not the fixture data.
  Owner-confirmed.
- The open decision on the fate of gold + schema-gap backlog ("guided examples" mode) remains open
  (tracked in [[unified-two-gate-restructure]] decision #3) — untouched here.

## Observable behaviour change

- `GET /admin/expert-demo/cases` and `POST /admin/expert-demo/reviews` → **404** (were 200/201).
- The `審閱` tab is gone from the app; `#expert` hash falls back to the default view.
- Everything else (group Review, Ingestion, query, graph, library, eval) unchanged;
  `GET /admin/review/groups` still 200.
- **Schema-gap capture removed with no replacement (review M1):** `GAP_OPTIONS` (deleted) was the
  only UI producing the "無法表達 / schema gap" expert outcome + the plain-language ⇄ `schema_gap_type`
  mapping in `docs/schema-gap-policy.md`. The surviving group Review offers only 核准 / 退回, so
  `data/sample/expert_demo/schema_gap_backlog.json` + `schema-gap-policy.md` are now orphaned from any
  running surface. Re-introducing a third "record as gap" outcome on group Review (and fixing the P3
  banner at `app.js` that still promises "只能退回或記為 gap") is a **separate follow-up change**.

## Contract / dependency / migration

- **Contract:** removal of `/admin/expert-demo/*` (deliberate deprecation; documented). No other
  endpoint changes.
- **Schema/DB:** none. `graph_change_logs` is generic; removing the only writer of
  `action='expert_review'` needs no migration; existing rows remain valid history.
- **Dependency / migration:** none.

## Review remediation (`REVIEW_REPORT.md`)

Independent review found 1 Blocking, 1 High, 1 Medium, 5 Low, 1 Suggestion. Disposition:

| # | Sev | Disposition |
|---|---|---|
| **B1** README + workflow/demo-cases/plan docs still presented the deleted endpoints/screen as live | Blocking | **Fixed.** `README.md` governance walkthrough (steps 2/4/6) + screens table rewritten onto the surviving `收錄`/`群組審閱` surface (also corrected the P1–P3-era staleness the same lines carried — `審訂`→`收錄`+`群組審閱`, "Five"→"Six screens"); retirement banners added to `docs/expert-in-the-loop-workflow.md` + `docs/demo-cases-blood-glucose.md`; in-body notes at `docs/expert-in-the-loop-plan.md`. Repo-wide grep now shows only retirement notes or banner-covered historical records. |
| **H1** deleted test was the only pin on case 007's back-translation output; reports mis-described it | High | **Fixed.** Pin re-added (see above); the "tested only the retired surface" sentence corrected here + in `VERIFICATION_REPORT.md`. |
| **M1** schema-gap capture removed with no replacement, not disclosed | Medium | **Disclosed** (Observable-behaviour section above); the third-outcome + banner fix is a recorded follow-up. |
| **L2** dead `.ex-*` CSS left behind | Low | **Fixed.** Removed the 6 unreferenced rules (`.ex-src/.ex-note/.ex-notlist/.ex-not/.ex-radio*/.ex-gapwrap`) from `styles.css` (verified 0 token-bounded refs in `app.js`). |
| **L3** `styles.css?v=` bumped though the file was unchanged | Low | **Moot** — `styles.css` now legitimately changes (L2), so the `?v=20260803-3` bump is justified. |
| **L4** CI not run; rollback wording assumed a commit | Low | **Recorded.** CI has not run (change uncommitted); `make eval` not run (no retrieval change). Rollback below corrected. |
| **L5** approval evidence self-asserted | Low | **Recorded.** Owner approved the three decisions in-session (cases.json kept / base=main / supervised-auto); to be confirmed at disposition. |
| **L6** `cases.json` `expert_review` blocks now asserted by nothing | Low | **Recorded** — unpinned fixture data; no current defect. |
| **S1** `data/sample/expert_demo/` legacy dir name | Suggestion | **Recorded** — out of scope; a future rename touches 4 refs. |

## Deviations from plan

- **Doc sync wider than the planned sweep (B1):** the plan scoped docs to `api_contract.md` +
  `expert-in-the-loop-plan.md`; remediation additionally edited `README.md`,
  `docs/expert-in-the-loop-workflow.md`, and `docs/demo-cases-blood-glucose.md` because the review
  found they advertised the deleted endpoints as live (DoD "相關文件已同步"). Disclosed here.
- **Engine regression test added (H1):** a pure-removal change now adds one test
  (`test_case7_...`) to preserve a pin that a deleted file carried — disclosed.
- One in-scope tidy: updated a stale comment in `renderReview` (`frontend/app.js`) naming the
  retired screen — same file, within scope.

## Verification

ruff 0.15.21 check exit 0 + format clean; `mypy backend/app ingestion scripts` clean (77 files);
full offline suite **163 passed** (167 − 5 deleted-surface tests + 1 re-added engine pin;
engine/gold pass); `node --check` OK; endpoints 404 / review 200. **CI has not run** (change
uncommitted); `make eval` not run (no retrieval change). Details in `VERIFICATION_REPORT.md`.

## Limitations / remaining work

- **Owed:** human browser pass of the nav (frontend manual-only). While there, note **N3
  (pre-existing, not this change):** `frontend/app.js:592` uses class `ex-case-body` for which
  `styles.css` has no rule and never had one (predates P4, came in with the P1–P3 group-review
  screen) — surfaced by the L2 bidirectional class audit; worth an eyeball but out of P4 scope.
- The extract→unified-review work (statement segmentation, endpoint resolution, dedup, bulk triage)
  is the next change (pinned scope in [[unified-two-gate-restructure]]).

## Rollback

The change is **uncommitted**, so rollback today is `git checkout -- <files>` (discard the working
tree) — not `git revert`. No migration, no data deletion (`cases.json`/`gold/` retained). Re-adding
the router + `renderExpertDemo` restores the demo surface verbatim. Once committed, `git revert`
applies.

## Handoff

All approved tasks complete, full verification passed. Not committed, not reviewed by the author.
Recommend an independent `review-change` (or the owner's reviewer) + the browser pass before commit.
