# Implementation Plan: expert-readable-review

> 原始需求(繁體中文):「我希望能在前端的審核頁面 改善成專家來讀的感覺 就是減少 code 感 對人類閱讀與輸入友好」
> 定案交付邊界(見文末 Human Decisions):**合成一份大計畫** — 同時 (A) 改善現有 `renderCuration` 審訂頁面的呈現,及 (B) 補完 `docs/expert-in-the-loop-plan.md` 的 Phase B + Phase C。

## Objective

讓「審核 / 審訂」流程對**非工程背景的領域專家**友好:把 schema code、raw JSON、node id 的「code 感」從人類要讀與要輸入的地方移除,改成白話卡片與句子;並補完 expert-in-the-loop governance demo 的引擎(反向翻譯 / engineer gate / gold)與呈現層(唯讀端點 + 三 tab 專家審閱畫面),使「AI 提案 → 工程師 gate 檢形式 → 反向翻譯成白話 → 專家不看 JSON 審語意 → schema gap → gold 回歸測試」這條敘事可端到端展示。

## In Scope

**Part 1 — 現有審訂頁面 polish（純前端）**
- 為 11 種 node type / 13 種 relationship type 建立中文可讀 label（閱讀 + 表單下拉）。
- 待審佇列卡片改成專家可讀:白話標題句、description 散文、edge 以**節點名稱**呈現（解析 id→label）、方向/關係用中文措辭。
- 原始 id / schema check / action 收進**可展開的「技術細節」**（工程師 gate 仍查得到，預設收起）。
- 提出候選表單:中文欄位標籤、去除 mono `CODE` 提示、友善 placeholder 與說明。
- 對應 `styles.css` 樣式（沿用本草/Honzō 視覺基底）。

**Part 2 — Expert-in-the-loop Phase B（後端，可純後端驗證）**
- `backend/app/graph/back_translation.py`：純函式 pattern renderer P1–P5 + `tests/unit/test_back_translation.py`。
- `backend/app/graph/engineer_gate.py`：複用既有驗證器 + `tests/unit/test_engineer_gate.py`（Case 5 → `needs_schema_extension`）。
- `data/sample/expert_demo/gold/*.json` + `backend/tests/gold/test_gold_examples.py`（結構最小斷言）。
- `data/sample/expert_demo/schema_gap_backlog.json` + `docs/schema-gap-policy.md`。

**Part 3 — Expert-in-the-loop Phase C（端點 + UI + 文件）**
- `backend/app/api/routes_expert_demo.py`：`GET /admin/expert-demo/cases`（read-only、admin key、讀 `cases.json`）+ 掛進 `main.py`。**（API 合約新增，人類 checkpoint）**
- 前端 `renderExpertDemo` 三 tab（AI Proposal / Engineer Gate / Expert Review；Expert tab 強制隔離不顯示 JSON/id）+ VIEWS 註冊 + styles（複用 `renderGraph`）。
- 文件:`docs/expert-in-the-loop-workflow.md`、`docs/rule-card-format.md`、`schema/rule_cards/*.md`（3 張）、`extraction_guidelines.md` / `README` 索引補一段。

## Out of Scope

- **Phase A**（`demo-cases-blood-glucose.md`、`cases.json`、5 案例生物學驗收）— **已完成並 commit**（`08edd49`、`3c16e32`），本計畫不重做，僅消費其產物。
- 任何 `schema/` 型別變更;`CellType/Stimulus/STIMULATES/AntagonisticInteraction/ON_PROCESS/ACTS_VIA` 一律只記 backlog（MVP 邊界 §七）。
- 多使用者 / 專家帳號 / 權限、真 pipeline 接入、prompt auto-optimization、schema migration UI、LLM 潤飾層。
- 改動 `curation_items` / `graph_change_logs` schema 或 approve/reject 的**寫入語意**（只改前端呈現，不改後端行為）。
- 新增任意 Cypher / bulk-export / `/all-nodes` 端點（`graph_plan` 5.3 明確禁止）。
- commit / push（除非審查後另行核准）。

