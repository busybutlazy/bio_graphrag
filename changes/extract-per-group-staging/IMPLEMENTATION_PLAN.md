# Implementation Plan: extract-per-group-staging

## Objective

讓 **LLM 抽取路徑**的產出以「一個生物陳述 = 一個提案群組」的形式進入群組審閱佇列，接上目前斷開的
主線：`文件 → LLM 抽取 → 兩道 gate → 專家審閱 → 寫入知識圖譜`。今日抽取結果以單項寫入且不帶
`group_id`，永遠不會出現在群組審閱頁（`frontend/app.js:928` 對使用者揭露了這個斷點）。

分組規則、去重語意與 chunk 邊界已於 `changes/phase-p5-run-2026-08-11/` 的 grill 會期定案（G1–G3）。

## In Scope

1. `ingestion/pipeline/group_statements.py`（新檔）：**純函式**切分器，把一份
   `{nodes, edges}` 抽取輸出切成數個群組——每個 pattern anchor（`RegulatoryEffect` / `Interaction`）
   一組，殘餘一組。**含巢狀 anchor 規則**（revision 3，T1b）：anchor 節點永不成為另一個 anchor
   群組的成員，只被引用。
2. `backend/app/curation/service.py::approve_group`：新增**邊端點必須存在**的 guard
   （revision 3，T1c）——每條邊的兩端必須是本群組提案的節點或既有 approved 節點，否則 `409`。
3. `ingestion/pipeline/load_postgres.stage_extraction_output`：改為 group-aware——寫入
   `group_id`、item_id 改群組範圍、已 approved 的節點只被引用不重新提案。
4. `ingestion/extract/runner.py`：呼叫點傳入 `chunk_id` 與 approved-id 集合；統計加上群組數。
5. 更新既有抽取測試 + 新增切分器單元測試 + `curation_items` 層級的重跑冪等斷言。
6. 移除 `frontend/app.js` 的「尚未自動組成審閱群組」揭露文字（該限制已解除）；`docs/api_contract.md`
   記載抽取路徑現在也產生群組，並記載 T1c 的新 guard。

## Out of Scope

- **schema-gap backlog 生命週期**（DF1）與 **gold 改打真實抽取輸出**（DF2）——P5 的另外兩個產出，
  已由 owner 決議拆開。
- 任何 `schema/` 型別變更、`extraction_output_schema.json` 或 prompt 變更（G1 選 (c) 正是為了避免）。
- `reject_group` / `record_group_gap` / `create_group` 的任何邏輯變更。
- `approve_group` 除 **T1c 的邊端點 guard** 以外的任何邏輯變更（revision 3 前此處為全面排除；
  選定 B 方案後，該 guard 成為 B 的前提，經 owner 明示納入範圍）。
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

### revision 3 追加證據（T1.5 真實抽取，2026-08-11，11,894 tokens）

- **巢狀 anchor 是真實形態，非假想。** 實際抽出
  `interaction:insulin_glucagon_blood_glucose ─USES_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose`
  ——兩端都是 anchor。revision 2 的切分器把每一端收進對方的組，產生互相包含對方 anchor 的兩組。
- **`back_translation` 已有 P4 拮抗模式**（`back_translation.py:84-103`）：
  `Interaction{antagonism} ─USES_EFFECT→ RE×2, ─ON_VARIABLE→ Var`，且以 `effect_to_hormone`
  **查表**解析效果背後的激素，**不要求那些效果出現在提案內**。renderer 本就是為「交互作用引用效果」
  設計的，這是選 B 的直接證據。
- **P4 排在 P1 之前**（`:84` vs `:106`）：若採 A 方案（交互作用與其效果同組），該組只會渲染拮抗那一句，
  兩個調控效果各自的主張不會被描述——正是 F2 淘汰 chunk 級分組的同一個缺陷。
- **新 guard 對現有資料無回歸風險（實測）**：以 T1c 的規則檢查目前佇列中 7 個群組
  （5 個 demo + 2 個 human），**全部通過**，無懸空端點。
- **`approve_group` 目前沒有端點檢查**：五道防線為 404 / 409 無 proposed / 422 非 create /
  409 gate 未過 / 409 id 已存在（`docs/api_contract.md`），無「邊端點必須存在」。
  `create_group` 在**建立時**有此檢查（dangling endpoint → 422），核准時沒有。

