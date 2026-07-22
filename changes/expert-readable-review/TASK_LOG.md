# Task Log: expert-readable-review

- Plan revision: r1 (Approved)
- Approval evidence: 使用者 (busybutlazy@gmail.com) 2026-07-22 對話明確回覆「我同意」— 核准 r1、medium risk、supervised-auto、checkpoint 清單、3 張 rule cards。
- Risk level: medium
- Automation mode: supervised-auto
- Auto-approved tasks: T1, T2, T3, T4 (Part 1 前端 polish) + T5, T6, T7, T8 (Part 2 Phase B 後端)
- Approved path scope: frontend/app.js, frontend/styles.css, backend/app/graph/{back_translation,engineer_gate}.py, backend/tests/{unit,gold}/, data/sample/expert_demo/{gold/,schema_gap_backlog.json}, docs/schema-gap-policy.md
- Phase C (T9–T11): NOT in this run — requires CP2/CP3.
- Baseline Git state and tests: branch `main`, clean except untracked `changes/`, `docs/agent-guideline.md`, `note.txt` (unrelated, preserved). Phase A already committed (08edd49, 3c16e32). Baseline `make test` assumed green; T5–T7 will exercise new tests.

---

## T1 — 中文可讀 label 對照 + 關係措辭 helper — Result: Pass
- Paths: frontend/app.js (additive, near typeColor)
- Added NODE_TYPE_LABEL / REL_TYPE_LABEL maps + nodeTypeLabel()/phraseRelation() (value/API still English codes).
- Check: `node --check frontend/app.js` OK.
- Deviations: None.

## T2 — 待審佇列白話卡片 + edge label 解析 + 可展開技術細節 — Result: Pass
- Paths: frontend/app.js (resolveNodeLabels + nodeLabelCache module-level; rewrote loadQueue rendering).
- Node card = 類型 pill + 名稱 + description; edge card = {sourceLabel} {關係中文} {targetLabel}; raw id/schema/action/原始關係 → <details class="q-tech">; approve/reject 與 decide() 不動; schema 失敗時卡片加 qitem-warn + summary ⚠ 提示.
- GET /nodes/{id} returns {id,type,label,description,properties} (approved-only→404); fallback sibling queue → shortId, silent.
- Check: node --check OK.
- Deviations: None.

## T3 — 提出候選表單人性化 — Result: Pass
- Paths: frontend/app.js (seg labels 概念/關係; field(label,input,hint) drops mono CODE; paintForm human-first fields, zh option text with English value, plain hints).
- Submit body/validation unchanged (same API/body).
- Check: node --check OK.
- Deviations: field() signature reordered (label,input,hint); all call sites are local to renderCuration and updated together.

## T4 — CSS 專家卡片 + 收合區 + 表單 — Result: Pass
- Paths: frontend/styles.css (+22 lines: .q-head/.q-kind/.q-name/.q-rel/.q-edge/.q-desc/.q-reason/.q-tech(+summary marker)/.q-tech-body/.q-warn/.qitem-warn/.field-hint). Uses existing design tokens only.
- Check: CSS brace balance 210/210.
- Deviations: None.

## T5 — back_translation renderer + 單元測試 — Result: Pass
- Paths: backend/app/graph/back_translation.py (pure, no LLM); backend/tests/unit/test_back_translation.py.
- Patterns P1–P5 per §五.2; build_context() cross-case label + effect_to_hormone index (references_existing 解析).
- Container: `docker compose run --rm --build backend pytest tests/unit/test_back_translation.py` → 6 passed.
- Host pre-check: all 5 rendered sentences match gold expected text exactly.
- Deviations: None.

## T6 — engineer_gate + 單元測試 — Result: Pass
- Paths: backend/app/graph/engineer_gate.py (reuses validate_extraction_output + VALID_NODE/RELATIONSHIP_TYPES); backend/tests/unit/test_engineer_gate.py.
- 8 checks §五.3; id-convention on node ids only (edge ids like e:c1:has_effect intentionally exempt); result precedence fail_schema→fail_pattern→needs_schema_extension→fail_testability→pass.
- Container: 5 passed. Cases 1–4 pass, Case 5 needs_schema_extension.
- Deviations: None.