## Current-State Evidence

- **Repository state**:分支 `main`,乾淨（僅未追蹤 `docs/agent-guideline.md`、`note.txt`,與本變更無關,不動）。無 pre-existing 失敗基線紀錄;`make test` 為既有綠燈假設,T5–T7 會實測。
- **現有審訂頁面（Part 1 目標）**：
  - `frontend/app.js:486` `renderCuration`;待審卡片渲染 `app.js:556-586`;edge 摘要 `app.js:560` = `${p.source}  —${p.type}→  ${p.target}\n${p.id}`（raw id + 英文 code）；schema badge `app.js:562-574`；`it.action` mono `app.js:578`。
  - 提出表單 `app.js:509-533`：`field()` 標籤帶 mono `CODE`（`app.js:510`）,placeholder 如 `hormone:example`/`edge:example`/`source node id`。
  - 型別常數:`NODE_TYPES` `app.js:483`（11 種）、`REL_TYPES` `app.js:484`（13 種）、`TYPE_COLOR` `app.js:108-114`。**無**任何中文 label 對照。
  - id→label 解析已有前例:graph 視圖 `nodesById` `app.js:247`。DOM helper `E()`;`api.get/post`;`shortId()`。
  - CSS:`.cur-wrap/.cur-col` `styles.css:234-236`、`.field*` `237-241`、`.seg*` `242-244`、`.qitem/.pay/.acts` `245-249`、`.schema-badge` `138`、`.tag-proposed` `136`、`.mono` `113`。
- **API 事實（Part 2/3 依賴）**：
  - `GET /nodes/{id}` 存在（`docs/api_contract.md:71`）→ 供 edge 端點 label 解析。
  - **無** `/all-nodes` / `/export-all` / `POST /cypher`（`api_contract.md:205`,`graph_plan` 5.3）→ Part 1 edge label 解析只能逐一 `GET /nodes/{id}` + 佇列同儕節點,查不到退回 `shortId`。
  - Curation 端點:`GET/POST /admin/curation/items`、`/{id}/approve|reject`（`api_contract.md:128-170`）。
  - 現有 route 模組 `backend/app/api/routes_*.py`;`main.py:9-15` import、`57-63` `include_router` — Part 3 依同模式新增。
- **可複用資產（不重造，§六）**：
  - `ingestion/pipeline/validate_extraction.py:10` `validate_extraction_output(candidate)`。
  - `ingestion/pipeline/normalize_concepts.py:1` `VALID_NODE_TYPES` / `:19` `VALID_RELATIONSHIP_TYPES`（type 白名單）。
  - `graph_change_logs` / `curation_items`（`schema.sql`、`curation/service._log_change`）。
  - 前端 `renderGraph` SVG（概念圖，Expert tab Tab3 複用）、`E()`/`svgEl()`。
- **Phase A 產物（已存在，消費而非重做）**：
  - `docs/demo-cases-blood-glucose.md`(tracked)。
  - `data/sample/expert_demo/cases.json`(tracked):`list` 共 **5 案**,每案 keys = `id / domain / source_text / proposal / did_not_understand_as / expert_review / gold`,符合 §五.1 規格。
- **尚不存在（本計畫要產出）**：`backend/app/graph/back_translation.py`、`engineer_gate.py`、`routes_expert_demo.py`、`data/sample/expert_demo/gold/`、`schema_gap_backlog.json`、`docs/schema-gap-policy.md`、`docs/expert-in-the-loop-workflow.md`、`docs/rule-card-format.md`、`schema/rule_cards/`、前端 `renderExpertDemo`。
- **既有測試**：`backend/tests/{unit,api,integration}`、`ingestion/tests`;**無前端 JS 測試**（Part 1 靠手動 + 無回歸驗證）。

## Acceptance Criteria

