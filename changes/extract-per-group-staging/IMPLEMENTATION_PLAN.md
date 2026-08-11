# Implementation Plan: extract-per-group-staging

## Objective

讓 **LLM 抽取路徑**的產出以「一個生物陳述 = 一個提案群組」的形式進入群組審閱佇列，接上目前斷開的
主線：`文件 → LLM 抽取 → 兩道 gate → 專家審閱 → 寫入知識圖譜`。今日抽取結果以單項寫入且不帶
`group_id`，永遠不會出現在群組審閱頁（`frontend/app.js:928` 對使用者揭露了這個斷點）。

分組規則、去重語意與 chunk 邊界已於 `changes/phase-p5-run-2026-08-11/` 的 grill 會期定案（G1–G3）。

## In Scope

1. `ingestion/pipeline/group_statements.py`（新檔）：**純函式**切分器，把一份
   `{nodes, edges}` 抽取輸出切成數個群組——每個 pattern anchor（`RegulatoryEffect` / `Interaction`）
   一組，殘餘一組。
2. `ingestion/pipeline/load_postgres.stage_extraction_output`：改為 group-aware——寫入
   `group_id`、item_id 改群組範圍、已 approved 的節點只被引用不重新提案。
3. `ingestion/extract/runner.py`：呼叫點傳入 `chunk_id` 與 approved-id 集合；統計加上群組數。
4. 更新既有抽取測試 + 新增切分器單元測試 + `curation_items` 層級的重跑冪等斷言。
5. 移除 `frontend/app.js` 的「尚未自動組成審閱群組」揭露文字（該限制已解除）；`docs/api_contract.md`
   記載抽取路徑現在也產生群組。

## Out of Scope

- **schema-gap backlog 生命週期**（DF1）與 **gold 改打真實抽取輸出**（DF2）——P5 的另外兩個產出，
  已由 owner 決議拆開。
- 任何 `schema/` 型別變更、`extraction_output_schema.json` 或 prompt 變更（G1 選 (c) 正是為了避免）。
- `approve_group` / `reject_group` / `record_group_gap` / `create_group` 的任何邏輯變更。
- 檢索路徑、`status='approved'` 不變式、seed 路徑（`stage_demo_review_group` 不動）。
- 抽取路徑設定 `possible_schema_gap`（I5：schema 無此欄位）。
- 既有 `group_id IS NULL` 資料的 backfill（I4：DB 內無此類資料）。

## Current-State Evidence

- **Repository state:** `main` @ `0a3e5be`（PR #16 已合併）。工作區唯一未追蹤項為
  `changes/phase-p5-run-2026-08-11/`（本次 grill 的規劃產物）。無不明修改。
- **Relevant files and symbols:**
  - `ingestion/pipeline/load_postgres.py:109 stage_extraction_output(conn, candidate)
    -> (ok, error, staged_nodes, staged_edges)`——逐元素 `INSERT … ON CONFLICT (item_id) DO NOTHING`，
    `item_id = f"curation:{node['id']}"`（**全域**），`proposed_by='llm'`，**不寫 `group_id`**。
  - `ingestion/extract/runner.py:262` 唯一呼叫點，在逐 chunk 迴圈內；
    `:153 ingest_document(..., neo4j_driver=None, ...)`——driver 是**選用**的
    （`:90 _fetch_existing_concepts` 在 None 時退回無提示）。
  - `backend/app/graph/engineer_gate.py:42 _pattern_check`——只認 `RegulatoryEffect`
    （HAS_EFFECT 入邊 / ON_VARIABLE 出邊 / INCREASES|DECREASES 出邊）與 `Interaction`
    （≥2 條 USES_EFFECT / ON_VARIABLE）。
  - `backend/app/curation/service.py:378 list_groups` 只取 `group_id IS NOT NULL AND status='proposed'`；
    其 ctx 組裝**已能解析「被引用但非提案」的既有 approved 節點標籤**（`:396-399`）。
  - `ingestion/pipeline/normalize_concepts.py`：`VALID_NODE_TYPES` / `VALID_RELATIONSHIP_TYPES`
    白名單所在，是 pattern anchor 常數的自然歸屬。