## Acceptance Criteria

1. **切分正確性（G1）：** 對一份含兩個完整 RegulatoryEffect 且**共用**一個
   `PhysiologicalVariable` 的抽取輸出，切分器回傳 **2 個 pattern 組**（各含自己的 anchor、三條邊、
   兩個端點節點），共用節點**同時出現在兩組**；無殘餘時不產生殘餘組。
1b. **巢狀 anchor（T1b）：** 對真實觀察到的 `Interaction ─USES_EFFECT→ RegulatoryEffect` 形態，
   切分結果為兩個**互不包含**的群組：Interaction 組含該邊但**不含**那個 RE 節點（引用）；
   RE 組**不含**該 USES_EFFECT 邊、也不含 Interaction 節點。任一 anchor 都不會出現在另一個
   anchor 的 `nodes` 內。
1c. **端點 guard（T1c）：** 核准一個含「指向尚未核准且不在本組內之節點」的邊的群組 → `409`，
   **Neo4j 完全未被寫入**；錯誤訊息指出缺少的端點與應先核准的對象。
   目前佇列中的 7 個群組（5 demo + 2 human）仍全部可核准（無回歸）。
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
- **Contract 變更（revision 3，需核准點）：** `POST /admin/review/groups/{id}/approve` **新增第六道
  防線**——邊端點不存在 → `409 conflict`。這是**限縮性**變更（fail-closed）:原本會成功並寫出懸空邊
  的請求，現在被拒絕。實測現有 7 個待審群組不受影響。須同步 `docs/api_contract.md` 的四道／五道
  防線表格。
- **Schema/DB：** **無 migration**。`group_id` 欄位已存在（P1 加入，nullable）；本變更只是開始在
  抽取路徑寫入它。
- **資料語意變更（需核准點）：** `curation_items.item_id` 在**抽取路徑**由全域
  `curation:{elem_id}` 改為群組範圍 `curation:{group_id}:{elem_id}`。既有 `llm` 資料為 0 列
  （已查證），故無資料相容問題；但這**移除了跨陳述的全域去重**——同一未核准概念會在多組各自提案，
  此後果已由 owner 於 G2 明示接受。
- **Dependency / Migration：** 無新增依賴、無 migration。

## Execution Policy

- **Plan revision:** 3（Draft）——T1.5 觸發 stop condition 後的修訂。相對 revision 2:
  新增 **T1b**（巢狀 anchor 規則）與 **T1c**（`approve_group` 端點 guard，B 方案的前提,
  owner 明示納入範圍）；`approve_group` 由「全面排除」改為「僅此一項 guard 可動」。
- **Risk level:** **medium**——新增寫入語意與 item_id 方案變更；但無 migration、無依賴、
  不碰 Neo4j、不碰 approve/reject/gate 邏輯，且既有 `llm` 資料為 0 列。
- **Automation mode:** **混合**——T1 為單一任務後停；**T2、T3 為 `supervised-auto`**。
  依據:停點的價值在於「人能發現機器發現不了的事」。T1 之後要判斷的是**一個生物陳述的邊界該畫在哪**,
  那是領域判斷,測試只能驗證我寫的規則有被執行、驗不出規則本身是否符合生物學。T2／T3 的正確性則是
  完全可機器驗證的(測試綠不綠、欄位對不對),停在那裡只會得到「測試過了,繼續」。
  （revision 1 曾提「單獨授權 T1 走 supervised-auto」——那是思考錯誤:T1 是第一個任務,任何模式下
  跑完都會停,授權它自動化省不到任何東西。已移除。）
- **Auto-approved task IDs（`supervised-auto`）：** **T2、T3**。
  **T1b、T1c 不在自動化清單內**——T1b 是被 stop condition 打回來的修正、T1c 動到寫入知識圖譜的
  核准路徑，兩者都需要停點。
- **Approved file/path scope:**
  `ingestion/pipeline/group_statements.py`（新）、`ingestion/pipeline/normalize_concepts.py`、
  `ingestion/pipeline/load_postgres.py`、`ingestion/extract/runner.py`、
  `ingestion/tests/test_group_statements.py`（新）、`ingestion/tests/test_document_ingest.py`、
  `backend/app/curation/service.py`（**僅** `approve_group` 的端點 guard）、
  `backend/tests/unit/test_engineer_gate.py`（僅漂移守衛測試）、
  `backend/tests/integration/test_review_groups.py`（僅新增 guard 測試）、
  `frontend/app.js`、`frontend/index.html`、`docs/api_contract.md`、`changes/extract-per-group-staging/*`