Part 1（現有審訂頁面）:
1. 待審佇列每張卡片預設**不**顯示 raw node id、schema code、`NODE/EDGE`/action 代碼於主視覺;改為白話標題（如「新增激素:胰島素」）與 description 散文。
2. Edge 卡片以**節點名稱**呈現關係（如「胰島 β 細胞 —分泌→ 胰島素」用中文關係詞），端點名稱由 `GET /nodes/{id}` + 佇列同儕解析;查不到才顯示 `shortId`,且不報錯。
3. 每張卡片有可展開的「技術細節」,展開後可見原始 id / schema check 明細 / action —— 工程師 gate 資訊零遺失。
4. 提出表單欄位為中文標籤、無 mono `CODE` 提示、placeholder 為人話;型別下拉顯示中文（value 仍送合法英文 code）。
5. 批准 / 拒絕行為與送出 payload **完全不變**（仍打同一 API、同一 body）。
6. 全程 offline（無 `OPENAI_API_KEY`）可運作。

Part 2（Phase B）:
7. `back_translation.render(proposal)` 對 5 案輸出符合 §五.2 P1–P5 模板的白話句;Case 5 命中 P5 gap 句;`test_back_translation.py` 綠燈。
8. `engineer_gate.evaluate(proposal)` 對 Case 1–4 = `pass`、Case 5 = `needs_schema_extension`;失敗碼 ∈ §五.3 集合;複用 `validate_extraction_output` 與型別白名單;`test_engineer_gate.py` 綠燈。
9. `gold/*.json` 存最小結構斷言;`test_gold_examples.py` 逐案綠燈。
10. `schema_gap_backlog.json` 含 Case 5 permissive_effect 及 D6 排除型別;`docs/schema-gap-policy.md` 有白話⇄code 對照表。

Part 3（Phase C）:
11. `GET /admin/expert-demo/cases` 唯讀回傳 `cases.json` 內容;受 admin key 保護（空 key = demo 開放,一致於現況);**不**寫 Neo4j、**不**碰 approved 圖、**不**繞過 curation。
12. 前端 `renderExpertDemo` 三 tab 可運作:Tab1 可見 JSON/id;Tab2 逐項 gate 燈號（當場計算或由端點附帶）；Tab3 專家畫面**不出現** JSON/id/schema code/gap code —— 只有原文、系統理解（當場 render）、概念圖、「系統沒理解成」、審查 radio、備註;選「無法表達」展開白話 gap radio;選擇存 sessionStorage。
13. `make test` 全綠;`make health` 通過;新端點與新 view 不破壞既有畫面。

## Contract, Schema, Dependency, and Migration Impact

- **API 合約新增**:`GET /admin/expert-demo/cases`（read-only）。需同步補 `docs/api_contract.md`。**這是合約變更審批點（T9）。**
- **DB schema**:無變更（不動 `schema.sql`、`curation_items`、`graph_change_logs`）。
- **圖 schema / 型別**:無變更（MVP 邊界明確排除;新型別只進 backlog）。
- **依賴**:不新增第三方套件（純函式 + FastAPI 既有 + 前端 vanilla）。無 migration。
- **不變式**:`status='approved'` 檢索不變式**不受影響** —— expert-demo 端點讀固定 json、不寫圖;offline 模式不變式維持（back_translation 為 deterministic 純函式,零 token）。

## Execution Policy

- **Plan revision**: r1（scope 由「純前端」→「合成大計畫」後的首版）。
- **Risk level**: **medium** —— 新增一個 read-only API 端點（合約新增）、後端純函式模組與測試、新前端 view;但全為**附加式**,不改資料寫入語意、不動 schema/型別、不碰 approved 不變式、無 migration/資料遺失。
- **Automation mode（建議，待人類明確核准）**: **supervised-auto**（medium 允許）。
- **Auto-approved task IDs**:T1、T2、T3、T4（Part 1 純前端）+ T5、T6、T7、T8（Phase B 後端,附加 + 測試自證）。
- **Human checkpoints（不自動）**:
  - **CP1** — Part 1 完成後,人類肉眼確認審訂頁面「專家感」達標（無自動測試可代）。
  - **CP2** — 進入 **T9 之前**:確認 `GET /admin/expert-demo/cases` 合約與 auth 行為（合約新增審批點）。
  - **CP3** — **T9、T10、T11**（Phase C:端點 + 使用者可見 view + 文件）逐一在核准後才做。
  - **CP4** — commit / push 前。
