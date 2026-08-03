# Verification Report: two-gate-review-p3

> **Post-review note (superseding update):** this report was the *pre-review* verification. The
> independent `REVIEW_REPORT.md` then found real defects the automated suite missed — notably **F1**
> (the statement builder staged the wrong node/relation type, a *data* defect hidden behind the
> "visual owed" framing below) and **F2** (dangling edge endpoint silently dropped). Both are now
> **fixed and re-verified**; see `CHANGE_REPORT.md` for the disposition of all findings and the
> post-remediation run (**166 passed**, 23 targeted; F2→422 and F4 `propose_reason` confirmed via
> e2e). Treat the AC5 "Pass (functional) / Owed (visual)" line below as corrected by that trail.

## Result

- Overall: **Pass** (automated backend/contract/lint/type + e2e all green; one owed item is the
  human *visual* browser pass — the functional path is proven).
- Environment and container entrypoint: branch `feat/two-gate-review-p3` (uncommitted working tree
  vs `main` @ `fe4da9e`). All checks via Docker/Compose; ruff via `ghcr.io/astral-sh/ruff:0.15.21`
  (CI-pinned); mypy 1.15.0 on host (matches `make lint`). Docker 29.2.1 / Compose v5.1.0.
  **Offline test posture** (`-e OPENAI_API_KEY=`) per the project's documented design (CLAUDE.md:
  "tests run offline (no key configured)"); see the environment note under Known Risks.
- Diff scope (working tree vs main): 8 files, +347/−169 — `backend/app/curation/service.py`,
  `backend/app/api/routes_curation.py`, `backend/app/schemas/curation.py`,
  `backend/tests/api/test_curation_groups.py` (new), `backend/tests/integration/test_review_groups.py`,
  `docs/api_contract.md`, `frontend/{app.js,index.html,styles.css}`, plus `changes/two-gate-review-p3/`.

## Requirement Traceability

| Requirement (acceptance criterion) | Implementation | Test or observation | Result |
|---|---|---|---|
| AC1 hand-made group stages → listed in group Review with live gate | `service.create_group`; `POST /admin/curation/groups` (`routes_curation.py`) | `test_create_group_appears_in_review_and_approves`; e2e: create `201` → list `proposed_by=human gate=pass` | Pass |
| AC2 approving round-trips into approved graph; B1 guard 409 on approved-id reuse | `create_group` + existing `approve_group` B1 guard | `test_create_group_appears_in_review_and_approves` (approve 200, neo4j status approved); `test_approve_refuses_when_a_member_already_exists_approved`; e2e approve `200` (3+3) | Pass |
| AC3 validation 422 (bad type / empty / over-cap / duplicate id), error contract | `create_group` guards; `_validate_curation_payload`; `_as_api_error` | `test_invalid_type_rejected_422`, `test_empty_group_rejected_422`, `test_over_cap_rejected_422`, `test_duplicate_id_within_group_rejected_422`; e2e empty→`422 invalid_request`, bad type→`422` | Pass |
| AC4 `possible_schema_gap` → `is_gap` + `needs_schema_extension` (D5) | flag threaded via `schema_check` (`create_group`); `list_groups` surfaces it | `test_possible_schema_gap_flag_surfaces_needs_schema_extension` | Pass |
| Condition 1 fixed element cap | `MAX_GROUP_ELEMENTS = 20` (named constant) | `test_over_cap_rejected_422` (21 elements → 422, message names 20) | Pass |
| Condition 2 transaction atomicity | `async with conn.transaction()` around inserts | `test_create_group_is_atomic_on_failure` (fault-injected → whole group rolled back); `test_approve_group_rolls_back_postgres_on_neo4j_failure` | Pass |
| Condition 3 intra-group duplicate-id guard | combined node+edge id check in `create_group` | `test_duplicate_id_within_group_rejected_422` | Pass |
| Condition 4 admin-auth on endpoint | `require_admin` router dependency | `test_endpoint_is_admin_gated` (401 no/ wrong key, 201 valid) | Pass |
| Provenance for hand-made (schema requires `source_chunk_id`) | `create_group` stamps `source_chunk_id:"manual"` when absent | round-trip test sends **no** `source_chunk_id` yet gate=pass + approvable; e2e (frontend-shaped payload) gate=pass | Pass |
| AC5 Ingestion page: `[LLM 抽取] ↔ [人工建構]` toggle; hand-made group visible in 群組審閱 | `renderIngest` wrapper + `paintExtract`/`paintHandmade` (`app.js`) | e2e proves the endpoint the builder posts to; `node --check` clean; served nav shows `收錄`. **Visual layer = owed manual pass** | Pass (functional) / Owed (visual) |
| AC6 `審訂` tab removed; `/admin/curation/*` still respond | removed `curation` VIEWS entry + `renderCuration` | served nav = `問答/圖譜/典藏/收錄/群組審閱/審閱/評估`; `POST /admin/curation/items` → `201` (checked earlier this session); `test_curation.py` green in full suite | Pass |
| AC7 full suite + lint/type green | — | 163 passed; ruff+format+mypy exit 0 | Pass |
| Contract doc updated | `docs/api_contract.md` `POST /admin/curation/groups` section | present in diff | Pass |