- **Human checkpoints:**
  1. **T1 完成後**——切分規則正確性是整個變更的地基。（**已於 2026-08-11 通過**）
  2. **T1.5 真實抽取觀察之後**——未預期形態即回到 T1。（**已觸發**:巢狀 anchor → T1b）
  3. **T1b 完成後**——巢狀 anchor 的切分結果需 owner 以領域判斷確認。
  4. **T1c 完成後**——動到核准路徑（唯一會寫入知識圖譜的地方），需確認現有群組不受影響。
  通過 4 之後才解鎖 T2／T3 的 supervised-auto。
- **Mandatory stop conditions:** 需要 migration、需要改 `extraction_output_schema` 或 prompt、
  需要改 `engineer_gate`/`back_translation` 任一邏輯、需要改 `approve_group` **端點 guard 以外**的
  任何邏輯、需要新增依賴、切分規則與 grill 定案不符、離線套件出現非本變更造成的失敗、
  **T1c 的 guard 擋到任何現有待審群組**、supervised-auto 期間需要新增任務或路徑。
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

### Task 1b — 巢狀 anchor 規則（checkpoint）

被 T1.5 打回來的修正。**問題**：`Interaction ─USES_EFFECT→ RegulatoryEffect` 兩端都是 anchor，
revision 2 的規則讓兩組互相包含對方的 anchor。

- **Files/symbols:** `ingestion/pipeline/group_statements.py::split_into_statements`；
  `ingestion/tests/test_group_statements.py`。
- **Implementation:** 兩條規則:
  1. **邊的歸屬**——每條邊只屬於一組:恰有一端是 anchor → 歸該 anchor；**兩端都是 anchor → 歸
     `source` 端**（`USES_EFFECT` 的 source 正是 Interaction，與 gate 檢查
     `out(nid,"USES_EFFECT")` 的方向一致）；兩端皆非 anchor → 殘餘。
  2. **節點的歸屬**——一個 anchor 群組含該 anchor 與其邊上**非 anchor** 的端點節點；
     另一端若也是 anchor 則**只引用不納入**（P4 的 `effect_to_hormone` 查表本就支援引用）。
- **Tests:** 新增 (g) 巢狀 anchor:Interaction 組含 `USES_EFFECT` 但不含 RE 節點,RE 組不含該邊
  也不含 Interaction 節點；(h) 以 T1.5 的真實 payload 為 fixture 的回歸測試,斷言切出 5 組且
  無任何 anchor 出現在別組的 `nodes` 內。
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests/test_group_statements.py -q
  ```
- **Stop/handoff:** 把切分結果攤給 owner 判斷後停。

### Task 1c — `approve_group` 邊端點 guard（checkpoint）

B 方案的前提。交互作用群組引用其他組的效果,若先核准交互作用組,會寫出**懸空的邊**。

- **Files/symbols:** `backend/app/curation/service.py::approve_group`（**僅**新增此 guard）；
  `backend/tests/integration/test_review_groups.py`。
- **Implementation:** 在既有 gate guard 之後、寫入 Neo4j 之前:蒐集所有提案邊的端點,扣掉本群組
  提案的節點,剩餘者以既有 `_existing_approved_ids` 查詢；若有任何端點既不在組內也非 approved →
  `CurationError(409, ...)`,訊息列出缺少的端點。**沿用既有 helper,不新增查詢機制。**
- **Tests:** (a) 引用尚未核准節點的群組 → 409 且 Neo4j 未被寫入；
  (b) 該端點先被核准後,同一組即可成功核准（順序依賴可解）；
  (c) 回歸:現有 demo／human 群組仍可核准（已預先實測 7/7 通過）。
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_review_groups.py tests/api/test_review.py -q
  ```
- **Stop/handoff:** 完成後停,確認無回歸後才解鎖 T2／T3。

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

