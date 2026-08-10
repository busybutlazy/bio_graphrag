# Verification Report: group-review-gap-outcome

## Result

- Overall: **Pass**. All automatable checks green, and the human browser pass (plan condition 6) was
  **completed by the owner** — all four scenarios verified, each corroborated against Postgres. See
  "Browser Pass" below.
- Environment: branch `feat/group-review-gap-outcome` @ `ddaf281` (rebased onto `main` @ `da2eed2`,
  which merged PR #14 repo/CI hardening). Start gate satisfied: **P4 merged** (`705e61c`).
  Docker/Compose; ruff `ghcr.io/astral-sh/ruff:0.15.21` (CI-pinned); mypy 1.15.0 on the host
  (`make lint` runs it there — it is not in the backend image).
- **Online posture.** The owner topped up the OpenAI account mid-task, so `make seed` and `make test`
  ran with a live key (real embeddings, not the lexical fallback). Targeted backend runs additionally
  used the offline posture `-e OPENAI_API_KEY=`.
- Diff scope: Task 1 committed as `ddaf281` (7 files, +674/−12). Task 2+3 in the working tree:
  `frontend/app.js`, `frontend/styles.css`, `frontend/index.html`, `docs/api_contract.md`,
  `docs/schema-gap-policy.md`, `changes/group-review-gap-outcome/*`.

## Requirement Traceability

| Acceptance criterion | Implementation | Test / observation | Result |
|---|---|---|---|
| AC1 `POST .../gap` → 200, items `schema_gap`, one audit row with `schema_gap_type`+`item_ids`, nothing in Neo4j, leaves the queue | `service.record_group_gap`, `routes_review.py` | `test_record_gap_flips_status_audits_once_and_leaves_queue`; live `curl` → `200 {"status":"schema_gap","schema_gap_type":"permissive_effect"}` | Pass |
| AC2 guards 404 / 409 no-proposed / 409 wrong gate / 422 bad type / 422 blank reviewer | guard chain in `record_group_gap` | `test_double_record_gap_is_409`, `test_record_gap_refuses_a_non_gap_group`, `test_record_gap_rejects_unknown_type_blank_reviewer_and_missing_group`; live `curl` → 409 (pass group, with message) / 422 (bogus type) | Pass |
| AC3 atomicity — status UPDATE + audit INSERT in one transaction | single `async with conn.transaction()` | `test_record_gap_is_atomic` (fault-injects `_log_change`; asserts items still `proposed` **and** no audit row) | Pass |
| AC4 reviewer required + reviewer/reason persisted to audit row and `curation_items` | `422` on blank; `UPDATE … reviewed_by/reason/reviewed_at`; `_log_change(actor, reason)` | happy-path test asserts `actor` + `reason` on the audit row | Pass |
| AC5 frontend shows 記為 gap only for `needs_schema_extension`, with the 6 plain-language options; recording drops the group; 核准 stays disabled | `GAP_OPTIONS` + `reviewActions` | `node --check` OK; **owner browser pass, 4/4 scenarios** (below), each cross-checked in Postgres | Pass |
| AC6 `make demo-reset` re-arms the demo gap group | `_reset_schema_gaps` in `scripts/reset_demo_review.py` | live round trip: record → group absent from `GET /admin/review/groups`; `make demo-reset` → `{'reset_schema_gap_groups': 1}` → group present again | Pass |
| AC7 `make test` green; ruff + mypy clean; `node --check`; `api_contract.md` documents the endpoint | — | **170 passed in 283.77s**; ruff check + format clean; mypy 77 files clean; `node --check` OK; `api_contract.md` §`POST /admin/review/groups/{group_id}/gap` added | Pass |
| approve/reject and `list_groups` unaffected | untouched apart from the gate-flag fix | full suite green incl. the pre-existing group tests | Pass |

## Commands Executed

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_review_groups.py -q
  → 20 passed in 32.99s

make seed → success: 45 nodes / 84 edges / 5 documents / 9 chunks / 5 demo review groups
make test → 170 passed in 283.77s   (P4 baseline 163 + 7 new)

ruff 0.15.21 check (LINT_PATHS)        → All checks passed!
ruff 0.15.21 format --check            → 99 files already formatted
mypy backend/app ingestion scripts     → Success: no issues found in 77 source files
node --check frontend/app.js           → OK
```

HTTP-level contract check through nginx (`http://localhost:8080`):

```
POST .../group:demo_plain_addition/gap  → 409 {"error":{"code":"conflict","message":"… gate result 'pass' …"}}
POST .../group:demo_schema_gap/gap  (schema_gap_type=bogus) → 422
POST .../group:demo_schema_gap/gap  (permissive_effect)     → 200 {"group_id":…,"status":"schema_gap",…}
GET  /admin/review/groups → group absent; after `make demo-reset` → present
```

## Regression Evidence for the approve_group Fix

The new `test_approve_refuses_a_flagged_schema_gap_group` was run against the **pre-fix** code to
prove it is not a tautology:

```
E   Failed: DID NOT RAISE <class 'app.curation.service.CurationError'>
```

i.e. before the fix, `approve_group` really did approve a group the queue and the UI both showed as
`needs_schema_extension`, writing it into the approved graph. Confirmed independently by evaluating
the gate both ways on the seeded group: `approve_group sees (no flag): pass` vs
`queue/UI + gap endpoint see: needs_schema_extension`.

## Browser Pass (condition 6) — completed by the owner, 2026-08-10

Run against the seeded `group:demo_schema_gap` at `http://localhost:8080/app/` → 群組審閱. Every
scenario was corroborated by querying Postgres directly, so the evidence is the persisted state, not
just the rendered page.

| # | Scenario | Observed | DB corroboration |
|---|---|---|---|
| ① | Success — pick a gap type → 記為 gap | ok flash; the group left the list; 核准 disabled throughout | 1 audit row `action='schema_gap'`, `actor='demo'`, `gap_type='unknown'` (the reviewer chose 其他), `item_ids` = 3; all 3 `curation_items` → `schema_gap`; **audit `created_at` == items `reviewed_at` to the microsecond**, i.e. one transaction |
| ② | API failure re-arms the buttons | error flash `失敗:review group group:demo_schema_gap has no proposed items`; 退回 + 記為 gap re-enabled; **核准 stayed disabled** | the failed attempt wrote **nothing** — no extra audit row, member statuses unchanged |
| ③ | Double-click fires one request | list removed once, single flash | exactly **1** `schema_gap` row for the operation |
| ④ | Post-refresh the group does not reappear | F5 → group gone, 6 groups remain | status persisted server-side (`status='schema_gap'` leaves `list_groups`) |

**Method note.** Scenario ② was originally specced as "stop the backend and click". That turned out
to be a poor test: the group list itself comes from `GET /admin/review/groups`, so with the backend
down `renderReview` renders an error notice and no list at all — there is nothing left to click, and
recovering requires not refreshing at any point. It was replaced with a **two-tab stale-view test**:
tab A records the gap; tab B, whose list is now stale, clicks 記為 gap and gets the backend's 409.
This exercises the same frontend failure path while also proving a real governance property — two
reviewers racing on one group cannot produce a duplicate audit row or overwrite the first
reviewer's disposition.

An earlier ① run additionally confirmed the free-text `reason` is persisted verbatim to both the
audit row and `curation_items` (`現行 schema 表達不了`); in the final run the owner left it blank,
which correctly stored `NULL`.

## Owed / Not Run

- **CI has not run** (Task 2+3 uncommitted at the time of writing).
- `make eval` not run — no retrieval-path change (gap never writes Neo4j; confirmed by querying the
  three proposed node ids → **0 rows** in Neo4j after a successful record).

## Environment Notes (pre-existing, unrelated, left alone)

- `scripts/wait_for_services.sh` polls port 8000, which `docker-compose.yml` does not expose; it
  times out while the stack is healthy. `make health` (nginx :8080) is the working check.
- `mypy` is absent from the backend image; `make lint` runs it on the host.
- `.sb-row select` in `styles.css` sets `color: var(--text)`, a variable that does not exist in
  `:root`. Noticed while adding `.ex-gap-select` (which therefore inherits instead); not fixed here.