- **Approved file/path scope**:
  - Part 1:`frontend/app.js`、`frontend/styles.css`。
  - Part 2:`backend/app/graph/back_translation.py`、`backend/app/graph/engineer_gate.py`、`backend/tests/unit/`、`backend/tests/gold/`、`data/sample/expert_demo/gold/`、`data/sample/expert_demo/schema_gap_backlog.json`、`docs/schema-gap-policy.md`。
  - Part 3:`backend/app/api/routes_expert_demo.py`、`backend/app/main.py`、`frontend/app.js`、`frontend/styles.css`、`docs/{api_contract,expert-in-the-loop-workflow,rule-card-format}.md`、`schema/rule_cards/*.md`、`extraction_guidelines.md`/`README.md`。
- **Mandatory stop conditions**:需求衝突、發現需改 `schema/` 型別才能表達某案、需寫 Neo4j 或改 approve/reject 語意、`cases.json` 結構與 §五.1 不符導致 renderer/gate 需臆測、任何合約/資料遺失風險超出上述附加範圍。
- **Commit/push permission**: **No unless separately approved after review.**

## Tasks

### Part 1 — 現有審訂頁面 polish（純前端，低風險）

#### Task 1 — 中文可讀 label 對照 + 關係措辭 helper
- Files/symbols:`frontend/app.js`（新增 `NODE_TYPE_LABEL`、`REL_TYPE_LABEL` 對照表 + `phraseRelation(relType)` / `nodeTypeLabel(t)` helper;置於 `TYPE_COLOR` 附近 `app.js:108`）。
- Implementation:11 node type / 13 rel type → 教材慣用中文（如 `Hormone→激素`、`Structure→構造`、`RegulatoryEffect→調控效果`、`SECRETES→分泌`、`HAS_EFFECT→產生調控效果`、`REGULATES_SECRETION_OF→調控分泌`、`INCREASES→使…上升`、`DECREASES→使…下降`…）。value/送出仍用英文 code。未知型別 fallback 回原字串。
- Tests and container command:無自動測試;`make up` 後於瀏覽器確認對照被 T2/T3 使用。
- Stop/handoff:對照表定稿,交 T2/T3 消費。

#### Task 2 — 待審佇列卡片改白話 + edge label 解析 + 可展開技術細節
- Files/symbols:`frontend/app.js` `renderCuration.loadQueue` 卡片渲染（改寫 `app.js:556-586`);新增小工具解析節點 label（佇列同儕 payload 建 map + 對缺漏 id 逐一 `api.get('/nodes/'+id)`,失敗回 `shortId`，仿 `nodesById` `app.js:247`）。
- Implementation:node 卡 = 白話標題（`nodeTypeLabel(p.type)` + `p.label`）+ description 散文 + 理由;edge 卡 = 「{sourceLabel} —{phraseRelation(p.type)}→ {targetLabel}」。schema badge、raw id、`action`、raw payload 移入 `<details class="tech">` 收合區。批准/拒絕按鈕與 `decide()` 不動。
- Tests and container command:`make up`;提出 1 node + 1 edge 候選後檢視佇列;確認白話呈現、技術細節可展開、缺漏 id 退回 shortId 不報錯、approve/reject 仍正常。
- Stop/handoff:符合 AC1–3、5;停於 CP1 併同 T3/T4。