## T7 — gold 最小斷言 + 回歸測試 — Result: Pass
- Paths: data/sample/expert_demo/gold/*.json (5); backend/tests/gold/test_gold_examples.py.
- In-task correction: case_002 gold wrongly listed PhysiologicalVariable in has_node_types (it is references_existing, not proposed); removed. Re-ran → 6 passed.
- Container: `docker compose run --rm backend pytest tests/gold/test_gold_examples.py` → 6 passed.
- Deviations: gold data fix within task boundary (ordinary mistake).

## T8 — schema gap backlog + policy — Result: Pass
- Paths: data/sample/expert_demo/schema_gap_backlog.json (5 entries incl. Case5 permissive_effect + D6 excluded types); docs/schema-gap-policy.md (白話⇄code 表).
- Check: JSON valid (5 entries).
- Deviations: None.

## Full verification (make test) — 1 pre-existing failure, unrelated to change
- `make test` → 122 passed, 1 failed in 231.72s.
- FAIL: ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent — chunk_count 12 != 9.
- Root cause: chunks table holds 8 chunk:sample:* + 4 doc:private:endocrine_demo_v1:chunk:* ; the 4 private chunks are written by the pre-existing document-ingestion (extract) test and persist in the shared Postgres volume. The idempotent-pipeline test counts ALL rows against the 9-chunk sample source, so it fails against any non-pristine volume.
- Attribution: NOT caused by this change. Seed loader reads fixed filenames (biology_sample_*.json), so data/sample/expert_demo/* is invisible to it; the diff adds no chunks and does not touch ingestion pipeline or the failing test. Evidence: chunk_id listing above; git diff scope = frontend + app/graph + new tests + expert_demo data + docs only.
- Per supervised-auto contract: recorded, did NOT modify the failing test (out of approved path scope). Stopping.

## STOP — reached planned checkpoints
- All auto-approved tasks T1–T8: Pass. Change-scoped tests green (17 new tests).
- CP1 (human visual acceptance of Part 1 frontend) pending — requires human to view running app.
- Phase C (T9–T11) NOT started — gated behind CP2/CP3.

---
# Phase C (T9–T11) — approved to continue via user instruction「先繼續」(CP2/CP3)

## Cache-bump (out-of-original-scope, user-approved fix) — Result: Pass
- frontend/index.html: app.js?v=20260722-1 → -2 → -3 (每次前端變更後 bump,強制瀏覽器重取).
- Cause of "看不到變更": nginx mounts ./frontend live (verified served app.js has new tokens); browser cached old ?v. make down/up 不改 ?v,故無效。

## T9 — 唯讀端點 GET /admin/expert-demo/cases + main 掛載 + 合約 — Result: Pass
- Paths: backend/app/api/routes_expert_demo.py (require_admin; reads DATA_DIR/expert_demo/cases.json; system_understanding + engineer_gate 當場算,不落地); backend/app/main.py (import + include_router); docs/api_contract.md (新增端點段落); backend/tests/api/test_expert_demo.py.
- Read-only: no writes, no Neo4j, does not touch approved graph or curation.
- Verify: restarted running backend (uvicorn no --reload; app/ mounted) → live curl via nginx: 200, 5 cases, gate 1–4 pass / 5 needs_schema_extension, understanding sentences correct. In-container: test_expert_demo.py 2 passed.
- Deviations: None (matches plan §五.4; contract addition documented).

## T10 — 前端 renderExpertDemo 三 tab + VIEWS 註冊 + styles — Result: Pass
- Paths: frontend/app.js (VIEWS {id:'expert',label:'審閱'}; renderExpertDemo + conceptMap reusing forceLayout/svgEl/typeColor; GAP_OPTIONS); frontend/styles.css (+ .ex-* block).
- Tab1 AI提案 (shows id/JSON), Tab2 工程師gate (逐項燈號 from engineer_gate.checks), Tab3 專家審閱 強制隔離 (原文/系統理解/概念圖(僅label,無id、不可點開)/系統沒理解成/審查radio/無法表達→白話gap radio/備註; sessionStorage per case).
- Verify: node --check OK; CSS braces 253/253; served live via nginx (v3).
- Deviations: None. Manual visual (CP1/CP3) pending user.

## T11 — 文件收尾 — Result: Pass
- Paths: docs/expert-in-the-loop-workflow.md, docs/rule-card-format.md, schema/rule_cards/{single_regulatory_effect,secretion_trigger,antagonistic_interaction}.md (3), schema/extraction_guidelines.md (指向 rule_cards + workflow), README.md (審閱 row).
- Deviations: None.

## Phase C full verification
- `docker compose run --rm --build backend pytest` (4 new suites) → 19 passed.
- `make test` (full) → 124 passed, 1 failed (261s). Failure = same pre-existing test_pipeline_run_is_idempotent chunk-count (unchanged, unrelated). No new regressions from Phase C (TestClient(app) API tests pass ⇒ main.py imports/starts clean).
- Live: /health 200, /admin/expert-demo/cases 200 via nginx; frontend served live at ?v=-3.

## FINAL STATE
- All tasks T1–T11 complete. New tests: 19 (2 api + 6 renderer + 5 gate + 6 gold), all green.
- Pending human: CP1/CP3 visual acceptance of 審訂 + 審閱 分頁 (hard-refresh or ?v=-3 handles cache).
- Nothing committed.
