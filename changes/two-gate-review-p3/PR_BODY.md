## What & why

Phase 3 of the unified two-gate governance restructure — the **propose** side. A hand-authored
biological statement now stages as one `group_id` proposal group into the **same** group Review and
the **same** two gates (Schema gate → Expert gate) that LLM-extracted knowledge is meant to use, and
the **Ingestion** page merges the two sources behind one toggle. Builds on P1 (#10) and P2 (#11).

The point of the whole restructure: *source is irrelevant — form and meaning are what the gate
checks.* P3 makes the hand-made path a first-class producer for that one review flow.

## Changes

- **`POST /admin/curation/groups` + `service.create_group`** — stage a nodes+edges statement as one
  proposal group in a single transaction (atomic). Guards, all returning the documented
  `{"error":{code,message}}` contract:
  - type-whitelist (the injection guard — a bad type can never reach Cypher label interpolation),
  - empty group, over-cap (`MAX_GROUP_ELEMENTS=20`), intra-group duplicate id,
  - **dangling / empty edge endpoints** — every endpoint must resolve to an in-group proposed node
    or an already-approved node, else `422` at propose time (otherwise the gate passes and the edge
    is silently dropped at approval with a false audit row).
- **Provenance** — hand-made knowledge has no source chunk, so `source_chunk_id` is stamped
  `manual:{proposed_by}` (namespaced so it can't collide with a real chunk id) to satisfy the schema
  gate. The propose-time `reason` is persisted in `schema_check.propose_reason` (surviving a
  reviewer's later overwrite of `curation_items.reason`), surfaced by `list_groups`, and shown on
  the review card.
- **Frontend** — the Ingestion page hosts a `[LLM 抽取] ↔ [人工建構]` toggle: the extract sub-view is
  the prior flow, the hand-made sub-view is a statement builder posting the new endpoint. The `審訂`
  tab is removed (the `/admin/curation/*` single-item endpoints are kept for compatibility); the
  ingest tab is relabelled `收錄`. Also fixes an `E()` boolean-attribute bug that had been staging
  the wrong node/relation type, and a toggle race that could show a stale sub-view.
- **Docs** — `docs/api_contract.md` documents `POST /admin/curation/groups` and the new
  `propose_reason` field on `GET /admin/review/groups`.

## Review & verification

- **Two independent review rounds** (`changes/two-gate-review-p3/REVIEW_REPORT.md` +
  `REVIEW_REPORT_2.md`): every Blocking/High finding remediated (notably F1 wrong-type staging and
  F2 silent edge drop), plus new-round Low items R2/R4 fixed. F9/F10/R3 accepted as pre-existing /
  deferred, disclosed in `CHANGE_REPORT.md`.
- Full offline suite **167 passed** (`docker compose run --rm -e OPENAI_API_KEY= backend pytest
  tests ingestion/tests`); targeted P3 = 24 passed; ruff 0.15.21 check+format clean; `mypy
  backend/app ingestion scripts` clean. e2e through nginx: hand-made round-trip
  (create → list → approve), dangling → 422, `propose_reason` surfaced.

## Not covered / owed

- **Frontend visual pass** — the SPA has no test harness, so F1/F7 fixes are verified by e2e +
  `node --check` but a human browser pass of the builder (type dropdowns, toggle, gap banner) is
  owed.
- **LLM-extract path** still stages ungrouped per-item, so it has the backend gate + `proposed`
  invariant but no review UI yet — a disclosed limitation; the extract→unified-review work (statement
  segmentation, cross-chunk endpoint resolution, dedup, bulk triage) is the next change.
- Retiring the standalone `審閱` (expert-demo) screen + `/admin/expert-demo/*` is the following change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
