# Review Report: two-gate-review-p4

## Review Context

- **Diff base and scope:** uncommitted working tree vs `main` @ `c64163b` (branch `feat/two-gate-review-p4`
  has no commits of its own — `git log main..HEAD` is empty). 10 files, +10/−602; `changes/two-gate-review-p4/`
  untracked. Reviewed the whole diff, not a sample.
- **Artifacts reviewed:** `IMPLEMENTATION_PLAN.md` (rev 2), `TASK_LOG.md`, `CHANGE_REPORT.md`,
  `VERIFICATION_REPORT.md`, the full diff, the two deleted test files (via `git show HEAD:…`), the kept
  engine/gold tests, `README.md`, `docs/expert-in-the-loop-workflow.md`, `docs/demo-cases-blood-glucose.md`,
  `docs/schema-gap-policy.md`, `schema/graph_schema.md`, `.github/workflows/ci.yml`, `Makefile`.
- **Checks re-run independently** (read-only, existing containerized/Makefile entrypoints):
  `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests` → **162 passed** (56.98s);
  `ruff 0.15.21 check` (pinned image) → All checks passed; `mypy backend/app ingestion scripts` → Success, 77 files;
  live `curl` through nginx → `GET /admin/expert-demo/cases` **404**, `POST /admin/expert-demo/reviews` **404**,
  `GET /admin/review/groups` **200**, `/health` **200**; served `app/app.js?v=20260803-3` → **0** matches for
  `renderExpertDemo|expert-demo`, nav array = `問答/圖譜/典藏/收錄/群組審閱/評估`.
- **Independence disclosure:** this is a separate reviewer session; I did not author the plan or the
  implementation, and every artifact was read from disk rather than recalled from an implementation
  context. Reduced-independence caveats remain: (a) same agent tooling and repo context as the implementer;
  (b) the plan's approval evidence is self-asserted inside the plan file ("recorded in-session") with no
  independent trace I can verify — see L5; (c) the owed **human browser pass** is outside what I can perform.
  A human should still perform the browser pass and confirm the approval record.

## Completion Claim Assessment

The claim is: the standalone `審閱` (expert-demo) surface is retired, the two-gate engine and gold net are
intact, and everything is verified green.