#### Task 3 — 提出候選表單人性化
- Files/symbols:`frontend/app.js` `field()`（`app.js:509-511`）與 `paintForm()`（`512-533`）;`seg` 標籤（`503-505`）。
- Implementation:欄位標籤改純中文、移除 mono `CODE` 參數（或改為極淡的中性提示）;placeholder 改人話（例:「輸入激素中文名」而非 `hormone:example`);型別 `select` option 顯示中文（`textContent` 中文、`value` 英文 code）;`seg` 顯示「節點 / 關係」。送出 body 與驗證（`app.js:534-541`）不變。
- Tests and container command:`make up`;送出一筆確認仍寫入 proposed、下拉送出的是合法英文 code。
- Stop/handoff:符合 AC4;停於 CP1。

#### Task 4 — CSS:專家卡片 + 收合區 + 表單
- Files/symbols:`frontend/styles.css`（調整 `.qitem/.pay` `247`、新增 `.tech`/`details` 樣式、去除卡片主視覺 mono、微調 `.field`）。
- Implementation:`.pay` 去 mono 改內文字體;技術細節 `<details>` 給收合樣式與 mono（僅限收合內);沿用既有 design tokens/色票,不引入新字體或外部資源。
- Tests and container command:`make up`;確認淺/深一致、無水平溢出、視覺與本草基底協調。
- Stop/handoff:Part 1 完成 → **CP1 人類肉眼驗收**。

### Part 2 — Expert-in-the-loop Phase B（後端,可純後端驗證）

#### Task 5 — back_translation renderer + 單元測試
- Files/symbols:新增 `backend/app/graph/back_translation.py`（純函式,pattern-match 結構簽章,**不呼叫 LLM、無模板引擎**）;`backend/tests/unit/test_back_translation.py`。
- Implementation:實作 P1–P5（§五.2 表）:輸入 `proposal{proposed_nodes, proposed_edges, references_existing}`,以型別/邊簽章比對輸出白話句;`direction_zh`(increase→上升/decrease→下降)、`trigger_zh`(由 edge `properties.trigger_direction`);無 pattern 命中 → P5 gap 句。references_existing 依 Phase A 已定案的 existing-node 模型解析 label。
- Tests and container command:`docker compose run --rm backend pytest tests/unit/test_back_translation.py` — 對 5 案斷言輸出句（Case 5 = gap 句）。
- Stop/handoff:AC7;綠燈後交 T6/T7。

#### Task 6 — engineer_gate + 單元測試
- Files/symbols:新增 `backend/app/graph/engineer_gate.py`;`backend/tests/unit/test_engineer_gate.py`。
- Implementation:複用 `validate_extraction_output`（`ingestion/pipeline/validate_extraction.py:10`）、`VALID_NODE_TYPES`/`VALID_RELATIONSHIP_TYPES`（`normalize_concepts.py`）、id 慣例 regex、三段式/Interaction pattern 檢查、`back_translation` 可用性、testability、duplication（標記不擋）。`result ∈ {pass, fail_schema, fail_pattern, fail_testability, needs_schema_extension}`;僅 Case 5 → `needs_schema_extension`;**gate 不碰生物語意**。
- Tests and container command:`docker compose run --rm backend pytest tests/unit/test_engineer_gate.py` — Case 1–4 `pass`、Case 5 `needs_schema_extension`。
- Stop/handoff:AC8。

#### Task 7 — gold 最小斷言 + 回歸測試
- Files/symbols:新增 `data/sample/expert_demo/gold/*.json`（各案 `expected_understanding` + `min_assertions{has_node_types, has_edge_types, direction}`）;`backend/tests/gold/test_gold_examples.py`（需要時加 `backend/tests/gold/__init__.py`）。
- Implementation:MVP 先打固定 proposal（來自 `cases.json`）,以 `back_translation` + 結構斷言逐案驗證,非完整 equality。
- Tests and container command:`docker compose run --rm backend pytest tests/gold/test_gold_examples.py`。
- Stop/handoff:AC9。

