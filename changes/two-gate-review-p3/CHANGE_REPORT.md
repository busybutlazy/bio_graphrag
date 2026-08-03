# Change Report: two-gate-review-p3

Branch `feat/two-gate-review-p3` (uncommitted working tree vs `main` @ `fe4da9e`). Covers P3
(propose side: Ingestion page + hand-made grouped-propose) **and** the remediation of the independent
`REVIEW_REPORT.md` (2 Blocking, 2 High, 3 Medium, 3 Low, 2 Suggestions).

## Completed — P3 core (Tasks 1–3)

- **Backend** `POST /admin/curation/groups` + `service.create_group`: stages a hand-made statement
  (nodes+edges) as one `group_id` proposal group flowing into the P2 group Review. Guards: type
  whitelist (injection), empty, over-cap (`MAX_GROUP_ELEMENTS=20`), intra-group duplicate id, and
  (post-review) dangling edge endpoint. Single transaction (atomic). `{"error":{code,message}}`
  contract. `CurationGroupCreate` schema.
- **Frontend** Ingestion page: `[LLM 抽取] ↔ [人工建構]` toggle; `paintExtract` (prior flow) +
  `paintHandmade` (statement builder posting the new endpoint).
- **Nav** `審訂` tab removed (`renderCuration`+`resolveNodeLabels` deleted); `ingest` relabelled
  `收錄`. `/admin/curation/*` single-item endpoints kept. `docs/api_contract.md` updated.

## Review remediation — disposition of every finding

| # | Sev | Disposition |
|---|---|---|
| **F1** builder stages wrong node/relation type (`E()` boolean-attr bug) | Blocking | **Fixed.** `E()` now omits `false` attrs / sets `""` for `true`; the type `<select>` is built then `sel.value = current` (robust, no reliance on attribute presence). New `typeSelect` helper. |
| **F2** dangling edge endpoint passes gate, silently dropped, false audit | Blocking | **Fixed.** `create_group` rejects `422` if any edge endpoint resolves to neither a proposed node in the group nor an approved node (Neo4j check). Tests + e2e (`422`). |
| **F3** retiring `審訂` leaves LLM-extract items with no dispose UI; note points at deleted queue | High | **Fixed (note) + disclosed (gap).** The extract disclosure note no longer references the deleted `審訂佇列`; it now states extract output is single-item, not yet grouped, not in group Review, and API-only until the extract-grouping phase. The *reviewability gap itself* is an accepted, disclosed limitation (extract grouping = a later phase); the misleading pointer is fixed. |
| **F4** propose-time `reason` accepted, documented, silently discarded | High | **Fixed.** `reason` persisted in members' `schema_check.propose_reason` (survives reviewer overwrite), surfaced by `list_groups` as `propose_reason`, shown on the review card, and the builder gained a reason field. Contract doc updated. Test added. |
| **F5** `CHANGE_REPORT.md` missing | Medium | **Fixed** — this document. |
| **F6** 3 files outside approved path scope, undisclosed | Medium | **Disclosed** (below) + narrowed blast radius: the app-wide `@media` that repainted `.page-head`/`.lib-groups` is removed; responsive rules are now scoped to the builder (`.sb-row`) only. |
| **F7** toggle can render a stale sub-view (race) | Medium | **Fixed.** `paint()` uses a generation token and renders into a detached holder, committing only if still current. |
| **F8** `source_chunk_id:"manual"` unnamespaced sentinel | Low | **Fixed.** Now `manual:{proposed_by}` (e.g. `manual:human`), matching the `prefix:id` convention so it cannot collide with a real chunk id. Documented in the contract. |
| **F9** no bounds on element field sizes | Low | **Not changed** (accepted). Pre-existing project-wide pattern (`CurationItemCreate` is equally unbounded); admin-gated; tightening belongs in a project-wide change, not this endpoint alone. |
| **F10** authenticated proposer identity discarded (`proposed_by='human'`) | Low | **Not changed** (accepted). Pre-existing pattern; no `/admin` route consumes the vendor name today. Worth a dedicated governance change to thread the vendor through propose/approve. |
| **S1** duplicate `.seg button` selector | Suggestion | **Fixed** (folded `cursor` into the base rule). |
| **S2** quadratic duplicate-id check | Suggestion | **Fixed** (`collections.Counter`). |

## Deviations from approved plan (revision 2)