**The mechanical removal is sound and every automated claim reproduces exactly.** I attempted to break the
numbers and could not: the "162 = 167 − 5" arithmetic is right (the two deleted files contained exactly 3 + 2
tests); the 404s are real against the live stack, not asserted; the served bundle is genuinely clean; no JS
helper was orphaned (`forceLayout`, `svgEl`, `phraseRelation`, `typeColor`, `nodeTypeLabel`, `conceptMap` are
all still used by `renderGraph`/`renderReview`); `_log_change` still has 8 callers after `record_expert_review`
was removed; `#expert` really does fall back to `chat` (`frontend/app.js:150-152` — this was listed as "owed
human verification" but is provable by inspection); and `ingestion/pipeline/load_postgres.py:156` reads
`review_groups.json`, so keeping `cases.json` as a fixture is correct and `make seed` is unaffected.

**The claim of completion does not hold, on two counts:**

1. **Docs are not synced.** The doc sweep was scoped to `docs/api_contract.md` +
   `docs/expert-in-the-loop-plan.md`; `README.md` — the repository front page — still presents the removed
   screen and both removed endpoints as live, inside a section literally headed *"Governance walkthrough
   (all of it runs)"*. `docs/expert-in-the-loop-workflow.md` (the doc README points readers to) is
   likewise untouched. AC1's grep was `backend/app`-scoped, so it could never catch this.
2. **A test deletion is mis-described.** The reports state both deleted files "tested only the retired
   surface". One of them also carried the *only* regression pin on the project's marquee governance
   property (case 007: form-valid, biologically wrong direction), and that pin now exists nowhere.

Neither is a code defect; both are gaps between what was done and what the reports assert, and item 1
fails the project's stated Definition of Done ("相關文件已同步").

## Findings

### Blocking

**B1 — `README.md` and `docs/expert-in-the-loop-workflow.md` still document the deleted endpoints as live.**

- **Evidence:**
  - `README.md:18` (walkthrough step 4, under the heading *"Governance walkthrough (all of it runs)"*):
    "the 審閱 (Expert Review) screen … (`GET /admin/expert-demo/cases`)" — that endpoint now returns **404**
    (reproduced).
  - `README.md:20` (step 6): "(`POST /admin/expert-demo/reviews` records expert-gate decisions)" — **404**.
  - `README.md:78`: the screens table still lists a **審閱 Expert Review** row whose Endpoint column is
    `GET /admin/expert-demo/cases`, pointing to `docs/expert-in-the-loop-workflow.md`.
  - `docs/expert-in-the-loop-workflow.md:16, 43, 48` — present-tense: "實作 … 前端 `renderExpertDemo` Tab3",
    "前端「審閱」分頁(`renderExpertDemo`),資料源 `GET /admin/expert-demo/cases`(唯讀)",
    "專家決定經 `POST /admin/expert-demo/reviews` 寫成 … 稽核列". No retirement note was added here.
  - `docs/demo-cases-blood-glucose.md:167` — same present-tense claim about the POST endpoint.
  - `docs/expert-in-the-loop-plan.md` received a retirement banner at the top, but its body (`:201`, `:290`)
    still states the endpoint as the live data source; a reader must reconcile the two.
  - Why it was missed: AC1 specifies `grep -rn "expert_demo\|record_expert_review\|ExpertReview" backend/app`
    — backend-only. `VERIFICATION_REPORT.md` AC4 only checked `grep expert-demo docs/api_contract.md`.
    A repo-wide grep (which I ran) returns all of the above.
- **Violated requirement:** project DoD "相關文件已同步，無 blocking review finding"; `CHANGE_REPORT.md`
  asserts the docs work is **Completed** with no disclosed doc debt.
- **Impact:** this is a portfolio repository whose README is the front door and whose thesis is auditable
  governance. It currently instructs a reader (or interviewer) to hit an endpoint that 404s, and advertises a
  screen that no longer exists, in a section that promises "all of it runs". The credibility cost lands
  precisely on the thing the project is selling.
- **Bounded remediation:** rewrite `README.md:18/20/78` onto the surviving surface (`群組審閱` /
  `GET /admin/review/groups`, `POST /admin/review/groups/{id}/approve|reject`) and add a retirement banner to
  `docs/expert-in-the-loop-workflow.md` (+ one line in `docs/demo-cases-blood-glucose.md`, and an in-body
  pointer at `expert-in-the-loop-plan.md:201/290`). **Note the scope is larger than a delete:** the README
  table says "Five screens" but lists six rows and mentions neither `收錄` nor `群組審閱` — pre-existing
  staleness inherited from P1–P3, not introduced by P4, but the same edit should fix it. If the owner prefers
  to defer the README rewrite to a follow-up change, that is a legitimate call — but it must then be recorded
  as an explicit, disclosed deviation rather than left as an implicit completion claim.

### High

**H1 — Undisclosed regression-net loss: case 007's back-translation output is now unpinned, and the reports
describe the deleted tests inaccurately.**

- **Evidence:** the deleted `backend/tests/api/test_expert_demo.py::test_expert_demo_gate_and_understanding_are_computed_live`
  asserted, with an explicit warning comment —
  `# marquee "form vs meaning": renderer faithfully reflects the WRONG (reversed) direction / # the expert rejects — pin the text so renderer drift can't quietly erase the point.` —
  that for `blood_glucose_case_007`: `system_understanding["is_gap"] is False` and `"上升" in system_understanding["text"]`.
  After deletion:
  - `backend/tests/unit/test_engineer_gate.py:49` covers case 007's **gate** result only (`== "pass"`).
  - `backend/tests/unit/test_back_translation.py` has **no** case-007 test (cases 1–5 only; verified by reading
    the file and by `grep -rn "case_007" backend/tests/`, which returns exactly one hit — the gate test).
  - `backend/tests/gold/test_gold_examples.py` covers only *promoted* cases, and `test_every_promoted_case_has_a_gold_file`
    ties that set to `data/sample/expert_demo/gold/` = cases 001–005. Case 007 is deliberately excluded
    (it is a rejection case), so gold structurally cannot cover it.
- **Violated requirement:** DoD "變更報告已產生，無未揭露偏差". `CHANGE_REPORT.md` and
  `VERIFICATION_REPORT.md` both state the deleted files "tested only the retired surface" — that is true of
  `test_expert_review_log.py` and of two of the three tests in `test_expert_demo.py`, but not of this one,
  which pinned engine behaviour that the change explicitly promised to keep ("the two-gate **engine** …
  and its regression nets are kept").
- **Impact:** the demonstration the whole governance thesis rests on — a proposal that is *form-valid but
  biologically wrong*, rendered faithfully enough for a domain expert to catch it — now has no automated
  guard on the rendered sentence. A future `back_translation.py` change that dropped or reversed the
  direction phrase for case 007 would pass CI green.
- **Bounded remediation:** add a ~5-line `test_case7_wrong_direction_is_rendered_faithfully` to
  `backend/tests/unit/test_back_translation.py` asserting `pattern`/`is_gap is False` and the direction phrase
  (`"上升"`), mirroring the deleted assertion; then correct the "tested only the retired surface" sentence in
  both reports. If the owner instead accepts the loss, it must be recorded as an accepted deviation.

### Medium

**M1 — Schema-gap capture has been removed from the product with no replacement, and this is not stated as an
observable behaviour change.**

- **Evidence:** `GAP_OPTIONS` (deleted from `frontend/app.js`) was the only implementation of the
  plain-language ⇄ `schema_gap_type` mapping that `docs/schema-gap-policy.md` specifies, and the only UI that
  could produce a `cannot`/"無法表達" outcome. The surviving group Review offers two outcomes only —
  `frontend/app.js:685-724` (`reviewActions`) builds `核准並寫入` + `退回` and nothing else — while its own
  banner at `frontend/app.js:646` tells the reviewer the proposal "只能退回**或記為 gap**". After P4,
  `data/sample/expert_demo/schema_gap_backlog.json` and `docs/schema-gap-policy.md` are orphaned from any
  running surface. (The banner-vs-actions mismatch is P3 code, unchanged here — P4 removes the other half of
  the loop.)
- **Violated requirement:** `CHANGE_REPORT.md` §"Observable behaviour change" lists only the 404s and the tab
  removal; the plan mentions the *fate of gold + backlog* as an open decision but not that the gap-capture
  capability disappears with this change.
- **Impact:** a documented governance capability (expert declares "the current schema cannot express this" →
  typed backlog entry) is silently no longer reachable anywhere in the app, and README/workflow docs still
  advertise "schema-gap backlog" as part of the demo (compounds B1).
- **Bounded remediation:** add one line to the change report's observable-behaviour section, and open an
  explicit backlog item for a third outcome on the group Review surface (or amend `frontend/app.js:646` so the
  banner stops promising an action that no longer exists — a separate change, not this one).

### Low

**L2 — Dead CSS left behind; the plan's dead-code claim was broader than the check performed.**
`frontend/styles.css` still defines `.ex-gapwrap`, `.ex-not`, `.ex-note`, `.ex-notlist`, `.ex-radio`, `.ex-src`,
none of which is referenced by any remaining code (verified by diffing the `.ex-*` selector set in
`styles.css` against the `ex-*` class strings in `app.js`; the other ~27 `ex-*` classes are legitimately reused
by `renderReview`). The plan's Verification Strategy claims "grep sweeps confirm no dangling refs to the removed
symbols **in either language**" — the sweep covered JS and Python, not CSS. Impact: dead bytes only; the
inaccuracy is in the claim, not the code. Remediation: drop the six rules, or narrow the claim.

**L3 — `styles.css?v=` was bumped although `styles.css` is unchanged.** `frontend/index.html` moves both assets
to `?v=20260803-3` but the diff touches only `app.js`. Impact: one unnecessary cache invalidation on the
CDN-cached public domain; harmless. Remediation: none required — note it as a convention question (bump only
changed files).

**L4 — CI has not run, and the reports do not say so.** The change is entirely uncommitted, so
`.github/workflows/ci.yml` (which additionally runs `make eval`, correctly listed as not-run) has never
executed against it. The DoD requires "CI 通過（或如實回報未執行的項目與原因）"; CI is not mentioned in either
report. Related: because there is no commit, the stated rollback ("`git revert` / delete the branch") does not
currently apply — today the only rollback is `git checkout --` of the working tree. Impact: low; risk to
`make eval` is genuinely small since retrieval was untouched. Remediation: state CI-not-yet-run in the
verification report, and let CI gate the PR.

**L5 — Approval evidence is self-asserted.** `IMPLEMENTATION_PLAN.md` records "Approval evidence: recorded
in-session; the three decisions above are the approval." There is no artifact outside the plan file that an
independent reviewer can check, and the plan authorises `supervised-auto` execution of a **medium**-risk
change that removes published endpoints. Impact: process traceability, not correctness. Remediation: the owner
should confirm the three decisions (cases.json kept / base = main / supervised-auto) explicitly at disposition.

**L6 — `expert_review` blocks in `data/sample/expert_demo/cases.json` are now asserted by nothing.**
The deleted API test was the only reader of `case["expert_review"]["status"]`; `test_gold_examples.py` keys off
`gold.promote` instead. Impact: unpinned fixture data that a future edit could silently corrupt; no current
defect. Remediation: none required — record it.

### Suggestion

**S1 —** `data/sample/expert_demo/` is now a legacy directory name that also holds `review_groups.json`
(consumed by `ingestion/pipeline/load_postgres.py:156`). Correctly out of scope here; a future rename touches
only four references (3 test files + `load_postgres`).

## Requirement and Test Coverage Gaps

| AC | Claimed | Reviewer verdict |
|---|---|---|
| AC1 endpoints 404, files/symbol removed, no backend refs | Pass | **Confirmed** — 404/404 reproduced live; repo-wide grep shows no code references outside kept fixtures/docs. The grep was `backend/app`-scoped, which is why B1 escaped. |
| AC2 engine + gold suites still pass | Pass | **Confirmed but incomplete** — suites pass, but "the regression nets are kept" is not fully true (H1). |
| AC3 tab gone, nav correct, `node --check`, `?v=` bumped | Pass | **Confirmed** — verified against the nginx-served bundle, not just the source file. `#expert` → `chat` fallback additionally proven at `app.js:150-152`; the reports treated this as owed. |
| AC4 `api_contract.md` no longer documents `/admin/expert-demo/*` | Pass | **Confirmed for that file; the criterion itself was under-specified** — it never covered README or the workflow doc (B1). |
| AC5 full suite + lint/type green | Pass | **Confirmed independently** — 162 passed, ruff clean, mypy 77 files clean. |

Coverage gap: case 007 back-translation output (H1). No new tests were added anywhere in this change; that is
appropriate for a pure removal *except* for the pin identified in H1.

## Compatibility, Security, and Scope Assessment

- **Contract:** a genuine removal of two published `/admin/*` endpoints. I searched the repo for consumers and
  found none outside the deleted screen — the removal is internally consumer-free. External consumers cannot
  be ruled out from inside the repo; the verification report flags this correctly.
- **Security:** net-positive and narrow — one fewer authenticated admin route, one fewer write path into
  `graph_change_logs`. No auth logic touched. The `status='approved'` retrieval invariant is untouched:
  nothing in the diff goes near `cypher_templates.py` or the RAG pipeline. `record_expert_review` never wrote
  Neo4j, so its removal cannot affect the approved graph.
- **Data/migration:** none, as claimed. `graph_change_logs` is generic; historical `action='expert_review'`
  rows remain readable. `schema/graph_schema.md` does not enumerate action values, so no schema doc drift.
- **Backward compatibility:** the only breaking surface is the two endpoints (intended). `#expert` deep links
  degrade to `chat` rather than erroring.
- **Scope:** the diff stays inside the approved path list. The one extra edit (a stale comment in
  `renderReview`) is same-file, in-scope, and was disclosed. No out-of-scope refactors, no over-abstraction,
  no dependency changes, no generated artifacts. Worktree state is fully explained by the plan (uncommitted by
  design; commit permission withheld).

## Unreviewed Areas and Residual Risk

- **Browser pass (still owed):** I verified the served bytes and the router logic, not rendering. Nobody has
  loaded the six remaining tabs in a browser to confirm no console errors and no broken layout from the
  removed CSS-adjacent markup.
- **`make eval`** was not run by anyone (disclosed); I did not run it either. Risk is low — no retrieval code
  changed — but it is a CI gate that has not been exercised.
- **The public domain** (`biograph.busybutlazy.com`) was not checked; the `?v=` bump should handle the edge
  cache, but that is unverified.
- **External consumers** of the removed endpoints cannot be ruled out from inside the repository.
- **My test run used the existing (non-pristine) Postgres volume.** It passed 162/162, including the test
  historically flaky on dirty volumes — so no masking occurred here, but CI on fresh volumes remains the
  authoritative run.
- **Absence of further findings is not proof of correctness.** I did not audit the P1–P3 group-review code
  itself beyond what the removal touches.

## Human Disposition Required

Recommended disposition: **fix B1 before commit** (or downgrade it to a disclosed, deferred deviation by
explicit owner decision), **fix or explicitly accept H1**, and **disclose M1** in the change report. L2–L6 are
record-and-proceed. The implementation itself is clean, correctly fenced, and independently reproduces every
automated claim it makes; what fails is the completeness of the documentation sync and the accuracy of two
sentences in the reports.

The reviewer does not approve, fix, merge, or release this change.

---

# Re-review (round 2) — after the author's remediation

## Scope of this pass

Re-checked every finding above against the current working tree (now 15 changed files, +42/−621; added since
round 1: `README.md`, `frontend/styles.css`, `backend/tests/unit/test_back_translation.py`,
`docs/expert-in-the-loop-workflow.md`, `docs/demo-cases-blood-glucose.md`). All checks re-run from scratch —
no result below is carried over from round 1.

**Re-run evidence:** full offline suite → **163 passed** (56.13s, exit 0); ruff 0.15.21 `check` → All checks
passed; ruff `format --check` → 99 files already formatted; `mypy backend/app ingestion scripts` → Success,
77 files; `node --check frontend/app.js` → OK; live through nginx: `GET /admin/expert-demo/cases` **404**,
`POST /admin/expert-demo/reviews` **404**, `GET /admin/review/groups` **200**.

## Finding disposition

| # | Sev | Author claim | Reviewer verdict |
|---|---|---|---|
| B1 | Blocking | Fixed | **Confirmed fixed** — see verification below |
| H1 | High | Fixed | **Confirmed fixed, and the pin is stronger than the one it replaces** |
| M1 | Medium | Disclosed | **Confirmed** — accurate and appropriately scoped disclosure |
| L2 | Low | Fixed | **Confirmed** — exactly the 6 rules, no collateral |
| L3 | Low | Moot | **Confirmed** — correct reasoning |
| L4/L5/L6/S1 | Low/Sugg | Recorded | **Confirmed recorded** |

**B1 — verified fixed, including the new claims it introduced.** A remediation that rewrites documentation can
introduce fresh falsehoods, so I checked the new README text as claims rather than accepting the edit:

- `README.md:18` now asserts the seeded demo groups include a form-passing/biologically-wrong one, a
  form-rejected one, and a schema-gap one. Verified against live `GET /admin/review/groups`:
  `group:demo_reject_meaning` → gate `pass`, understanding "胰島素會造成一個調控效果:使血糖**上升**。"
  (form-valid, reversed direction, rendered faithfully — exactly as claimed);
  `group:demo_reject_form` → `fail_pattern`; `group:demo_schema_gap` → `needs_schema_extension`, `is_gap` true.
  All three claims are true against real data.
- Every endpoint the new README cites exists: `POST /admin/curation/groups`
  (`routes_curation.py:45`, live probe → 422 on empty body, i.e. routed), `GET /admin/review/groups` +
  `POST /admin/review/groups/{id}/approve|reject` (`routes_review.py:29/34/42`).
- "Six screens" now matches the six-entry `VIEWS` array; the table rows for `收錄`/`群組審閱` replace the
  stale `審訂`/`審閱` rows, so the P1–P3 staleness I flagged as adjacent debt was fixed too.
- All four referenced screenshots exist in `docs/screenshots/`.
- Repo-wide grep: every surviving `expert-demo` mention is now either a retirement note or historical body
  text sitting under an explicit retirement banner (`expert-in-the-loop-workflow.md:3-8`,
  `expert-in-the-loop-plan.md:6-9` + in-body notes at `:201`/`:292`, `demo-cases-blood-glucose.md:167`).
  Leaving the prototype's design record intact under a banner is the right call — it is history, not
  instructions.

**H1 — verified fixed.** `backend/tests/unit/test_back_translation.py:103-111`
(`test_case7_form_valid_but_wrong_biology_is_rendered_faithfully`) restores the pin and tightens it: it
asserts `pattern == "P1"` in addition to the original `is_gap is False` + `"上升" in text`. The pin is real,
not vacuous — a renderer that flipped or dropped the direction phrase fails it. Suite count moves 162 → 163,
matching the claim exactly. The "tested only the retired surface" sentence is corrected in both reports.

**M1 — disclosure verified accurate.** `CHANGE_REPORT.md` §Observable behaviour change now states the
capability loss, names the orphaned `schema_gap_backlog.json` + `schema-gap-policy.md`, and books the
third-outcome plus the `app.js:646` banner fix as a separate follow-up. That is the correct disposition:
adding a gap outcome to group Review is new behaviour, out of scope for a retirement change.

**L2 — verified precisely.** The 6 unreferenced rules are gone from `frontend/styles.css`. `.ex-notes`
(still used by `reviewActions`) is correctly retained — a naive prefix grep flags it as a false positive, so I
checked with token-bounded matching in both directions: all 6 removed classes now have 0 CSS and 0 JS
occurrences, and the served `styles.css?v=20260803-3` confirms it end-to-end.

## New findings from this pass

**N1 (Low) — `VERIFICATION_REPORT.md`'s body is stale relative to its own header.** The header banner records
the remediation and the new **163**, but the Requirement Traceability table (AC2, AC5) still reads
"162 passed", and §Result "Diff scope" still says "6 modified", omitting `README.md`, `frontend/styles.css`,
`backend/tests/unit/test_back_translation.py`, `docs/expert-in-the-loop-workflow.md`, and
`docs/demo-cases-blood-glucose.md`. The banner explicitly corrects one body sentence but does not flag these.
Impact: a reader consulting the traceability table alone gets superseded numbers and an incomplete file list.
Remediation: update the table's two counts and the diff-scope line (or add "superseded — see header" markers).

**N2 (Low) — `CHANGE_REPORT.md` §Completed "Docs:" bullet still lists only `api_contract.md` +
`expert-in-the-loop-plan.md`.** The wider sync appears in the remediation table and in §Deviations, so the
report is not misleading overall, but the Completed section under-reports what was done.
Remediation: one-line edit.

**N3 (informational, pre-existing — not this change's defect).** `frontend/app.js:592` uses class
`ex-case-body`, for which `styles.css` has no rule and never had one (`git show HEAD:frontend/styles.css`
→ 0 matches). It predates P4 and came in with the P1–P3 group-review screen. Surfaced only because the L2 fix
prompted a bidirectional class audit; worth a look during the owed browser pass.

## Residual risk after round 2

Unchanged from round 1 and still owed: the **human browser pass** of the six remaining tabs (no FE test
harness — I verified served bytes, router logic, and class/rule consistency, not rendering); **CI has not
run** (the change is still uncommitted, so `make eval` and the fresh-volume suite are unexercised — now
correctly disclosed in both reports); the **public domain edge cache** is unverified; **external consumers**
of the removed endpoints cannot be ruled out from inside the repo. My suite run again used the existing
non-pristine Postgres volume and passed 163/163 with no masking, but CI on fresh volumes remains
authoritative.

## Round-2 disposition

**All round-1 findings are resolved** — B1 and H1 fixed and independently verified (including the new claims
the README rewrite introduced), M1 disclosed accurately, L2/L3 fixed or correctly moot, the rest recorded.
No blocking or high finding remains. N1 and N2 are report-hygiene items that do not affect the code and can be
fixed in the same pass as the commit; N3 is pre-existing.

The remaining gates are human, not automated: the browser pass, confirmation of the in-session approval
record (L5), and the commit/PR decision — CI will then exercise `make eval` and a fresh-volume run.

The reviewer still does not approve, fix, merge, or release this change.