## Commands Executed

| Command | Exit code | Counts / relevant result |
|---|---:|---|
| `ruff 0.15.21 check backend/app backend/tests ingestion scripts` | 0 | All checks passed |
| `ruff 0.15.21 format --check …` | 0 | 103 files already formatted |
| `mypy backend/app ingestion scripts` (1.15.0) | 0 | no issues in 79 source files |
| clean slate: `docker compose down -v && up -d` + offline seed | 0 | 45 nodes / 84 edges / 9 chunks / 5 demo groups |
| `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests` | 0 | **163 passed** in 87s |
| `… pytest tests/api/test_curation_groups.py tests/integration/test_review_groups.py -v` | 0 | **20 passed** in 23s |
| e2e via nginx: `POST /admin/curation/groups` (no source_chunk_id) | — | `201`; list `proposed_by=human gate=pass is_gap=False` |
| e2e via nginx: `POST /admin/review/groups/{id}/approve` | — | `200` `{status:approved, nodes:3, edges:3}` |
| e2e guards: empty / bad-type POST | — | `422 {"error":{"code":"invalid_request",…}}` both |
| `node --check frontend/app.js` | 0 | OK |
| served asset check | — | index refs `?v=20260803-1` for both; nav shows `收錄`, no `審訂` |

## Tests Added or Modified

- **New** `backend/tests/api/test_curation_groups.py` (7 tests): round-trip create→review→approve
  (payload carries **no** `source_chunk_id`, proving provenance injection), 4× 422 guards,
  schema-gap flag, admin-auth.
- **Modified** `backend/tests/integration/test_review_groups.py`: added
  `test_create_group_is_atomic_on_failure` (fault-injected rollback) + `import uuid`.

## Tests Not Run

| Test/check | Reason | Consequence |
|---|---|---|
| Frontend visual/interaction (toggle repaint, builder add/remove, gap banner, console errors) | No FE test harness in the project (vanilla JS SPA) | Visual layer unverified by automation — **owed human browser pass**; functional path proven by e2e + `node --check` |
| `make eval` (22 golden questions) | Not in P3 scope; no retrieval/eval change; requires online mode | No eval-threshold evidence produced; P3 does not touch retrieval or the eval path |
| Bare `make test` (with the host `.env` key) | The `.env` `OPENAI_API_KEY` is credit-exhausted (429) → online path fails at seed/test; the documented posture is offline | Ran the offline equivalent instead (same command + `-e OPENAI_API_KEY=`); noted below |

## Manual Verification and Mock Boundaries

- No mocks introduced. `create_group` writes real `curation_items`; `approve_group` writes real
  Neo4j nodes/edges. All e2e went through the real stack (nginx → FastAPI → Postgres/Neo4j) and
  test artifacts were cleaned up (Postgres rows + `graph_change_logs` + Neo4j nodes deleted).
- Offline mode uses the project's deterministic paths (hash embeddings / extractive answers); the
  new endpoint does not touch the LLM at all, so offline vs online is immaterial to it.

## Known Risks, Blockers, and Human Review Hotspots

- **Environment (not a code defect):** the host `.env` `OPENAI_API_KEY` has no credits (429).
  Bare `make test`/`make seed` fail on it; verification used the documented offline posture. The
  owner may want to clear or replace that key so CI/`make test` run clean without the override.
- **Owed visual pass** (hotspot): the toggle + statement-builder DOM/CSS and the Review gap banner
  need a human browser check. Note the earlier edge-hugging + CDN-cache issues were found and fixed
  during the owner's live review (`.sb-wrap` padding/`max-width`; `?v=20260803-1` cache-bust,
  owner-confirmed). See [[public-domain-cdn-cache]].
- **Scope boundaries (intentional, disclosed):** LLM-extract per-group staging remains **P5**
  (extract still stages ungrouped per-item; the Ingestion page discloses this). Comprehensive
  app-wide RWD deferred to a **future phase** (owner's call). `/admin/expert-demo/*` + the `審閱`
  tab retire in **P4**.
- **Provenance marker** `source_chunk_id:"manual"` is a deliberate design choice (hand-made
  knowledge's source is the author). Reviewer should confirm this is acceptable vs. a nullable
  schema field; the schema/contract was intentionally left unchanged (changing it would ripple into
  the extract path — a stop condition).

## Unsupported Claims

- No claim is made that the frontend renders correctly *visually* — only that it parses
  (`node --check`), serves, and posts to a verified endpoint. Visual correctness awaits the human
  browser pass (the owner did confirm the Ingestion/hand-made layout after the padding + cache-bust
  fixes, but a full checklist pass across all six items is still owed).
- No performance, load, or security-scan claims beyond the injection-guard behavior asserted by
  `test_invalid_type_rejected_422` and the type-whitelist validation.