- **R1 — 已實現並已處置（revision 3）。** T1.5 確實抓到未預期形態（巢狀 anchor），證明這個
  checkpoint 有價值:0.2 美分買到一個單元測試想不到、但真實 LLM 第一次就產出的形態。
  處置為 T1b。**殘餘風險**:仍只觀察過兩章／兩次呼叫,更多語料可能有更多形態；T1b 的規則以
  「邊只屬於一組、anchor 不互相納入」為通則,不針對特定型別,對新形態的耐受度優於 revision 2。
- **R6（新，revision 3）：審閱順序依賴。** 選 B 之後,交互作用群組必須在它引用的效果群組**之後**
  核准,否則 T1c 的 guard 會回 409。這是刻意的——「這兩個效果拮抗」在邏輯上預設兩個效果成立。
  **代價**:專家若不照順序點,會撞到 409。**緩解**:錯誤訊息必須指出缺少哪個端點；
  審閱佇列的排序讓 pattern 組排在交互作用組之前（T2 的群組順序已依 anchor id 排序,
  此點在 T3 的瀏覽器確認時觀察是否足夠直覺,不足則記入 backlog,不在本次擴大範圍）。
- **R7（新，revision 3）：抽取語意品質低。** T1.5 實測 5 組中 4 組 `fail_pattern`——LLM 把
  `HAS_EFFECT` 用成 `RegulatoryEffect → PhysiologicalVariable`（該位置應為 `ON_VARIABLE`）,
  且未提案任何 `Hormone`、無方向邊。**本次範圍外**（屬 prompt/profile 議題,見 backlog N2）,
  但意味著主線接通後**初期通過率會很低**。這不是本變更的缺陷,但驗收時不得把「群組都 fail_pattern」
  誤判為分組錯誤。
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
### revision 3 的決定（owner，2026-08-11）

- **巢狀 anchor → 選 B**（三個獨立審閱單位，交互作用只引用效果）。理由:A 會讓一組同時含
  Interaction 與其 RE,而 P4 排在 P1 之前,該組只渲染拮抗那一句,兩個效果的主張不會被描述——
  正是本變更存在的理由（F2）在另一處復發。B 另有粒度優勢:可核准正確的效果、單獨退回錯的那個。
- **T1c 納入範圍**（`approve_group` 端點 guard）。這是 B 的前提,且該防護缺口本來就存在——
  任何群組核准都不該寫出懸空的邊,與抽取路徑無關。
- 發現二（抽取語意品質,prompt/profile）與發現三（Structured Outputs + 逐元素失敗）**不納入本次**,
  排入後續 change（N1／N2）。owner 確認 Structured Outputs 目前**未**使用
  （`llm_client.py:47` 僅 `response_format={"type":"json_object"}`）。

### revision 4（2026-08-11）——獨立審查後的重新設計

獨立審查（`REVIEW_REPORT.md`）的 B1／H2 顯示切分規則只對齊 `engineer_gate`、未對齊
`back_translation`;第二輪 grill（`DECISION_INVENTORY_R2.md`）另發現 **P3 也被切壞**,四個 pattern
壞了兩個。決議（owner，2026-08-11）:

- **G5** 切分改**模板法**:在 `ingestion` 宣告 pattern 模板（收斂點型別 + 必要邊型別與方向），
  依 renderer 優先序 P2 → P4 → P1 貪婪匹配;**不改 `back_translation`**。
  一致性靠兩個行為守衛:每個模板的最小實例必須渲染出對應 pattern;**殘餘組永不得渲染出 pattern 句**。
- **G6** 殘餘邊連同端點一起納入（懸空從結構上消失;共用節點重複提案是 G2 已接受的語意）。
- **G7** P3 不是切分單位（機制與效果分開審）→ 須記載「P3 在抽取路徑不會觸發」。
- **I7** 一併修審查的 M1／M3／M4／L1／L3／S1／S2。
- **新增決定（實作時定義）**:模板未匹配的 anchor **仍自成一組**（保留現行行為,讓 gate 判
  `fail_pattern`),而非混進殘餘——否則不完整的調控效果會被靜默稀釋成 P0。

範圍新增檔案:`ingestion/pipeline/group_statements.py`（重寫）。`approve_group` 僅動 docstring（L1）。
**不含**:抽取語意品質（N1／N2）、backlog 生命週期（DF1）、`back_translation` 任何改動。

### revision 5（2026-08-11）——補批准:核准語意變更超出 revision 4 的範圍