- **架構事實（決定實作放置位置）：** `backend` 依賴 `ingestion`
  （`main.py:18`、`service.py:12-13`、`retriever_vector.py:14`、`db/qdrant_client.py:4`），
  **`ingestion` 完全不依賴 `backend`**（`grep "^from app\." ingestion/` 為空）。
  因此切分器必須放在 `ingestion`，**不得** import `engineer_gate`。
- **切分器只需要 anchor 型別，不需要複製 pattern 規則（觀察，非假設）：** 群組 = anchor 節點 +
  所有與其相連的邊 + 邊另一端的節點。以血糖語料驗證：RE1 的相連邊為 HAS_EFFECT/ON_VARIABLE/DECREASES，
  端點為胰島素、血糖 → 正確切出組 1；RE2 同理切出組 2。**無需任何 pattern 專屬的邊型別知識**，
  故 `_pattern_check` 的完整性規則不會被複製、不存在漂移面。
- **Existing behavior and baseline tests:**
  - `ingestion/tests/test_document_ingest.py` 以注入的 `fake_extract` + `pg_conn`/`qdrant_client`
    fixtures 跑完整 run，**零 token**；`test_full_run_is_idempotent_on_chunk_count:189` 目前
    **只斷言 chunk 數**，不涵蓋 `curation_items` 的重跑冪等。
    這些測試**不帶 neo4j fixture**（`ingest_document` 的 driver 為 None）。
  - Baseline（`main` @ `0a3e5be`，離線姿態實跑於 2026-08-11）：
    `pytest tests ingestion/tests` → **171 passed**；`app.eval.runner` → Overall **PASS**；
    ruff + mypy 全清。**無既知失敗**。
  - `curation_items` 現況：`demo` 19 列、`human` 8 列，全部 `group_id NOT NULL`；`llm` **0 列**。

## Acceptance Criteria

1. **切分正確性（G1）：** 對一份含兩個完整 RegulatoryEffect 且**共用**一個
   `PhysiologicalVariable` 的抽取輸出，切分器回傳 **2 個 pattern 組**（各含自己的 anchor、三條邊、
   兩個端點節點），共用節點**同時出現在兩組**；無殘餘時不產生殘餘組。
2. **殘餘組（I2）：** 不與任何 anchor 相連的節點/邊歸為單一殘餘組；該 chunk 若無殘餘則不產生該組。
3. **群組可見（主線接通）：** 跑完一次離線 `ingest_document` 後，
   `service.list_groups()` 回傳該次抽取產生的群組，每組帶 `schema_gate` 與 `understanding`；
   完整三段式的組 gate = `pass`，且 `understanding.text` 描述的是**該組自己**的陳述。
4. **去重語意（G2）：** 已存在於 approved 圖的節點**不被重新提案**（不產生 node item），
   但仍可作為邊端點被引用；未核准的共用節點在每一組各自提案。
5. **重跑冪等（I1）：** 對同一文件連續執行兩次 `ingest_document`，`curation_items` 的列數與
   `list_groups()` 的群組數**不增加**（`group_id` 為確定性命名，item_id 隨之穩定）。
6. **Neo4j 未被觸碰：** 抽取路徑全程不寫 Neo4j（沿用現況；以查詢節點筆數斷言）。
7. **驗證全綠：** `pytest tests ingestion/tests` 離線 ≥ 171 + 新增測試且全通過；
   `app.eval.runner` Overall PASS；ruff `check`/`format --check`、mypy、`node --check` 全清。
8. **文件同步：** `frontend/app.js` 的「尚未自動組成審閱群組」揭露文字移除且 `?v=` bump；
   `docs/api_contract.md` 記載抽取路徑產生群組與 `group_id` 命名規則。

## Contract, Schema, Dependency, and Migration Impact

- **Contract：** 無端點簽章變更。`GET /admin/review/groups` 開始回傳 `proposed_by='llm'` 的群組——
  **純資料新增**，回應形狀不變。`POST /admin/ingest/run` 的 `stats` **新增** `proposed_groups` 欄位
  （加欄位，既有欄位不動）；須同步 `docs/api_contract.md`。
- **Schema/DB：** **無 migration**。`group_id` 欄位已存在（P1 加入，nullable）；本變更只是開始在
  抽取路徑寫入它。
- **資料語意變更（需核准點）：** `curation_items.item_id` 在**抽取路徑**由全域
  `curation:{elem_id}` 改為群組範圍 `curation:{group_id}:{elem_id}`。既有 `llm` 資料為 0 列
  （已查證），故無資料相容問題；但這**移除了跨陳述的全域去重**——同一未核准概念會在多組各自提案，
  此後果已由 owner 於 G2 明示接受。
