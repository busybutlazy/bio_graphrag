# Review Report: two-gate-review-p3

## Review Context

- **Diff base and scope:** working tree vs `main` @ `fe4da9e` (branch `feat/two-gate-review-p3` has
  **zero commits** — `git rev-parse HEAD` = `fe4da9e`; the whole change is uncommitted working-tree
  state, consistent with the plan's "Commit/push permission: No"). 8 modified files + 2 untracked
  (`backend/tests/api/test_curation_groups.py`, `changes/two-gate-review-p3/`), +347/−169.
- **Artifacts reviewed:** `IMPLEMENTATION_PLAN.md` (revision 2, Conditionally Approved 2026-08-01),
  `TASK_LOG.md`, `VERIFICATION_REPORT.md`, the full diff, `docs/api_contract.md`,
  `schema/extraction_output_schema.json`, `backend/app/graph/engineer_gate.py`,
  `ingestion/pipeline/{load_neo4j,load_postgres,schema}.{py,sql}`, `backend/app/api/auth.py`.
  **`CHANGE_REPORT.md` is absent** (see F5).
- **Independence disclosure:** this review ran in a **fresh session with no implementation context**
  — I did not author the plan, the code, or any of the reports. Findings below were derived from the
  artifacts and from independent execution, not from recollection of the build. Independence is
  adequate; a human browser pass is still separately owed and this review does not substitute for it.
- **Checks I ran** (read-only / non-mutating, existing container entrypoints only):
  | Command | Result |
  |---|---|
  | `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/api/test_curation_groups.py tests/integration/test_review_groups.py -q` | **20 passed** in 23.8s — reproduces the report's claim |
  | `docker compose run --rm ... backend python -c "engineer_gate.evaluate(<dangling-edge proposal>)"` | `GATE RESULT = pass` (evidence for F2) |
  | headless `chromium --dump-dom` on an isolated repro of `E()` + the builder's `<select>` | `state.type=Hormone \| select.value=Misconception` (evidence for F1) |
  | `git rev-parse HEAD`, `git status --porcelain`, `git diff fe4da9e --stat` | as above |
  I did **not** run `docker compose down -v` (destructive) and did **not** write to the dev
  Postgres/Neo4j outside what the existing test suite does and cleans up itself.

## Completion Claim Assessment

The claim under review is Verification Report "Overall: **Pass**", with all seven acceptance criteria
marked Pass and only the *visual* browser pass owed.

**The claim does not hold as stated.** The backend half of the change is genuinely solid: the
endpoint, the four guards, the injection guard reuse, transaction atomicity, and the admin gate are
all real, tested, and independently reproduced (20/20). But **AC5 is not met**, and the report's
"Pass (functional) / Owed (visual)" framing is what conceals it: the e2e evidence exercised a
hand-written curl payload, never a payload produced by the statement builder. The builder itself
emits the wrong `type` for every row a curator does not manually re-select (F1) — a defect in the
*data*, not in the pixels, so it falls outside the "only the visual layer is unverified" boundary the
report draws.

Two further problems are structural rather than cosmetic: retiring the `審訂` UI leaves the LLM
extract path with **no disposal surface at all** (F3), and the propose-time `reason` is accepted by
the API, documented in the contract, and then silently discarded (F4) — on a project whose stated
spine is an auditable curation trail.

Summary: **2 Blocking, 2 High, 3 Medium, 3 Low, 2 Suggestions.** Not ready for merge.

## Findings

### Blocking

#### F1 — The statement builder stages a different node/relation type than the curator sees

- **Evidence:** `frontend/app.js:1039` and `frontend/app.js:1056`:
  `E('option', { value: t, selected: t === n.type }, …)`. The `E()` helper
  (`frontend/app.js:6-14`) skips only `null`/`undefined` (`if (v == null) continue;`) and otherwise
  falls through to `el.setAttribute(k, v)` — so for every **non-matching** option it executes
  `setAttribute('selected', false)`, writing the literal string `"false"`. In HTML the *presence* of
  the `selected` content attribute sets default-selectedness regardless of its value; with a
  non-`multiple` select and many default-selected options, **the last one wins**.
  Independently confirmed in a real engine (headless Chromium, isolated repro of `E()` + the exact
  option-mapping code):
  `state.type=Hormone | select.value=Misconception | displayed=Misconception`.
  Pre-existing `E('option', …)` call sites (`app.js:380,381,383,1146,1147`) never pass a boolean
  prop — this is introduced by P3.
- **Violated requirement:** AC5 ("the hand-made statement builder submits a group and, on success,
  that group is visible in `群組審閱`") and the project's governance premise that a curator approves
  what they can see.
- **Impact:** `addNode()` seeds `type: NODE_TYPES[0]` (`Hormone`) while the dropdown renders
  `常見迷思` (`Misconception`); `addEdge()` seeds `SECRETES` while the dropdown renders `常被混淆為`
  (`COMMONLY_CONFUSED_WITH`). No `change` event fires, so `state` and display diverge silently. Even
  after a curator *does* pick a type, any repaint (add/remove another row) re-renders the row and
  restores the divergence while `state` keeps the earlier value. The staged proposal therefore
  carries types the domain expert never chose, and every downstream surface (Schema gate, expert
  lens back-translation, the approved graph) is faithful to the *wrong* input. This is a
  correctness defect in the proposal payload, not a rendering nit — so it is **not** covered by the
  "visual layer owed" caveat.
- **Remediation direction:** don't pass booleans through `E()`'s attribute path. Either set the
  select's value after construction (`sel.value = n.type`) or make `E()` treat `false` on
  non-`on*` props as "omit the attribute" (and audit for other call sites once that semantic
  changes). Add a regression check — a headless-DOM assertion that `select.value === state.type`
  after paint — since the manual checklist demonstrably did not catch this.

#### F2 — A dangling edge endpoint passes the Schema gate, is reported as written, and is silently dropped

- **Evidence:** `backend/app/graph/engineer_gate.py:68-140` — `evaluate()` runs schema, node-type,
  edge-type, id-convention, pattern, back-translation, testability and duplication checks; **none of
  them verifies that an edge's `source`/`target` resolves** to a node in the proposal or in the
  approved graph. `_pattern_check` (`engineer_gate.py:29-61`) only inspects `RegulatoryEffect` /
  `Interaction` nodes *present in the proposal*. Reproduced in-container:
  a two-node `SECRETES` statement with a typo'd `target` → `GATE RESULT = pass`, all eight checks
  `True`. `approve_group` (`service.py:433-438`) only refuses when `gate["result"] != "pass"`, then
  calls `load_neo4j.write_edges` — whose Cypher is
  `MATCH (a {id:$source}), (b {id:$target}) MERGE …` (`ingestion/pipeline/load_neo4j.py:43-49`): an
  unmatched endpoint yields zero rows, so the MERGE never runs and **no error is raised**.
  `approve_group` then returns `"edges": len(edge_payloads)` (`service.py:493`) and writes
  `after_state={"edges": edge_payloads}` into `graph_change_logs` (`service.py:484-488`).
- **Violated requirement:** the append-only audit log must reconstruct exactly what entered the
  graph (`service.py:481-483`, verbatim: "the log must be able to reconstruct exactly what entered
  the graph"). It cannot, here.
- **Impact:** a curator typos one endpoint id → `200 {status: approved, edges: 1}`, the UI reports
  success, the audit log records an edge that does not exist in Neo4j, and the knowledge is silently
  lost. The underlying Cypher predates P3, but P2 only ever fed `approve_group` from the trusted
  seeder; **P3 is the change that opens this path to free-text curator input**, and the statement
  builder collects `source`/`target` as raw text with no picker, no existence check, and no
  server-side validation (`_validate_curation_payload`, `service.py:29-44`, checks only `id` and
  `type`). The plan's Risks section discloses dangling endpoints as a *lens cosmetic* issue ("will
  show a humanized id in the lens (no crash). Left as-is (YAGNI)") — it does not disclose the
  silent-drop / false-audit consequence, so the accepted risk as written does not cover this.
- **Remediation direction:** either (a) add an endpoint-resolution check to `create_group` /
  `engineer_gate` — every edge endpoint must be proposed in the same group or already approved —
  or (b) make `write_edges` fail loudly when the MATCH finds nothing so the transaction aborts.
  (a) is the smaller, more useful change: it turns a silent data-loss bug into a 422 at propose
  time. If the owner decides this is genuinely out of P3 scope, it must at minimum be recorded as a
  known defect rather than left inside a "YAGNI, cosmetic" note.

### High

#### F3 — Retiring the `審訂` tab removes the only disposal surface for LLM-extracted items

- **Evidence:** `frontend/app.js:137-145` — the `curation` VIEWS entry is removed and
  `renderCuration` + `resolveNodeLabels` are deleted (−161 lines). `grep -n "api.get('/\|api.post('/"
  frontend/app.js` shows the surviving calls: nothing reads `/admin/curation/items`. `renderReview`
  reads `/admin/review/groups`, and `list_groups` (`service.py:346-353`) filters
  `group_id IS NOT NULL`. The extract path stages **ungrouped** items
  (`ingestion/pipeline/load_postgres.py:128,143` — no `group_id`), which is explicitly kept
  unchanged as P5 scope.
- **Violated requirement:** the change's own objective, "closes the propose→dispose loop", and the
  governance invariant that proposed knowledge is reviewable by a human.
- **Impact:** after P3, `POST /admin/ingest/run` stages LLM proposals that **no UI in the
  application can list, approve, or reject** — they are only reachable by direct API call or SQL.
  The disclosure note added to the extract sub-view (`app.js:1133-1136`) even directs the user to
  "審訂佇列" — a queue whose UI this same change deleted, so the note is now misleading. The plan
  anticipated the *grouping* wart ("LLM-extracted items won't appear in group Review yet … the
  disconnect is disclosed") but not that the alternative surface would vanish simultaneously;
  AC6 was written as "endpoints still respond", which is true and which is why the gap passed
  verification.
- **Remediation direction:** smallest honest options, owner's call — (a) keep the `審訂` tab
  read-only-plus-dispose until P5 lands grouped extraction; (b) have `list_groups` synthesize a
  pseudo-group per ungrouped item so extract output stays reviewable; or (c) accept the gap but fix
  the note to say the extract queue has no UI until P5, and record it as a known limitation in the
  change report. What is not acceptable is the current state, where the note points at a deleted
  screen.

#### F4 — The propose-time `reason` is accepted, documented, and silently discarded

- **Evidence:** `routes_curation.py:46-53` passes `body.reason` into `service.create_group`;
  `service.py:152` declares `reason: str | None = None` — and the parameter is **never referenced in
  the function body**. The INSERT (`service.py:203-216`) lists
  `(item_id, item_type, action, payload, status, proposed_by, schema_check, group_id)` — no `reason`
  column, though `curation_items.reason TEXT` exists (`ingestion/pipeline/schema.sql:44`) and the
  sibling `create_item` does persist it (`service.py:137-145`). `docs/api_contract.md` publishes
  `reason: str | None = None` in the `CurationGroupCreate` block with no note that it is ignored.
  The frontend hardcodes `reason: '人工建構陳述'` (`app.js:1090`).
- **Violated requirement:** the documented API contract (a field that is advertised must do
  something), and the governance thesis that every curation action is auditable with its rationale.
  Also a plan deviation: Task 2 specifies the builder shall have "a `possible_schema_gap` checkbox,
  **a reason field**, and a submit" — the delivered builder has no reason field, and `TASK_LOG.md`
  lists the delivered controls without noting the omission.
- **Impact:** the proposer's rationale — the one field that explains *why* a human proposed this
  statement — is unrecoverable. It is not in `curation_items` (no write), not in
  `graph_change_logs` (`create_group` deliberately logs nothing at propose time), and not surfaced by
  `list_groups`, so the reviewer at the expert gate cannot see it. Note that even if it were
  persisted, `approve_group`/`reject_group` overwrite `curation_items.reason` with the *reviewer's*
  reason (`service.py:467-473`, `514-520`), so the column alone cannot hold both.
- **Remediation direction:** decide the intent explicitly. Either (a) persist it — most naturally in
  the members' `payload`/`schema_check` JSON or a propose-time `graph_change_logs` row, so it
  survives the reviewer's overwrite — and add the reason field back to the builder and surface it on
  the review card; or (b) drop `reason` from `CurationGroupCreate`, the contract doc, and the
  frontend body. Silently accepting a field that does nothing is the one option that should not ship.

### Medium

#### F5 — `CHANGE_REPORT.md` is missing

- **Evidence:** `changes/two-gate-review-p3/` contains only `IMPLEMENTATION_PLAN.md`, `TASK_LOG.md`,
  `VERIFICATION_REPORT.md`. Both prior comparable changes ship one
  (`changes/two-gate-review-p2/CHANGE_REPORT.md`, `changes/unified-two-gate-review/CHANGE_REPORT.md`).
- **Violated requirement:** the working agreement's step 6 ("產生變更報告，揭露完成、未完成與偏差")
  and this review's required inputs; Definition of Done requires "變更報告已產生，無未揭露偏差".
- **Impact:** deviations are scattered across the task log and had to be reconstructed here. Two of
  them (the missing reason field, F4; the out-of-scope file edits, F6) are **undisclosed** — exactly
  what the change report exists to surface. Note the task log is otherwise unusually honest: the
  provenance-stamp deviation, the owed browser pass, the CDN-cache issue and the deferred RWD are all
  disclosed clearly.
- **Remediation direction:** author `CHANGE_REPORT.md` before human disposition, and list every
  deviation from plan revision 2 explicitly, including the ones named in F6.

#### F6 — Three files were changed outside the plan's approved path scope, without disclosure

- **Evidence:** the plan's "Approved file/path scope" (IMPLEMENTATION_PLAN.md:109-112) lists
  `service.py`, `schemas/curation.py`, `routes_curation.py`, `frontend/app.js`, `docs/api_contract.md`,
  `backend/tests/integration/test_review_groups.py` (+ `test_curation.py` if needed), and
  `changes/two-gate-review-p3/*`. The diff also touches **`frontend/index.html`**,
  **`frontend/styles.css`**, and adds **`backend/tests/api/test_curation_groups.py`** (Task 1's test
  section names `test_review_groups.py` as the destination).
- **Violated requirement:** the plan's Mandatory stop conditions ("deviate from approved Plan") and
  the guideline's rule that deviations are reported, not absorbed.
- **Impact:** low technical risk — all three edits are defensible (CSS for the new builder, a
  cache-bust bump the owner explicitly confirmed, a new test file that is arguably cleaner). The
  issue is process: none is flagged as a scope deviation anywhere, and the missing change report
  (F5) is where they would have been caught. The `styles.css` edit also ships an app-wide
  `@media (max-width: 560px)` block that repaints `.page-head`, `.ing-wrap` and `.lib-groups` —
  pages outside P3's scope — which is a wider blast radius than the plan's frontend scope implies.
- **Remediation direction:** disclose all three in the change report and get the owner's
  retroactive nod; consider whether the app-wide responsive rules belong in the deferred RWD phase
  the task log already carves out rather than here.

#### F7 — The toggle can render a stale sub-view (the one thing the owed checklist item #1 targets)

- **Evidence:** `frontend/app.js:1011-1016`:
  ```js
  async function paint() { clear(sub); if (mode === 'extract') await paintExtract(sub); else await paintHandmade(sub); }
  function switchMode(m) { if (m === mode) return; mode = m; paintToggle(); paint(); }
  ```
  `switchMode` does not await `paint()`, and there is no generation token. `paintExtract`
  (`app.js:1124-1125`) does `clear(host)` and then `await api.get('/admin/ingest/options')`.
- **Violated requirement:** manual checklist item 1 ("switching repaints the correct sub-view
  **without stale DOM**") — which is still owed, so this is unverified in both directions.
- **Impact:** extract → handmade → extract (or any toggling faster than the `/admin/ingest/options`
  round trip) lets an in-flight `paintExtract` resolve *after* a newer paint, at which point its
  `clear(host)` wipes the current sub-view and appends the extract form while the toggle shows
  `人工建構`. On a fast local stack this is hard to hit; on the public domain it is not. Severity is
  Medium rather than High because it self-heals on the next toggle and loses only unsaved builder
  rows — but it does silently discard a curator's in-progress statement.
- **Remediation direction:** a generation counter (`const gen = ++paintGen;` … `if (gen !== paintGen)
  return;` before appending), or disable the toggle while a paint is in flight. Verdict: **PLAUSIBLE**
  — traced in code, not reproduced in a browser.

### Low

#### F8 — The `source_chunk_id: "manual"` stamp is an unvalidated provenance sentinel

- **Evidence:** `service.py:190-193` stamps `source_chunk_id: "manual"` on any element lacking one,
  to satisfy `extraction_output_schema`'s `required` list
  (`schema/extraction_output_schema.json:40,60`). `write_nodes`/`write_edges` propagate only
  `properties`, so the marker does **not** reach Neo4j today; `grep -rn source_chunk_id backend/app
  ingestion/pipeline frontend` shows no runtime consumer other than the schema check.
- **Impact:** harmless now, but `"manual"` is not a real `chunks.chunk_id`, so any future
  "show me the source passage" feature will silently fail on hand-made knowledge, and the value is
  indistinguishable from a chunk literally named `manual`. The stamp also applies to *every* caller
  of `create_group`, including P5's grouped-extract path if it reuses the function. The task log and
  verification report both flag this for reviewer attention — good disclosure; my assessment is that
  the sentinel is acceptable as an interim, but should be namespaced.
- **Remediation direction:** use a namespaced sentinel (`manual:human`, matching the project's
  `prefix:id` convention) and note it in `schema/extraction_output_schema.json`'s description, or
  make `source_chunk_id` nullable in a later change once the extract-path ripple is affordable.

#### F9 — No bounds on element field sizes

- **Evidence:** `CurationGroupCreate` (`schemas/curation.py:26-36`) types the payload as
  `list[dict]`. `MAX_GROUP_ELEMENTS = 20` caps the element *count* only; `label`, `description`,
  `id`, and `reason` are unbounded, as is total body size.
- **Impact:** a 20-element group each carrying a multi-megabyte `description` is accepted and stored
  in `curation_items.payload`. This is consistent with the pre-existing `CurationItemCreate`
  (`payload: dict`, equally unbounded), so it is **not a regression** — but the project's stated
  posture is that request limits live in the Pydantic schemas, and the new endpoint is admin-gated,
  which caps the blast radius further.
- **Remediation direction:** if tightened, do it project-wide (both create paths) rather than
  singling out the new endpoint; low priority for a portfolio demo.

#### F10 — The authenticated proposer's identity is discarded

- **Evidence:** `require_admin` (`auth.py:35-45`) returns the resolved vendor name specifically "so
  handlers/logs can attribute the action" (docstring, `auth.py:5-6`). `routes_curation.py:16` applies
  it as a router-level `dependencies=[…]`, discarding the return, and `create_group` hardcodes
  `proposed_by: str = "human"` (`service.py:154`).
- **Impact:** with multiple `ADMIN_API_KEYS` vendors configured, every hand-made group is attributed
  to the string `"human"` rather than the key holder. This mirrors the legacy `create_item`
  (`service.py:138`, also hardcoded) and **no** `/admin` route in the codebase consumes the vendor
  name today, so it is a pre-existing project-wide pattern, not a P3 regression.
- **Remediation direction:** out of scope here; worth a dedicated change that threads the vendor
  through the propose/approve paths, since it is squarely on the governance spine.

### Suggestion

#### S1 — `.seg button { cursor: pointer; }` is a duplicate selector

`frontend/styles.css:245` re-opens `.seg button` immediately after the block at line 243 solely to
add `cursor`. Fold it into the existing rule.

#### S2 — The duplicate-id guard is quadratic

`service.py:196-198` uses `ids.count(i)` inside a comprehension over `ids`. Bounded at 20 elements so
it is irrelevant in practice; a `collections.Counter` would read better and removes the footgun if
`MAX_GROUP_ELEMENTS` is ever raised.

## Requirement and Test Coverage Gaps

| AC | Verification claim | My assessment |
|---|---|---|
| AC1 stage → listed with live gate | Pass | **Confirmed** — reproduced (20/20 incl. `test_create_group_appears_in_review_and_approves`) |
| AC2 approve round-trips; B1 409 | Pass | **Confirmed** for the happy path. Note the B1 evidence (`test_approve_refuses_when_a_member_already_exists_approved`) uses a *seeder-authored* group, not one from the new endpoint — acceptable, since `approve_group` is unchanged and provenance-agnostic. Undercut by **F2** for the dangling-endpoint case, which no test covers. |
| AC3 four 422 guards + error contract | Pass | **Confirmed** — all four tests present and passing; the contract shape is asserted |
| AC4 `possible_schema_gap` → `needs_schema_extension` | Pass | **Confirmed** |
| AC5 Ingestion toggle + builder submits a visible group | "Pass (functional) / Owed (visual)" | **Not met.** The e2e exercised a hand-written payload, never the builder's output; the builder emits wrong types (**F1**). The type sent is data, not visuals, so the "visual owed" caveat does not cover it. **F7** additionally puts checklist item 1 in doubt. |
| AC6 `審訂` gone; `/admin/curation/*` respond | Pass | Literally true, but it verifies the endpoint and not the loop — see **F3** |
| AC7 full suite + lint/type green | Pass | **Partially reproduced.** I confirmed the 20 targeted tests. I did **not** re-run the full 163-test clean-slate suite (requires `docker compose down -v`, destructive) or ruff/mypy. No reason to doubt them. |

**Coverage gaps, ranked:**
1. **No test asserts what the builder actually sends.** Every backend test constructs its own JSON.
   A headless-DOM or contract test over `paintHandmade`'s body assembly would have caught F1.
2. **No test for edge endpoints that resolve to nothing** — neither at the gate nor through
   `approve_group` (F2).
3. **No test that `reason` survives anywhere** — F4 is invisible to the suite because nothing asserts
   the field's effect.
4. `test_endpoint_is_admin_gated` asserts 401 for missing and wrong keys; the plan said "401/403".
   `require_admin` only ever raises 401, so the test is right and the plan was loose. Not a gap.

## Compatibility, Security, and Scope Assessment

**Security — the part that matters here is sound.** The injection guard is correctly reused: every
element passes `_validate_curation_payload` (`service.py:186-189`) before staging, so a `type`
outside `VALID_NODE_TYPES` / `VALID_RELATIONSHIP_TYPES` can never reach the f-string label
interpolation in `load_neo4j.write_nodes` (`load_neo4j.py:29`). Defense in depth holds on the
approve side too: `extraction_output_schema` sets `additionalProperties: false`, so a client cannot
smuggle extra properties into the graph — such a group stages but can never pass the gate
(`approve_group` refuses any `result != 'pass'`). A client-supplied `"status": "approved"` is
overwritten at both insert (`service.py:212`) and approve (`service.py:444`). The `422`-before-
validation ordering means an oversized element list is rejected before any per-element work. Admin
auth is applied at router level and asserted by test. I found no injection, authz, or state-machine
hole introduced by this change.

**Transaction safety** is correct: a single `async with conn.transaction()` wraps all inserts, and
`test_create_group_is_atomic_on_failure` proves rollback with a genuine fault injection (a
pre-planted PK collision on the second element) rather than a mock — condition 2 is properly met.
`group_id` is uuid-based so cross-group `item_id` collisions are structurally impossible.

**Compatibility:** the contract change is genuinely additive — no existing endpoint's request,
response, or error shape moves; `/admin/curation/*` single-item routes keep their legacy `{"detail"}`
shape and `test_curation.py` stays green. No DB migration (the `group_id` column landed in P1). No
new dependency. The deliberate asymmetry (new route emits `{"error":{code,message}}`, neighbours emit
`{"detail"}`) is documented in both the code comment (`routes_curation.py:18-20`) and the contract
doc — acceptable, though it means one router now speaks two error dialects.

**Scope:** three files outside the approved path list (F6); one backend behaviour change
(the provenance stamp) introduced during a frontend task, after the T1 human checkpoint had already
passed — disclosed in the task log, but it means the backend the human checkpointed is not the
backend being reviewed. The `@media (max-width: 560px)` rules reach beyond P3's surfaces into
`.page-head` and `.lib-groups`. No dead code left behind: `renderCuration` and `resolveNodeLabels`
were removed together and `grep` confirms no dangling references.

**Rollback** is as claimed: revert the eight files, no migration, no backfill; groups staged during
testing are `proposed` only and therefore invisible to student-facing retrieval.

## Unreviewed Areas and Residual Risk

- **The full 163-test clean-slate suite, ruff, and mypy** — not re-run (the clean-slate run needs
  `docker compose down -v`, which is destructive to the user's volumes). I reproduced only the 20
  targeted tests. The reported figures are plausible and self-consistent; treat them as
  reported-not-independently-confirmed.
- **The visual browser pass** remains owed and this review does not substitute for it. F1 and F7 are
  precisely what checklist items 1 and 3 exist to catch, which is evidence that the checklist needs
  to be executed, not that it is redundant.
- **`renderReview` / the P2 dispose surface** was read for context but not re-reviewed; it was
  signed off in P2 and is unchanged here.
- **The extract sub-view** (`paintExtract`) is asserted to be "the previous flow verbatim minus its
  page-head". I diff-checked the moved block and it matches, but I did not exercise
  preview/run behaviour (run is owner-token-locked).
- **Offline/online parity:** the new endpoint touches no LLM path, so the offline-first invariant is
  unaffected. The `.env` key-exhaustion noted in the reports is an environment matter, not a code
  defect, and the offline posture used for verification is the project's documented one.
- **Concurrency:** two curators proposing the same node id in different groups is unguarded at
  propose time; the B1 guard catches it at the second approval. Correct, but the second curator only
  learns at approval time. Not filed as a finding — it matches the P2 design.

## Human Disposition Required

The reviewer does not approve, fix, merge, or release this change.

Recommended disposition, for the owner's decision:

1. **F1 must be fixed before merge** — it is a two-line fix and it currently makes the headline
   feature of P3 stage incorrect data.
2. **F2 needs a decision, not necessarily a fix** — either add the endpoint-resolution check, or
   accept it explicitly with the silent-drop/false-audit consequence written down. The current
   disclosure ("cosmetic, YAGNI") does not describe the actual risk.
3. **F3 needs a product call** — keep `審訂` until P5, synthesize pseudo-groups, or accept the gap
   and fix the misleading note.
4. **F4 needs an intent call** — persist the reason (and restore the builder field) or remove the
   field from the contract.
5. **F5/F6 are process** — author the change report and disclose the three out-of-scope files there.
6. F7–F10 and S1–S2 are the owner's discretion; F7 is worth the ~3-line generation-token fix while
   the file is open.
7. The owed **manual browser checklist** should be run *after* F1 and F7 are addressed, otherwise it
   will be run against a build known to be wrong.

---

# Round 2 — Independent re-review of the remediation (2026-08-03)

Same reviewer, same independence caveat as above: I did not implement any of these fixes, and every
verdict below comes from re-execution rather than from reading the claim. Re-review base: working
tree vs `main` @ `fe4da9e` (still **zero commits** on `feat/two-gate-review-p3`), now **8 files,
+409/−171**; `CHANGE_REPORT.md` now present.

## Checks I re-ran independently

| Command | Result |
|---|---|
| `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q` | **166 passed, 0 failed** (59.7s) — on a **non-pristine** volume, so even the known idempotent-pipeline flake passed |
| `… pytest tests/api/test_curation_groups.py tests/integration/test_review_groups.py tests/integration/test_curation.py -q` | **28 passed** (33.7s) |
| `docker run ghcr.io/astral-sh/ruff:0.15.21 check …` / `format --check …` | exit 0 — "All checks passed", "103 files already formatted" |
| `node --check frontend/app.js` | OK |
| headless Chromium loading the **real** `frontend/app.js`, exercising `typeSelect` + `E()` boolean handling | `state=Hormone \| select.value=Hormone \| displayed=激素 \| falseAttr=false \| trueAttr=true \| trueChecked=true` |
| JSON scan of the seeded demo review groups for external edge endpoints | 3 external refs found (evidence for R3 below) |

Not re-verified: **mypy** — it is not installed in the backend image (`mypy: not found`), and the
project's `make lint` runs it on the host; I installed nothing. Take the reported "79 files,
success" as reported-not-confirmed. `make eval` remains out of scope.

## Disposition of each original finding

| # | Sev | Claimed | **My independent verdict** |
|---|---|---|---|
| F1 | Blocking | Fixed | **Confirmed fixed.** `E()` now short-circuits `v === false` and maps `true → ''` (`app.js:8-16`), and `typeSelect` sets `sel.value = current` *after* construction rather than relying on attribute presence. I re-ran my original repro against the real `app.js` in headless Chromium: state and displayed value now agree (`Hormone` / 激素). I also checked for collateral damage from touching the shared `E()` helper — the only pre-existing boolean-ish props in the file are `checked: on ? '' : null` (`app.js:722,731`), and `''`/`null` take the unchanged paths; the runtime check confirms `true → attribute present & .checked === true`, `false → attribute absent`. No regression. |
| F2 | Blocking | Fixed | **Confirmed fixed for the path P3 opened**, with a residual (R3). `create_group` now resolves every edge endpoint against the group's own proposed nodes or the approved graph and returns 422 otherwise (`service.py:186-200`); two new tests cover reject-dangling and accept-reference-to-approved. |
| F3 | High | Note fixed; gap accepted | **Accurate, and the honest option.** The extract note no longer points at the deleted `審訂佇列`; it now states plainly that extract output is single-item, absent from 群組審閱, and API-only until the extract-grouping phase. The reviewability gap itself is accepted and recorded. This is the product call I asked for — but it is the **owner's** call to sign, not the implementer's (see Disposition below). |
| F4 | High | Fixed | **Confirmed fixed, and well designed.** `reason → schema_check.propose_reason` (`service.py:212-217`) deliberately avoids `curation_items.reason`, which approve/reject overwrite with the *reviewer's* reason — that was the subtle part and it was handled correctly. Surfaced by `list_groups` as `propose_reason` (`service.py:414-427`), rendered on the review card (`app.js:883`), the builder gained a real reason input, contract doc updated, `test_reason_is_persisted_and_surfaced` asserts the round trip. |
| F5 | Medium | Fixed | **Confirmed** — `CHANGE_REPORT.md` exists and discloses all four deviations, including the two that were previously undisclosed. |
| F6 | Medium | Disclosed + narrowed | **Confirmed.** All three out-of-scope files are named in the change report, and the app-wide `@media (max-width: 560px)` block that repainted `.page-head`/`.ing-wrap`/`.lib-groups` is gone; the surviving responsive rules touch `.sb-row`/`.sb-x` only. Blast radius is now genuinely inside P3. |
| F7 | Medium | Fixed | **Confirmed fixed.** `paint()` takes a generation token, renders into a **detached** holder, and commits only if still current (`app.js:1010-1019`). I checked the detached-build assumption: `paintExtract` uses no layout-dependent API (`getBoundingClientRect`/`offset*`/`scrollIntoView`/`getComputedStyle`/`document.*`), so building off-document is safe. |
| F8 | Low | Fixed | **Confirmed** — `manual:{proposed_by}` → `manual:human`, matching the `prefix:id` convention, and documented in the contract. |
| F9 | Low | Accepted | **Agreed.** Matches my own assessment that this is a pre-existing project-wide pattern, not a P3 regression. |
| F10 | Low | Accepted | **Agreed**, same reasoning; worth a dedicated governance change later. |
| S1 / S2 | Suggestion | Fixed | **Confirmed** (`cursor` folded into the base `.seg button` rule; `Counter` replaces the quadratic scan). |

**No finding was waved through, and no fix was cosmetic.** Both Blocking items are genuinely
resolved.

## New findings from this round

All minor; none blocks merge.

### R1 (Low) — `VERIFICATION_REPORT.md` body was not regenerated, only banner-noted

A superseding note was added at the top, but the body still states the pre-remediation reality in
roughly eight places: "163 passed" and "20 passed" (now 166 / 23), "(7 tests)" (now 10),
`source_chunk_id:"manual"` (now `manual:human`), `?v=20260803-1` (now `-2`), diff scope
"+347/−169" (now +409/−171), and the AC5 row still reads "Pass (functional) / Owed (visual)" —
the exact framing that hid F1. The banner is honest and points at `CHANGE_REPORT.md`, so this is
not a misleading-report finding; it is a stale-artifact one, and the Definition of Done asks for
documents to be in sync. **Remediation:** regenerate the traceability and command tables, or strike
the superseded rows explicitly rather than leaving them to be read as current.

### R2 (Low) — the F2 guard reuses a *label* lookup as an *existence* check

`create_group` resolves endpoints via `_approved_labels` (`service.py:196`), whose Cypher filters
`if r["label"]` (`service.py:330-343`) — it returns only approved nodes with a **truthy** label.
`_validate_curation_payload` never requires a non-empty `label`, and `extraction_output_schema`
accepts `""`, so an approved node with an empty label is reachable. Such a node would be reported
as an unresolved endpoint and the proposal rejected `422` — a false negative on a guard whose whole
job is to say "this node exists". **Remediation:** use a dedicated existence query (`RETURN n.id`
with no label filter), or drop the truthiness filter when the helper is used for existence.
Verdict: **PLAUSIBLE** — the code path is certain, the empty-label precondition is unlikely in
practice.

### R3 (Low, residual on F2) — the fix guards the input, not the sink

`approve_group` is unchanged: it still returns `"edges": len(edge_payloads)` and writes
`after_state={"edges": edge_payloads}` into `graph_change_logs` without checking that
`load_neo4j.write_edges`' `MATCH` actually matched. Any group **not** created through
`create_group` therefore retains the original silent-drop/false-audit behaviour — concretely, the
seeder path (`stage_demo_review_group`), and whatever grouped-extract staging the later phase adds.
This is not hypothetical: scanning `data/sample/expert_demo/review_groups.json` shows seeded groups
**do** carry edges pointing at external ids (`physiological_variable:blood_glucose`,
`structure:pancreas`) — they resolve against the seed graph today, so live risk is nil, but the
class of bug is untouched. For P3's scope the chosen fix is correct and adequate; I record this so
the extract-grouping phase does not inherit the hole silently. **Remediation direction (later
phase):** move or duplicate the endpoint check into `approve_group`, or make `write_edges` raise
when its `MATCH` yields no rows so the transaction aborts.

### R4 (Suggestion) — no loading state during a sub-view switch

`paint()` now defers `clear(sub)` until after the await, so toggling to `LLM 抽取` leaves the
previous sub-view on screen for the duration of the `/admin/ingest/options` round trip. Correct
(that is what fixes F7) but slightly less responsive than before; a one-line skeleton, or disabling
the toggle while a paint is in flight, would close it.

## Residual risk after round 2

- **The manual browser checklist is still owed** and is now worth running: F1 and F7 — the two items
  checklist steps 1 and 3 exist to catch — are fixed, so the pass will no longer be against a build
  known to be wrong. The one thing automation still cannot assert is that each builder row's
  `<select>` visibly shows the type held in `state` after add/remove cycles; my headless check
  covers the mechanism, not the assembled page.
- **No frontend regression test exists**, as the change report states. F1 was a real Blocking defect
  that the entire automated suite could not see. That is an infra gap rather than a P3 gap, but it is
  now twice-demonstrated and worth a small headless-DOM harness in a future change.
- **mypy** not independently re-verified (see above).
- Unreviewed areas from round 1 remain unreviewed: the P2 dispose surface, `paintExtract`'s
  preview/run behaviour (owner-token locked), and `make eval`.

## Human Disposition Required (round 2)

The reviewer still does not approve, fix, merge, or release this change.

My recommendation: **both Blocking findings are genuinely closed and I have no blocking finding in
this round.** Before merge the owner should:

1. **Explicitly sign the F3 acceptance.** It is the one disposition that is a product decision
   rather than an engineering one — after P3, `POST /admin/ingest/run` spends tokens to produce
   knowledge that no in-app surface can review or reject until the extract-grouping phase. The note
   is now honest about it; what is missing is the owner saying "yes, ship it that way".
2. **Run the owed browser checklist** (all six items), now that it is worth running.
3. **Refresh `VERIFICATION_REPORT.md`** (R1) so the artifact set is internally consistent.
4. R2/R3/R4 are discretionary; R3 in particular should be carried forward as a known constraint into
   the extract-grouping phase rather than closed here.
