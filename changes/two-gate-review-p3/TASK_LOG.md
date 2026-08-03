# Task Log: two-gate-review-p3

Branch `feat/two-gate-review-p3` (off `main` @ `fe4da9e`). Execution: one-task-at-a-time.

## Task 1 — Backend: grouped hand-made propose endpoint ✅ (awaiting human checkpoint)

**Delivered**
- `service.create_group(proposed_nodes, proposed_edges, reason, possible_schema_gap, proposed_by='human')`
  — validates every element against the type whitelists (injection guard), rejects empty groups,
  over-cap (`MAX_GROUP_ELEMENTS = 20`), and intra-group duplicate ids (combined node+edge set);
  stages all members with a shared `group:{proposed_by}:{uuid}` id inside one transaction (atomic).
  `possible_schema_gap` threaded via `schema_check.group_possible_schema_gap` (D5, no new column).
- `CurationGroupCreate` schema — structural only; business rules live in the service so every
  rejection follows the `{"error":{code,message}}` contract (not FastAPI's default 422 shape).
- `POST /admin/curation/groups` — admin-gated, `CurationError → APIError` map (documented contract).
  Legacy `/admin/curation/*` single-item routes untouched.

**Design note (refinement vs plan):** the element cap is enforced in `service.create_group`
(not the Pydantic validator) so its 422 shares the documented error contract with the other
guards; the schema stays structural. Satisfies condition 1 (fixed named cap) with uniform errors.

**Tests** (`backend/tests/api/test_curation_groups.py` + append to `test_review_groups.py`):
- round-trip: create → `GET /admin/review/groups` lists it (`pass` gate, real sentence, invisible
  to graph pre-approval) → approve round-trips into the approved graph;
- 422 bad type (injection guard), empty group, over-cap, **intra-group duplicate id** (cond. 3);
- `possible_schema_gap` → `is_gap` + `needs_schema_extension` (D5);
- **transaction atomicity** (cond. 2): fault-injected mid-group failure → whole group rolled back;
- **admin-auth** (cond. 4): `ADMIN_API_KEYS` set → no/ wrong key 401, valid key 201.

**Verification (Docker, offline mode — `OPENAI_API_KEY=` per the project's offline-first test posture)**
- Clean slate: `docker compose down -v` → up --build → seed (offline) → **`pytest tests ingestion/tests` = 163 passed, 0 failed** (pristine volume, so even the known idempotent-pipeline flake passed).
- Targeted: `test_curation_groups.py` + `test_review_groups.py` = 20 passed.
- ruff 0.15.21 (CI-pinned) check + format --check clean on all changed files; `mypy backend/app`
  = success (46 files). Compatibility: `test_curation.py` single-item path green.

**Environment note (not a code issue):** the host `.env` carries an `OPENAI_API_KEY` whose credits
are exhausted (429 insufficient_quota); running online-path seed/tests fails on it. The suite is
offline-first by design (CLAUDE.md: "tests run offline (no key configured)"), so verification was
run with the key blanked — the documented, intended test environment.

**Stop:** handed to human checkpoint before Task 2 (frontend). No commit yet.

## Task 2 — Frontend: Ingestion page + toggle + statement builder ✅ (awaiting human browser pass)

**Delivered** (`frontend/app.js`, `frontend/styles.css`)
- `renderIngest` reworked into an **Ingestion** page: one shared header + a `[🤖 LLM 抽取] ↔
  [✍️ 人工建構]` toggle (`.seg`) + a sub-container. Mode is a closure var (no hash sub-routing).
- `paintExtract(host)` = the previous extract flow verbatim (options/preview/run), minus its own
  page-head, **plus a disclosure note** that extract output is staged per-item and not yet grouped
  (honest about the P5 boundary).
- `paintHandmade(host)` = **statement builder**: add/remove concept rows (type/label/id/desc) and
  relation rows (type/source/target/id), a `possible_schema_gap` checkbox, client-side guards
  (≥1 element; every concept needs id+label, every relation needs id+source+target), and submit →
  `POST /admin/curation/groups`. On success: an "已提出…" notice with a `#review` link; the form
  resets. Errors surface `err.message` from the `{"error":{…}}` contract.
- CSS: `.ing-toggle`, `.sb-head/.sb-list/.sb-row/.sb-x/.sb-add/.sb-empty/.sb-gap`.

**Deviation found & fixed during T2 verification (provenance injection)**
The e2e smoke exposed that `extraction_output_schema` **requires `source_chunk_id` on every
node/edge** — but a hand-authored statement has no source chunk, and the builder doesn't (and
shouldn't) collect one. Without a fix every hand-made group would `fail_schema` and could never be
approved, defeating the approved A2 scope ("hand-made path wired through **and approvable**").
Fix: `service.create_group` stamps `source_chunk_id: "manual"` on any element lacking one (the
author *is* the source). The schema/contract is untouched (changing it would ripple into the
extract path — a stop condition). The round-trip HTTP test now sends **no** `source_chunk_id`, so
it proves the injection end-to-end (gate `pass` → approve round-trips).

**Verification (Docker, offline)**
- `node --check frontend/app.js` clean; SPA + app.js serve `200` via nginx.
- **Real e2e through nginx→backend→neo4j**: `POST /admin/curation/groups` (no source_chunk_id,
  the exact frontend payload) → group listed in `/admin/review/groups` as `proposed_by=human`,
  `schema_gate=pass`, correct back-translated sentence → `approve` `200` (3 nodes/3 edges into the
  graph). Empty group → `422` `{"error":{"code":"invalid_request"}}`.
- Targeted: 20 passed. **Clean-slate full suite: `pytest tests ingestion/tests` = 163 passed, 0
  failed** (pristine volume). ruff 0.15.21 check+format clean; `mypy backend/app` success.

**Owed (per approved plan — frontend manual-only):** a human browser pass of the M-checklist
(toggle repaint, builder add/remove/validation, `possible_schema_gap` banner in Review, no console
errors). The functional path is proven via e2e; only the *visual* layer is unverified.

**Browser-pass follow-ups (from the owner's live review):**
- *Edge-hugging fix:* the toggle + hand-made content sat in un-padded containers (the site's
  convention is a 48px gutter carried by each content body, e.g. `.ing-wrap`, `.page-head`). Added
  `.ing-toggle { margin: 0 48px }`, wrapped the builder in `.sb-wrap { padding: 4px 48px 40px;
  max-width: 1040px }`, and gave the extract disclosure note a 48px gutter.
- *Cache-busting:* `index.html` referenced `styles.css` with **no** version query, so the public
  domain's CDN/edge served a stale stylesheet even to a fresh incognito session. Bumped both refs
  to `?v=20260803-1` (`styles.css` newly gains a version param; `app.js` bumped). Owner confirmed
  the layout fix then appeared. See [[public-domain-cdn-cache]].
- *RWD:* left as a **separate future phase** (owner's call) — a minimal builder-responsive rule +
  small-screen gutter reduction was added, but comprehensive app-wide RWD is out of P3 scope.

**Stop:** handed to human checkpoint before Task 3 (nav consolidation + contract doc). No commit yet.

## Task 3 — Nav consolidation + contract doc ✅

**Delivered**
- `frontend/app.js`: removed the `curation` (`審訂`) nav entry; the now-unreferenced
  `renderCuration` **and** its private `resolveNodeLabels` helper deleted (dead code after the
  legacy per-item queue is retired from the UI). Renamed the `ingest` tab label `解析 → 收錄`
  (Ingestion) to match the merged page. Nav is now
  `問答 / 圖譜 / 典藏 / 收錄 / 群組審閱 / 審閱 / 評估`.
- `docs/api_contract.md`: added `POST /admin/curation/groups` (request schema, side-effects incl.
  the transaction + provenance `"manual"` stamp + no-graph-write, the four 422 guards, and the
  error-contract note).
- `/admin/curation/*` single-item endpoints untouched (decision C: keep endpoints). `審閱`
  (expert-demo) untouched (retires in P4).

**Verification**
- `node --check frontend/app.js` clean; no dangling `renderCuration`/`resolveNodeLabels` refs.
- Served nav (via nginx, frontend is a read-only mount so changes are live) shows the `審訂` tab
  gone and `收錄` present. Old `#curation` hash falls back to `chat` (unknown id → default).
- Compatibility: `POST /admin/curation/items` still `201` (legacy `{"detail"}` contract intact).
- Backend logic unchanged in T3 → the clean-slate **163 passed, 0 failed** result stands; ruff +
  mypy still clean (no backend/py edits in T3).

**Owed (unchanged):** human browser pass of the visual layer (M-checklist in the plan).

## Summary — all three tasks complete
Files: `backend/app/curation/service.py`, `backend/app/schemas/curation.py`,
`backend/app/api/routes_curation.py`, `backend/tests/api/test_curation_groups.py` (new),
`backend/tests/integration/test_review_groups.py`, `frontend/app.js`, `frontend/styles.css`,
`docs/api_contract.md`, `changes/two-gate-review-p3/*`. Not committed — awaiting verify/report/
review + the human browser pass.