- **Files outside the plan's approved path scope (F6):** `frontend/index.html` (cache-bust version
  bumps — the owner confirmed the layout fix required it; see [[public-domain-cdn-cache]]),
  `frontend/styles.css` (builder CSS), and a **new** test file `backend/tests/api/test_curation_groups.py`
  (Task 1 named `test_review_groups.py` as the destination; a dedicated HTTP-layer file is cleaner).
  All three are disclosed here and were exercised by the verification run.
- **Backend behaviour added during a frontend task:** the `source_chunk_id` provenance stamp was
  introduced in Task 2 (after the T1 human checkpoint) because e2e revealed the schema gate requires
  it — without it hand-made groups could never be approved, defeating the approved A2 scope. Disclosed
  in `TASK_LOG.md`; further changed in remediation (F8 namespacing).
- **Cap enforcement location:** enforced in `service.create_group` (not the Pydantic validator) so its
  422 shares the documented error contract; the schema stays structural. Satisfies condition 1.
- **UI polish beyond the plan:** edge-hugging padding fix (`.sb-wrap`, `.ing-toggle`) + CDN cache-bust,
  both from the owner's live browser review.

## Not completed / residual (recorded)

- **Frontend visual/interaction regression test for F1** — not added; the project has **no FE test
  harness** (vanilla-JS SPA, no jsdom/headless runner). The fix is idiomatic and defensive, but a
  human browser pass is still owed and should assert that each row's `<select>` shows the type held in
  `state`. Adding a JS test harness is a separate infra change.
- **RWD** — deferred to a future phase (owner's call); only the builder's own responsive collapse ships.
- **F9 / F10** — accepted as pre-existing, out of P3 scope (see table).
- **LLM-extract per-group staging + its review UI** — remains a later phase; the extract note now
  discloses the interim API-only state honestly.
- **`.env` `OPENAI_API_KEY` credit-exhausted** — environment matter, not code; verification ran in the
  documented offline posture.

## Files changed

`backend/app/curation/service.py`, `backend/app/api/routes_curation.py`,
`backend/app/schemas/curation.py`, `backend/tests/api/test_curation_groups.py` (new, 10 tests),
`backend/tests/integration/test_review_groups.py` (+ atomicity), `docs/api_contract.md`,
`frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, `changes/two-gate-review-p3/*`.

## Verification (post-remediation)

`docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests` → **166 passed**
(exit 0); targeted P3 = **23 passed**. ruff 0.15.21 check+format clean; `mypy backend/app ingestion
scripts` = success (79 files); `node --check frontend/app.js` clean. e2e via nginx: hand-made
round-trip (create→list→approve), **F2 dangling → 422**, **F4 `propose_reason` surfaced**, guards
`422`. Frontend assets re-bumped to `?v=20260803-2`. See `VERIFICATION_REPORT.md`.

## Re-review (Round 2, `REVIEW_REPORT_2.md`) — follow-up

Independent re-review (fresh reviewer) confirmed **no Blocking/High survives**; 10/10 findings +
both suggestions resolved or appropriately accepted. It raised 5 new Low/Suggestion items:

| # | Sev | Disposition |
|---|---|---|
| **R4** empty-string edge endpoint (`source:""`) slips the F2 `if ep` filter → same silent-drop/false-audit class | Low | **Fixed.** `create_group` now rejects any edge with an empty/missing `source`/`target` (422) before the resolution check. Test `test_edge_with_empty_endpoint_rejected_422` added. |
| **R2** F2 guard used `_approved_labels` (a label lookup) as an existence check → false-reject an edge into a real-but-unlabelled approved node | Low | **Fixed.** F2 guard now uses `_existing_approved_ids` (true existence), not label presence. |
| **R3** `approve_group` sink is unchanged, so non-`create_group` propose paths (seeder / future extract) keep the F2 class | Low | **Accepted / deferred.** `create_group` (the only UI-wired propose path) is fully guarded; the durable sink-level defense belongs with the extract→unified-review change (pinned scope in [[unified-two-gate-restructure]]). Recorded, not silently dropped. |
| **R1** `VERIFICATION_REPORT.md` body is pre-review/stale | Low | **Mitigated.** A superseding note at its top directs readers to this report + the post-remediation run; body left as the historical pre-review record. |
| **R5** no loading state during sub-view toggle switch | Suggestion | **Not changed** (Suggestion; the generation-token fix already prevents stale renders). |

Post-R2/R4 verification: targeted **24 passed**; full offline suite **167 passed** (exit 0); ruff
0.15.21 + mypy clean.

## Rollback

Revert the listed files; no migration, no dependency. Groups staged during testing are `proposed`
only (invisible to retrieval) and were cleaned up.