- **Dependency / Migration：** 無新增依賴、無 migration。

## Execution Policy

- **Plan revision:** 2（Draft）
- **Risk level:** **medium**——新增寫入語意與 item_id 方案變更；但無 migration、無依賴、
  不碰 Neo4j、不碰 approve/reject/gate 邏輯，且既有 `llm` 資料為 0 列。
- **Automation mode:** **混合**——T1 為單一任務後停；**T2、T3 為 `supervised-auto`**。
  依據:停點的價值在於「人能發現機器發現不了的事」。T1 之後要判斷的是**一個生物陳述的邊界該畫在哪**,
  那是領域判斷,測試只能驗證我寫的規則有被執行、驗不出規則本身是否符合生物學。T2／T3 的正確性則是
  完全可機器驗證的(測試綠不綠、欄位對不對),停在那裡只會得到「測試過了,繼續」。
  （revision 1 曾提「單獨授權 T1 走 supervised-auto」——那是思考錯誤:T1 是第一個任務,任何模式下
  跑完都會停,授權它自動化省不到任何東西。已移除。）
- **Auto-approved task IDs（`supervised-auto`）：** **T2、T3**（且僅在 T1 checkpoint 與 T1.5
  觀察結果均獲 owner 通過之後才解鎖）
- **Approved file/path scope:**
  `ingestion/pipeline/group_statements.py`（新）、`ingestion/pipeline/normalize_concepts.py`、
  `ingestion/pipeline/load_postgres.py`、`ingestion/extract/runner.py`、
  `ingestion/tests/test_group_statements.py`（新）、`ingestion/tests/test_document_ingest.py`、
  `backend/tests/unit/test_engineer_gate.py`（僅新增漂移守衛測試）、
  `frontend/app.js`、`frontend/index.html`、`docs/api_contract.md`、`changes/extract-per-group-staging/*`
- **Human checkpoints:**
  1. **T1 完成後**——切分規則正確性是整個變更的地基。我會把切分結果攤開給 owner 看（真實語料形態），
     由 owner 判斷陳述邊界是否符合生物學。
  2. **T1.5 真實抽取觀察之後**——若真實輸出出現計畫未預期的形態，**停止並回到 T1 修改切分器**，
     不得帶著未預期形態進入 T2。
- **Mandatory stop conditions:** 需要 migration、需要改 `extraction_output_schema` 或 prompt、
  需要改 `engineer_gate`/`back_translation`/`approve_group` 任一邏輯、需要新增依賴、
  切分規則與 grill 定案不符、離線套件出現非本變更造成的失敗、
  **T1.5 觀察到計畫未預期的抽取形態**、supervised-auto 期間需要新增任務或路徑。
- **Commit/push permission:** **No unless separately approved after review.**

## Tasks

### Task 1 — 切分器（純函式，零 DB）

- **Files/symbols:** 新增 `ingestion/pipeline/group_statements.py`；
  `PATTERN_ANCHOR_TYPES` 常數置於 `ingestion/pipeline/normalize_concepts.py`（與既有型別白名單同處）。
- **Implementation:**
  `split_into_statements(candidate: dict, chunk_id: str) -> list[dict]`，每個群組為
  `{"group_id": str, "nodes": [...], "edges": [...]}`。
  規則：對每個型別屬於 `PATTERN_ANCHOR_TYPES`（`RegulatoryEffect`、`Interaction`）的節點，
  取其**所有相連邊**與邊另一端的節點成一組，`group_id = f"group:llm:{chunk_id}:{anchor_id}"`；
  未被任何 anchor 組佔用的節點與邊歸為 `group:llm:{chunk_id}:residual`，無殘餘則不產生。
  群組順序穩定（依 anchor id 排序），純函式、不碰 IO。
