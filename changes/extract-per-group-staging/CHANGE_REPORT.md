# Change Report: extract-per-group-staging

分支 `feat/extract-per-group-staging`,基於 `main` @ `0a3e5be`。計畫 **revision 3**（owner 批准
2026-08-11)。執行順序:T1 → T1.5（owner 線上執行)→ T1b → T1c → T2 → T3。

## Completed

接通了本專案敘事的主線:**文件 → LLM 抽取 → 兩道 gate → 專家審閱 → 寫入知識圖譜**。
在此之前,抽取結果以單項寫入且不帶 `group_id`,群組審閱頁**永遠看不到**——收錄頁自己掛著揭露文字
承認這個斷點。

- **切分器**(`ingestion/pipeline/group_statements.py`,新):把一份抽取輸出切成「一個生物陳述一組」。
  每個 `RegulatoryEffect` / `Interaction`（`PATTERN_ANCHOR_TYPES`)連同其邊與端點自成一組;
  其餘每 chunk 歸為一個 residual 組。純函式、不 import backend（維持 ingestion 不依賴 backend 的
  單向規則),只共用 anchor 型別常數,並以行為探測式**漂移守衛**釘住它與 `_pattern_check` 的一致。
- **巢狀 anchor 規則**:每條邊只屬於一組（兩端都是 anchor 時歸 source);anchor 只被引用、
  不被另一個 anchor 吸收。
- **staging**(`load_postgres.stage_extraction_output`):逐組寫入,`item_id` 改群組範圍,
  `group_id` 由 chunk + anchor 推導(確定性,重跑冪等的前提);已 approved 的節點只被引用不重新提案。
- **`approve_group` 第六道防線**:邊端點既不在組內也非 approved → `409`;空端點 → `422`。
- **文件與前端**:`api_contract.md` 記載三種群組來源、抽取端切分規則、`stats.proposed_groups`
  與新防線;收錄頁的斷點揭露文字改述為現行行為。

## Deviations from the approved plan

1. **T1.5 觸發 stop condition（計畫預期的機制生效)。** 真實抽取產出
   `Interaction ─USES_EFFECT→ RegulatoryEffect`,兩端都是 anchor,revision 2 的規則讓兩組互相
   包含對方。依計畫停止 T2、回到 T1,產生 **T1b**。0.2 美分買到一個六個單元測試都想不到的形態。
2. **範圍擴大:T1c（owner 明示批准,revision 3)。** 選 B（交互作用引用效果而非包含)需要
   「邊端點必須存在」的保證,而 `approve_group` 原本沒有。`approve_group` 由計畫的「全面排除」
   改為「僅此一項 guard 可動」。
3. **`ingest_document` 新增 `approved_ids` 參數**(計畫僅指定 staging 層注入)。原因:既有抽取測試
   不帶 neo4j fixture,不開放注入就無法離線覆蓋引用分支。與該模組自陳的 "injectable resources"
   風格一致。
4. **修了 `_cleanup` 缺少的 `curation_items` 清除**(計畫未列)。這是既有 flake 的成因之一,
   且不修的話 T2 的冪等測試會互相污染。

## Data cleanup（owner 批准）

T1.5 留下的殘留使 `test_pipeline_run_is_idempotent` 持續失敗。清除:
`doc:private:endocrine_demo_v1`、**`doc:sample:hormone_regulation_demo`**（`demo.md` 那次
**抽取失敗但仍寫入 document 列**——這是真正多出來的那一筆,不在 seed 來源中)、9 筆未分組 llm items,
以及對應的 Qdrant 向量。`ingestion_jobs` 稽核列**保留**。清除後套件全綠,證實該失敗純屬資料殘留。

## Not completed / deliberately excluded

- **抽取語意品質**（T1.5 發現二):真實抽取把 `HAS_EFFECT` 用成 `RegulatoryEffect → PhysiologicalVariable`
  （該位置應為 `ON_VARIABLE`),且未提案任何 `Hormone`、無方向邊 → 5 組中 4 組 `fail_pattern`。
  **主線接通後初期通過率會很低,這不是分組錯誤。** 屬 prompt/profile 議題,排入後續 change（N2)。
- **Structured Outputs**（T1.5 發現三):`llm_client.py` 目前只用 `response_format={"type":"json_object"}`
  （保證合法 JSON,不保證 schema),故一條缺 `id` 的邊會讓整個 chunk 的抽取結果被丟棄。
  修法明確（改用 `json_schema` + `strict`,並改為逐元素失敗),排入後續 change（N1),
  **建議排在下一次真實抽取之前**。
- **schema-gap backlog 生命週期**(DF1)與 **gold 改打真實抽取輸出**(DF2)——P5 的另外兩個產出。
- **本次交付不使 roadmap 的 P5 完成**:P5 三個產出中只交付第三個。Roadmap 完成狀態不得因此變更。

## Known consequences（owner 已知情接受）

- **審閱順序依賴**:交互作用群組必須在它引用的效果群組之後核准,否則 `409`。這是刻意的——
  「這兩個效果拮抗」在邏輯上預設兩個效果成立。錯誤訊息會指出缺少的端點與應先核准的對象。
- **審閱負載**:一個 chunk 通常產生數個群組（實測 1 chunk → 2–5 組)。細粒度是設計目的。
- **殘餘組的敘述品質**:殘餘組一律走 P0 plain summary（「……但不屬於任何已知的調控模式;
  請就內容本身審查。」),owner 已指出這句不好懂。**與抽取無關、今日既有**,排入後續 change（N3)。

## Verification summary

離線 **186 passed**;`app.eval.runner` Overall **PASS**;ruff + mypy 全清;`node --check` OK。
端到端離線抽取 → 2 個群組出現在 `list_groups()`,完整三段式那組 `gate: pass` 且句子描述自己的陳述。
兩處反向驗證（漂移守衛、端點 guard)證明測試會真的失敗。**瀏覽器確認 owed**。
詳見 `VERIFICATION_REPORT.md`。