#### Task 8 — schema gap backlog + policy 文件
- Files/symbols:新增 `data/sample/expert_demo/schema_gap_backlog.json`、`docs/schema-gap-policy.md`。
- Implementation:backlog 每筆 `gap_id/raised_by_case/schema_gap_type/expert_facing_reason/example_text/status/proposed_schema_change/raised_at`;含 Case 5 `permissive_effect` 與 D6 排除型別（CellType/Stimulus/STIMULATES/AntagonisticInteraction/ON_PROCESS）。policy 文件放白話⇄`schema_gap_type` 對照表（§五.6）。
- Tests and container command:`python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('data/sample/expert_demo/*.json')]"`（JSON 合法性,經 backend 容器或本機皆可，優先容器）。
- Stop/handoff:AC10 → Phase B 完成。

### Part 3 — Expert-in-the-loop Phase C（端點 + UI + 文件；每項需 CP 核准）

#### Task 9 — 唯讀端點 + main 掛載 + 合約文件〔合約新增,先過 CP2〕
- Files/symbols:新增 `backend/app/api/routes_expert_demo.py`（`GET /admin/expert-demo/cases`,`require_admin`,讀 `data/sample/expert_demo/cases.json`）;`backend/app/main.py:9-15`/`57-63` 依現有模式 import + `include_router`;補 `docs/api_contract.md`。可選:端點附帶當場算的 engineer_gate 結果（不落地）。
- Implementation:唯讀、不寫任何 store、不碰 approved 圖;auth 行為與現有 `/admin/*` 一致（空 key = 開放）。
- Tests and container command:新增 `backend/tests/api/test_expert_demo.py`;`docker compose run --rm backend pytest tests/api/test_expert_demo.py`;`make health`。
- Stop/handoff:AC11;先取得 **CP2** 再動工。

#### Task 10 — 前端 renderExpertDemo 三 tab + 註冊 + 樣式
- Files/symbols:`frontend/app.js`（新增 `renderExpertDemo`、VIEWS 註冊 `{ id:'expert', label:'審閱' }` 於 `app.js:117-122` 陣列;複用 `renderGraph`）;`frontend/styles.css`。
- Implementation:左側 5 案例、右側 3 sub-tab（§五.4）。Tab3 Expert 強制隔離:**不**渲染任何 JSON/id/schema code/gap code/prompt;系統理解當場呼叫概念渲染或後端 render;審查 radio + 「無法表達」白話 gap radio;選擇存 sessionStorage。資料源 `GET /admin/expert-demo/cases`。
- Tests and container command:`make up`;逐 tab 手動確認;特別檢查 Tab3 DOM 內無 id/JSON 洩漏。
- Stop/handoff:AC12。

#### Task 11 — 文件收尾
- Files/symbols:新增 `docs/expert-in-the-loop-workflow.md`、`docs/rule-card-format.md`、`schema/rule_cards/*.md`（3 張,對應 P1–P4 主要 pattern）;`extraction_guidelines.md` 頂部指向 rule_cards;`README.md`/docs 索引補一段。
- Implementation:依 §五 與 roadmap C3/C4 撰寫;rule card 格式與既有文件語氣一致。
- Tests and container command:文件檢視;`make test` 全綠總驗收。
- Stop/handoff:AC13 → 全案完成,停於 CP4(commit 前)。

## Verification Strategy

- **正常**:`make up` → 手動走 Part 1 審訂頁面(node/edge 白話卡、技術細節收合、表單送出);`make test` 全綠(涵蓋 T5–T7、T9 新測試);`make health` 通過。
- **邊界**:edge 端點 id 查不到 → 退回 `shortId` 不報錯(T2);未知型別 → fallback 原字串(T1);Case 5 → gap 句 + `needs_schema_extension`(T5/T6)。
- **失敗**:`/admin/expert-demo/cases` 缺 admin key 時行為與現有 `/admin/*` 一致;cases.json 缺檔的錯誤走既有 error contract。
- **相容**:批准/拒絕 payload 與 API 不變(AC5);既有 `make test`、`make eval` 不回歸。
- **安全 / 不變式**:Tab3 DOM 無 id/JSON 洩漏(AC12);expert-demo 端點不寫圖、不繞 curation、不碰 `status='approved'` 檢索路徑;無新增任意 Cypher/export 端點。
- 驗證指令一律走既有容器封裝(`make up/test/eval/health`、`docker compose run --rm backend pytest …`);**無**主機直跑 Python。