- **Tests and container command:** 新增 `ingestion/tests/test_group_statements.py`——
  (a) 兩個 RE 共用一個變數 → 2 組、共用節點同時出現在兩組；
  (b) 純殘餘（Misconception / PART_OF）→ 1 組殘餘；
  (c) 混合（1 個 RE + 額外孤立邊）→ 2 組；
  (d) **不完整 pattern**（RE 只有 HAS_EFFECT）→ 仍成組（讓 gate 去判 `fail_pattern`）；
  (e) 空輸入 → 空清單；(f) 相同輸入兩次呼叫產生相同 `group_id`（確定性）。
  另於 `backend/tests/unit/test_engineer_gate.py` 新增**漂移守衛**：斷言
  `_pattern_check` 特別處理的節點型別集合 ⊆ `PATTERN_ANCHOR_TYPES`（backend 可 import ingestion）。
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests/test_group_statements.py tests/unit/test_engineer_gate.py -q
  ```
- **Stop/handoff:** 完成後停，等 checkpoint。

### Task 1.5 — 真實抽取形態觀察（花費 token；owner 執行，checkpoint）

**這不是實作任務，是為了關掉計畫裡唯一的 unknown（R1）。** 排在 T1 之後、T2 之前——此時切分器已存在
可直接餵真實輸出，若形態出乎意料，要改的是 T1 而非已寫完的 T2。

- **為什麼值得花：** 切分規則是從 `_pattern_check` 的語意**推導**的，我從未看過真實 LLM 抽取的產出。
  單元測試只能覆蓋「我想得到的」形態。成本：`gpt-4o-mini`（`llm_client.py:15 EXTRACTION_MODEL`），
  一章 4 個 chunk = 4 次呼叫，chunk 文字極短（83–157 字），主要成本是 system prompt + 既有概念清單
  （`max_existing=200`）——**總計不到 1 美分**。
- **執行方式：** 由 **owner** 執行一次真實 `POST /admin/ingest/run`（需 `INGEST_OWNER_SECRET`
  第二道鎖，執行者無此權限），或由 owner 授權後以既有容器入口執行。
- **要觀察的具體問題：**
  1. 一個 `RegulatoryEffect` 是否會連到**兩個以上**不同的 `PhysiologicalVariable`？
     （若會，該切成幾組是計畫未涵蓋的形態）
  2. 是否出現兩個 anchor 共用同一批邊？
  3. 單一 chunk 實際產出的節點／邊規模，與殘餘元素的比例（驗證 I2 的 6–8 組估計）。
  4. LLM 是否會重複提出既有概念（驗證 G2 的 approved 引用分支會被走到）。
- **判準：** 若觀察到的形態都在 T1 的六個單元測試涵蓋範圍內 → 通過，解鎖 T2／T3 的 supervised-auto。
  **若出現未預期形態 → 停止，回到 T1 修改切分器並補測試**，重新走此 checkpoint。
- **Stop/handoff:** 觀察結果如實記錄於 `TASK_LOG.md`（含實際 token 花費），交 owner 判定。

### Task 2 — group-aware staging + approved 引用

- **Files/symbols:** `ingestion/pipeline/load_postgres.py::stage_extraction_output`；
  `ingestion/extract/runner.py`（`:262` 呼叫點、`:195` 附近取得 approved id）。
- **Implementation:**
  - 簽章改為 `stage_extraction_output(conn, candidate, chunk_id, approved_ids: frozenset[str] = frozenset())`，
    回傳 `(ok, error, staged_nodes, staged_edges, staged_groups)`。
    **approved 判定以參數注入**（呼應本模組「injectable resources」風格），使離線測試無需 Neo4j
    即可覆蓋引用分支。
  - 先 `validate_extraction_output`（維持現行順序），再呼叫 `split_into_statements`；
    逐組寫入：`item_id = f"curation:{group_id}:{elem_id}"`、`group_id=group_id`、
    `proposed_by='llm'`、`schema_check` 逐元素照舊。
    **id 在 `approved_ids` 內的節點不寫 node item**（只作為邊端點被引用）；
    若某組扣掉 approved 節點後**不剩任何元素**，該組不寫入。
  - `runner.py`：`approved_ids` 由既有 `neo4j_driver` 查詢 approved 節點 id 取得，
    driver 為 None 時退回空集合（維持今日行為，離線測試路徑不變）；統計新增 `proposed_groups`。
- **Tests and container command:** 更新／新增於 `ingestion/tests/test_document_ingest.py`——
  (a) `test_full_run_stages_proposed_and_writes_chunks` 改為斷言列有 `group_id` 且群組數符合預期；
  (b) **新增** `curation_items` 層級的重跑冪等斷言（跑兩次，列數與群組數不變）——
      補上今日 `test_full_run_is_idempotent_on_chunk_count` 的缺口；
  (c) **新增** 傳入 `approved_ids` 含某節點時，該節點不產生 node item、但邊仍寫入；
  (d) **新增** 端到端：離線 run 後 `service.list_groups()` 看得到該群組，且完整三段式組
      `schema_gate.result == 'pass'`、`understanding.text` 描述本組陳述；
  (e) Neo4j 未被寫入（查詢提案節點 id → 0 列）。
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests/test_document_ingest.py -q
  ```