**這是一次補救性的修訂。實作先於批准發生,獨立審查（W1）指出,此處如實記錄。**

revision 4 白紙黑字寫「`approve_group` **僅動 docstring**」。實際做的是變更它的**核准語意**:
「成員已存在於 approved 圖 → 整組 409」改為「沿用不重寫」。這同時推翻了
`DECISION_INVENTORY_R2.md` 的 **G6** ——當時把「共用節點撞第四道防線」定性為
「G2 已接受的語意（退回重提)」。

**為什麼推翻**:第二輪審查（V1）實測顯示該定性低估了頻率——不是偶發,而是一個普通血糖 chunk 切出
三組、共用「胰島素」與「血糖」,**核准第一組後其餘組全部 409**,審閱者一段課文最多只能核准一個陳述。
根因是那道防線把「節點重用」誤當成「覆蓋策展知識」;圖層的 `MERGE` 本來就冪等,真正的覆蓋風險在
`write_nodes` 的 `SET n.label/.description`。

**Contract 影響（需 owner 批准的部分)**:
- `POST /admin/review/groups/{id}/approve` **移除**一道 409（成員已存在於 approved 圖)
- **新增**一道 409（成員重新提出 `deprecated` 的知識——見下)
- 回應**新增** `reused_nodes` / `reused_edges` 兩個欄位（加欄位,既有欄位語意不變:`nodes`/`edges`
  仍是實際寫入數)
- `docs/api_contract.md` 已同步（W1)

**同時修正的既有缺陷（W2)**:`_existing_approved_ids` 只看 `approved`,而 `delete_node` 是把節點留在
圖上設為 `deprecated`。因此一個被策展者刪除的概念會落入寫入清單,`MERGE … SET` 把它改回 `approved`
並覆寫文字——**無聲撤銷刪除決定**。已實測複現,並新增一道 409 擋下。此缺陷在舊防線下同樣存在
（舊查詢也只看 approved),但本次改動的正當性正是「策展版本永遠優先」,不修則該宣稱不成立。

**已知治理成本（W3，如實揭露）**:審閱者在核准的當下看到的理解句由**提案的** label 渲染,而圖上留下
的是策展版本;哪些成員被沿用只能事後查稽核紀錄。舊行為在這個情境是 409（強迫當場做明示決定),
新行為是靜默沿用。這是本次修法真實的取捨,已記入 `api_contract.md` 的已知限制。

- **Status:** **Approved**
- **Approved plan revision:** **5**（owner，2026-08-11:「三項都批准」)
- **revision 5 補批准的三項 Contract 變更**（owner 逐項確認後批准）:
  1. **移除**「成員已存在於 approved 圖 → 409」,改為沿用不重寫。放寬核准條件、同時收緊寫入保護:
     策展內容從此不會被提案覆寫。**已知代價**:不再強迫審閱者當場面對「這個概念已存在」——見 W3。
  2. **新增**「重新提出 `deprecated` 的知識 → 409」。範圍比它取代的那道窄得多,只擋被明確刪除過的
     成員。**已知缺口**:系統沒有「復原」動作,被擋下時只能退回該組,真正復原需直接改資料庫。
     是否補復原功能列為後續決定。
  3. 回應**新增** `reused_nodes` / `reused_edges`。純加法,但**既有欄位 `nodes`/`edges` 的值會變**——
     它們現在是「實際寫入數」而非群組成員數,與本路徑其他統計的語意一致。前端 flash 已同步說明。
- **流程偏差紀錄（不因批准而消失）**:實作先於批准發生。revision 4 的範圍寫「僅動 docstring」,
  實際變更了核准語意並推翻 `DECISION_INVENTORY_R2.md` 的 G6;CLAUDE.md 的
  「必須改變已批准的 Contract」stop condition 當時未觸發。由獨立審查（W1）指出後補正。
- **Approved risk level and automation mode:** risk **medium**；**混合模式**——T1 單獨停點 →
  T1.5（owner 執行真實抽取觀察）→ T2、T3 `supervised-auto`。
- **Approved by/date:** owner，2026-08-11
- **Approval evidence:** owner 於 session 中明示「批准 revision 2，開始 T1」。
  T2／T3 的 supervised-auto **尚未解鎖**——需先通過 T1 checkpoint 與 T1.5 觀察。
  Material plan changes invalidate approval.