## Risks and Unknowns

- **R1（前端無自動測試）**:Part 1 只能手動驗收 → 以 CP1 肉眼 gate 補償;approve/reject 不改 API 降低回歸面。
- **R2（edge label 解析多次 fetch）**:佇列大時逐一 `GET /nodes/{id}` 有 N 次請求;demo 佇列小可接受;可加簡單記憶體快取(同一 render 內)。查不到必須靜默 fallback。
- **R3（cases.json 契合度）**:Phase A 已定案,但 renderer/gate 需與其 `proposal`/`references_existing`/`properties.trigger_direction` 欄位精確對齊;**Unknown** — 需在 T5 開工時對讀實際 5 案結構,若欄位與 §五.1/§五.2 假設不符即為 stop condition,回報而非臆測。
- **R4（合約新增）**:新端點須同步 `api_contract.md`,並確認 auth 語意(空 key = 開放)與其他 `/admin/*` 一致 → CP2 把關。
- **R5（範圍大 / 11 任務）**:supervised-auto 只覆蓋 T1–T8;Phase C(T9–T11)逐項 CP,降低一次擴散風險。

## Rollback

- 全為附加式,無 migration/資料寫入變更 → 回滾 = `git checkout -- <files>` 或還原對應 commit。
- Part 3 端點以獨立 `routes_expert_demo.py` + 單行 `include_router` 掛載,移除該行即下線,不影響其他路由。
- 前端 `renderExpertDemo` 為獨立 view,自 VIEWS 陣列移除該項即隱藏,不影響審訂/其他分頁。
- Part 1 對 `renderCuration` 為就地改寫 → 回滾還原 `renderCuration` 函式與相關 CSS 區塊即可,後端零影響。

## Human Decisions and Approval

- **Decisions required（已在規劃對話取得,列此存證,仍待對本計畫整體核准）**:
  1. 交付邊界 = **合成一份大計畫**(Part 1 前端 polish + Phase B + Phase C)。〔已選〕
  2. edge 呈現 = **解析成節點名稱**(佇列同儕 + `GET /nodes/{id}`,fallback shortId)。〔已選〕
  3. 技術細節 = **收進可展開的「技術細節」**(工程師 gate 仍可見)。〔已選〕
  4. 自動化模式 = 建議 **supervised-auto**,auto-approve T1–T8,Phase C(T9–T11)逐項 CP。〔待對「medium 風險下的 supervised-auto + checkpoint 清單」明確核准〕
- **已解決的開放項**:
  - 中文 label 用詞**不**需對齊特定教材版本〔已定,2026-07-22〕→ T1 採教材通用、白話直觀譯法。
- **待確認的開放項**:
  - `schema/rule_cards/` 要幾張、對應哪些 pattern?(T11 暫定 3 張對 P1–P4)
- **Status**: **Approved**
- **Approved plan revision**: r1
- **Approved risk level and automation mode**: medium risk · **supervised-auto**(auto-approve T1–T8;Phase C T9–T11 逐項 CP)
- **`schema/rule_cards/` 張數**: 3 張(對 P1–P4)〔已定,2026-07-22〕
- **Approved by/date**: 使用者(busybutlazy@gmail.com),2026-07-22 —— 對話中明確回覆「我同意」。
- **Approval evidence**: 使用者於規劃對話核准 r1 全計畫、supervised-auto 模式與 checkpoint 清單、3 張 rule cards。Material plan changes invalidate approval.