- **Stop/handoff:** 完成後停，等 checkpoint。

### Task 3 — 文件、前端揭露文字、完整驗證

- **Files/symbols:** `frontend/app.js`（移除 `:928` 附近的「尚未自動組成審閱群組」段落）、
  `frontend/index.html`（`?v=` bump）、`docs/api_contract.md`。
- **Implementation:** `api_contract.md` 記載抽取路徑現在產生提案群組、`group:llm:{chunk_id}:{anchor}`
  命名規則、`stats.proposed_groups` 新欄位，以及「已 approved 節點只引用不提案／未核准則各組重複提案」
  的去重語意。
  **必須明寫 409 的觸發條件與處理動作**（否則日後會被誤判為 bug）：
  當一個 chunk 引進一個**全新**概念、而該概念同時被兩個**全新**陳述共用時，核准第一組會把該節點寫入
  approved 圖，核准第二組即命中「成員 id 已存在於 approved 圖」→ `409`。
  處理動作:**退回第二組並重新匯入**——此時該概念已核准,第二次會走引用分支而不再提案。
  文件須說明這是**開拓全新領域的首次匯入**才會踩到:已核准的共用概念（如
  `physiological_variable:blood_glucose`,已在 seed 的 45 個 approved 節點內）一律走引用分支,不會 409；
  圖譜越成熟越少見。
- **Tests and container command:**
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
  docker compose run --rm -e OPENAI_API_KEY= backend python -m app.eval.runner
  docker run --rm -v "$PWD":/w -w /w ghcr.io/astral-sh/ruff:0.15.21 check backend/app ingestion backend/tests ingestion/tests scripts
  docker run --rm -v "$PWD":/w -w /w ghcr.io/astral-sh/ruff:0.15.21 format --check backend/app ingestion backend/tests ingestion/tests scripts
  mypy backend/app ingestion scripts
  node --check frontend/app.js
  ```
- **Stop/handoff:** 產出 verification + change report 後停，交獨立審查。

## Verification Strategy

- **Normal:** 血糖語料形態（兩個 RE 共用一個變數）切成兩組，各自 gate `pass`、各自有正確的白話句；
  離線 `ingest_document` 後群組出現在 `list_groups()`。
- **Boundary:** 空輸入；純殘餘 chunk；不完整 pattern（應成組並被 gate 判 `fail_pattern`）；
  某組扣掉 approved 節點後為空（不寫入）。
- **Failure:** 抽取輸出 schema 驗證失敗時維持現行行為（不寫入、標記該 chunk 失敗）——
  以既有 `test_failed_extraction_flags_chunk_but_job_succeeds` 覆蓋。
- **Compatibility:** demo/手工兩條 staging 路徑不變（`stage_demo_review_group`、`create_group` 未動）；
  `list_groups`/`approve_group`/`reject_group`/`record_group_gap` 全數既有測試維持通過。
- **Security:** 不新增端點；型別仍走 `VALID_NODE_TYPES`/`VALID_RELATIONSHIP_TYPES` 白名單與
  `schema_checker`；SQL 全參數化；不觸 Cypher label 內插；不寫 Neo4j。
  `status='approved'` 檢索不變式未被觸及（以 `app.eval.runner` 佐證檢索未退化）。
- 全部**自動化**驗證命令走既有 Docker/Compose/Make 入口，離線姿態（`-e OPENAI_API_KEY=`），零 token。
- **唯一的線上動作是 T1.5**（owner 執行的一次真實抽取觀察，`gpt-4o-mini`，<1 美分）——它是
  checkpoint 證據，不是自動化驗證的一部分；離線套件不依賴它。

## Risks and Unknowns

- **R1（已知缺口，來自 grill）：未實跑真實 LLM 抽取**——單一 chunk 的真實產出規模與形態未觀察過。
  切分行為以確定性語意推導。**緩解（revision 2 升級）**：T1 的六個單元測試涵蓋多 pattern／純殘餘／
  混合／不完整 pattern 四種形態，**且新增 T1.5 為強制 checkpoint**——owner 執行一次真實抽取觀察
  （<1 美分），未預期形態即回到 T1。此風險由「接受並靠單元測試」升級為「用不到一美分關掉」。
- **R2：審閱負載**——4-chunk 章節約產生 6–8 個待審群組（I2 的已知後果）。非缺陷，但會改變審閱頁的
  視覺密度；T1.5 可提前得到真實數字，T3 的瀏覽器確認時一併觀察。
  **曾考慮但不採用的緩解**：殘餘組不進審閱佇列（可降到約 4–5 組）——不採用,因為殘餘裡含
  `Misconception` 節點（「學生常誤以為胰島素是升血糖的」),對教學系統是高價值知識,擋在門外等於
  它永遠進不了圖譜。
- **R3：G2 的 409 後果——比 revision 1 所述輕（已查證）。** 查 Neo4j:seed 的 45 個 approved 節點
  已含 5 個 `PhysiologicalVariable`（血糖／血鈣／滲透壓／血量／子宮收縮強度)與 7 個 `Hormone`,
  故本領域最常見的共用概念一律走**引用**分支,**不會 409**。409 只在「一個 chunk 引進全新概念且被
  兩個全新陳述共用」時發生（例如 `physiological_variable:metabolic_rate`,目前**不在** approved 圖內)。
  屬開拓新領域的首次匯入,非日常。已由 owner 知情接受；T3 文件須明寫觸發條件與處理動作。
- **R4：anchor 型別漂移**——若日後 `_pattern_check` 新增第三種 pattern 而未同步
  `PATTERN_ANCHOR_TYPES`，切分會退化成把它丟進殘餘組。**緩解**：T1 的漂移守衛測試。
- **R5：前端無測試 harness**——T3 只移除一段揭露文字，風險低，但仍需一次瀏覽器確認
  （群組審閱頁能看到 llm 來源群組）。

## Rollback

Revert 上列檔案即可：無 migration、無新依賴、不寫 Neo4j。若已在真實 DB 產生 `proposed_by='llm'`
的群組，以 `DELETE FROM curation_items WHERE proposed_by='llm' AND status='proposed'` 清除
（僅影響待審提案，不影響已核准的知識圖譜；此語句與 `stage_demo_review_groups` 既有的收斂式刪除同型）。

## Human Decisions and Approval

- **revision 2 的三項決定（owner，2026-08-11，已納入本文）：**
  1. **執行模式** → T1 單獨停點；**T2、T3 走 `supervised-auto`**。理由:停點只放在人的判斷能發現
     機器發現不了之事的地方（T1 的陳述邊界是領域判斷；T2／T3 的正確性可機器驗證）。
     同時移除 revision 1「單獨授權 T1 自動化」的思考錯誤。
  2. **R2／R3 知情接受** → 6–8 組／章節維持（殘餘組保留,因含 Misconception）；
     409 接受,但 T3 文件必須明寫觸發條件與處理動作。R3 經查證後嚴重性下修（見 Risks）。
  3. **R1 花 token 觀察** → 採納,新增 **T1.5** 排在 T1 與 T2 之間,作為解鎖 supervised-auto 的前提。
- **Decisions required（尚待）：** 正式批准 revision 2、risk level **medium**、上述混合執行模式,
  以及 T2／T3 的 auto-approved 清單與路徑範圍。
- 上游已定案決策見 `changes/phase-p5-run-2026-08-11/DECISION_READINESS_SUMMARY.md`（G1–G4、I1–I5、DF1–DF2）。
- **Status:** **Approved**
- **Approved plan revision:** **2**
- **Approved risk level and automation mode:** risk **medium**；**混合模式**——T1 單獨停點 →
  T1.5（owner 執行真實抽取觀察）→ T2、T3 `supervised-auto`。
- **Approved by/date:** owner，2026-08-11
- **Approval evidence:** owner 於 session 中明示「批准 revision 2，開始 T1」。
  T2／T3 的 supervised-auto **尚未解鎖**——需先通過 T1 checkpoint 與 T1.5 觀察。
  Material plan changes invalidate approval.
