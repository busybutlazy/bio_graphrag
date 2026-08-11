# Task Log — extract-per-group-staging

分支 `feat/extract-per-group-staging`，基於 `main` @ `0a3e5be`。計畫 revision 2（owner 批准 2026-08-11）。

## Task 1 — 切分器  ✅

| 檔案 | 內容 |
|---|---|
| `ingestion/pipeline/normalize_concepts.py` | `PATTERN_ANCHOR_TYPES = {"RegulatoryEffect", "Interaction"}` |
| `ingestion/pipeline/group_statements.py`（新） | `split_into_statements(candidate, chunk_id)` 純函式 |
| `ingestion/tests/test_group_statements.py`（新） | 6 個單元測試 |
| `backend/tests/unit/test_engineer_gate.py` | 漂移守衛（+1） |

設計要點：切分只需要 anchor 型別與相連關係，**不需要複製 `_pattern_check` 的完整性規則**——群組 =
anchor + 所有相連邊 + 邊另一端的節點。因此 `ingestion` 不必 import `backend`（單向依賴維持）。
`group_id = group:llm:{chunk_id}:{anchor_id}` 為確定性命名，這是重跑冪等的前提。

**刻意不做的事**：不完整的 pattern 仍會成組。切分不是驗證——讓它成組，Schema gate 才判得出
`fail_pattern` 讓專家退回；在此濾掉等於把有問題的提案藏起來。

漂移守衛經反向驗證：把 `PATTERN_ANCHOR_TYPES` 暫時改為只剩 `RegulatoryEffect`，測試立即失敗
（`gate=['Interaction','RegulatoryEffect'] splitter=['RegulatoryEffect']`），改回後通過。

**Checkpoint 通過**（owner，2026-08-11）：以模擬語料（兩個調控效果 + 一段解剖關係）展示切分前後，
owner 認可第一、二組的切分。切分前整個 chunk 一組時，專家只會讀到「胰島素會造成一個調控效果:使血糖
下降。」——升糖素與解剖關係全部不在描述裡卻會一起被核准；切分後三組各有正確敘述。

驗證：`pytest tests ingestion/tests` 離線 → **178 passed**（baseline 171 + 7）；ruff + mypy 全清。

## Task 1.5 — 真實抽取觀察（owner 執行）  ⚠ 觸發 stop condition

`gpt-4o-mini`，兩份章節共 **11,894 tokens**（約 0.2 美分，低於計畫估的 1 美分）。
兩次皆用預設 `recursive` 切塊（chunk_size=500）→ 整章 1 個 chunk。

### 觀察結果對照計畫的四個問題

| 問題 | 結果 |
|---|---|
| 1. 一個 RE 是否連到兩個以上變數？ | 否（每個 RE 只有 1 條邊） |
| 2. 是否出現兩個 anchor 共用同一批邊？ | **是——且是巢狀 anchor，計畫未涵蓋（見下）** |
| 3. 產出規模與殘餘比例 | 1 chunk → 5 節點 4 邊 → 切成 **5 組**（4 pattern + 1 殘餘）。與 I2 的 6–8 組估計同量級 |
| 4. 是否重複提出既有概念？ | **否**——LLM 完全沒有提案 `Hormone` / `PhysiologicalVariable`，邊直接指向既有 approved 節點。`existing_concepts` 提示有效，G2 的引用分支在 LLM 端就已部分發生 |

### 發現一（STOP）— 巢狀 anchor

```
interaction:insulin_glucagon_blood_glucose ─USES_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose
```

兩端都是 anchor。現行切分器把每一端收進對方的組，產生**互相包含對方 anchor** 的兩組；
兩組都提案同一節點，核准第一組後第二組必然 409。

依計畫 T1.5 判準「出現未預期形態 → 停止，回到 T1 修改切分器」，**T2／T3 的 supervised-auto 未解鎖**。

### 發現二（範圍外）— 抽取語意品質

真實抽出的 4 條邊全部是 `HAS_EFFECT`，方向為 `RegulatoryEffect → PhysiologicalVariable`；
依 schema 該位置應為 `ON_VARIABLE`（`HAS_EFFECT` 是 `Hormone → RegulatoryEffect`）。
完全沒有 `Hormone` 節點、`ON_VARIABLE`、`INCREASES`/`DECREASES`。
→ 5 組中 4 組 `fail_pattern`。**schema 驗證通過但語意錯誤**——型別都在白名單內，用法錯了。

### 發現三（範圍外）— 一條壞邊毀掉整個 chunk

`demo.md`：`edges[5]` 缺 `id` → `ValidationError` → **整個 chunk 丟棄**（0 節點 0 邊）。
搭配 `recursive` 切塊（整章 1 chunk），一條壞邊等於整章報銷。
根因在生成端：`llm_client.py:47` 用的是 `response_format={"type":"json_object"}`（僅保證合法 JSON），
而非 OpenAI Structured Outputs（`json_schema` + `strict`，可保證欄位齊全）。

## Task 1b — 巢狀 anchor 規則  ✅（checkpoint 通過）

兩條通則取代 revision 2 的「anchor + 所有相連邊」:

1. **邊的歸屬**——一端是 anchor → 歸該 anchor;**兩端都是 → 歸 source**;都不是 → 殘餘。
   `USES_EFFECT` 的 source 是 Interaction、`HAS_EFFECT` 的檢查掛在 RE 的入邊,兩者的歸屬都落在
   gate 查找 pattern 的那一端。
2. **anchor 不互相吸收**——另一端若也是 anchor,只被邊引用,不納入 `nodes`。

以結構正確的拮抗資料驗證(owner 已確認):三組、三句、各自描述自己的主張。
T1.5 的真實 payload 存成 fixture（連同 LLM 用錯的 `HAS_EFFECT` 原樣保留)作回歸測試。

## Task 1c — `approve_group` 邊端點 guard  ✅（checkpoint 通過）

第六道防線:端點既不在組內也非 approved → `409`（訊息列出缺少者並指示先核准提案它們的那組);
空端點 → `422`（與 `create_group` 提案時的判定一致)。沿用既有 `_existing_approved_ids`。

反向驗證:把判斷改成 `if False and missing:` 後測試失敗,且該次執行真的把 anchor 寫進 Neo4j
（製造出懸空的邊)——證明 guard 擋下的是真實會發生的資料損壞。殘留節點已清除,並加入
`_NODE_IDS` teardown。

無回歸:實測佇列中 7 個群組（5 demo + 2 human）在新 guard 下全部通過。

### 中途的資料清理（owner 批准）

T1.5 留下兩項殘留使 `test_pipeline_run_is_idempotent` 持續失敗:
`doc:private:endocrine_demo_v1`,以及 **`demo.md` 那次抽取失敗仍寫入的 `doc:sample:hormone_regulation_demo`**
（後者不在 seed 來源中,是真正的多餘列)。連同 9 筆未分組 llm items 與對應的 Qdrant 向量一併清除,
`ingestion_jobs` 稽核列保留。清除後套件全綠——證實該失敗純粹是資料殘留。

## Task 2 — group-aware staging  ✅（supervised-auto）

- `stage_extraction_output(conn, candidate, chunk_id, approved_ids)` → 回傳新增 `staged_groups`。
  逐組寫入、`item_id = curation:{group_id}:{elem_id}`、`group_id` 入欄。
  **`approved_ids` 以參數注入**（非在函式內查 Neo4j),讓離線測試無需 Neo4j 即可覆蓋引用分支。
- `runner.py`:新增 `_fetch_approved_ids(driver)`（只取 `status='approved'`,與供 prompt 用的
  `_fetch_existing_concepts` 區分——後者含 proposed);`ingest_document` 新增可注入的
  `approved_ids` 參數;統計新增 `proposed_groups`。
- 測試:群組進入審閱佇列（**直接呼叫 `service.list_groups()`**,因為只驗 `curation_items`
  證明不了佇列看得到)、重跑冪等（列數與群組數皆不增、第二次回報 0）、approved 節點只引用不提案。
- `_cleanup` 補上 `DELETE FROM curation_items WHERE proposed_by='llm'`——原本缺這行,
  正是既有 flake 的成因之一。

## Task 3 — 文件與前端  ✅（supervised-auto）

- `frontend/app.js`:移除「尚未自動組成審閱群組……僅能經 API 存取」的揭露文字,改述現行行為;
  `?v=20260811-1`。
- `docs/api_contract.md`:新增群組三來源對照表（demo／human／llm 的 `group_id` 形態）、
  抽取端切分規則與確定性命名、`stats.proposed_groups`;核准防線表新增第六道與空端點 422,
  並說明「順序與格式的分工」。

## 獨立審查後的重做（revision 4，2026-08-11）

`REVIEW_REPORT.md` 的 B1／H2 顯示切分只對齊 `engineer_gate`、未對齊 `back_translation`;
第二輪 grill（`DECISION_INVENTORY_R2.md`）另查出 **P3 也被切壞**——四個 pattern 壞了兩個。

**切分器改為模板法**:宣告式寫出 P2／P4／P1 的形狀,依 renderer 優先序貪婪匹配;未匹配的 anchor
仍自成一組（讓 gate 判 `fail_pattern`,不被稀釋進殘餘);殘餘邊連同端點納入（懸空從結構上消失)。

## 第二輪審查（V1–V5）與第一層修正

複審再找出兩個 High,兩者都經實跑複現:

- **V1**:節點跨組重複提案 → 核准第一組後,其餘組撞「成員已存在於已核准圖譜」→ **一個 chunk 最多
  只能核准一組**。實跑證實:第一組 approved,第二組 409。
- **V2**:模板收下所有同型邊,但 renderer 只描述第一條 → 兩個激素指向同一效果時,第二個主張
  無聲搭便車。

**根因不在切分,在核准語意。** 圖層的 `MERGE` 本來就是冪等的——一個節點掛多條關係是圖最基本的行為;
是核准防線把「節點重用」當成「覆蓋策展知識」在擋。真正的風險在 `write_nodes` 的
`SET n.label/.description`（無條件覆蓋),不在 MERGE。

修法:**已存在於已核准圖譜的成員改為沿用而非重寫**。實跑:兩組都核准成功,圖上一個胰島素節點掛
兩條關係;第二組回報 `reused_nodes: 1`,沿用的 id 記入稽核 `after_state.reused_nodes`。
比原本更安全——原本擋得住整組核准,但一旦核准就照樣覆蓋 label/description;現在策展版本永遠優先。
測試直接斷言:預寫 label 為 `pre-existing` 的節點,核准後仍是 `pre-existing`。

V2 修法:模板只取 renderer 會讀到的邊數,多的落入殘餘並被誠實列出（gate 標 `fail_pattern`)。

其餘:V3（守衛宣稱不實)見下;V4 補模板優先序測試;V5 teardown 改 `starts_with` 避開 `_` 萬用字元。

### 守衛的更正（V3）

原先兩個守衛的輸入全是手寫實例,**一個既沒模板也沒實例的新句型不會觸發任何失敗**——與當初漏掉 P2
是同一種盲區。新增第三個守衛,以 `inspect.getsource` 從 `back_translation` 列舉可回傳的 pattern id,
要求每一個不是被模板涵蓋就是列入「刻意不涵蓋」清單並附理由（目前只有 P3)。
反向驗證:移除 P3 的豁免紀錄後該守衛失敗。

## 第三輪審查（W1–W6）

- **W1（Blocking，流程）**:核准語意變更**超出 revision 4 的批准範圍**（該版寫「僅動 docstring」），
  且推翻了被記錄為「已接受」的 G6，未觸發 CLAUDE.md 的 Contract stop condition。
  契約文件同時載著一條**已不存在**的 409、缺 `reused_*` 欄位、標題「四道防線」而表內七列。
  處置:文件已同步;計畫補 **revision 5** 並如實記錄流程偏差;三項 Contract 變更經 owner 逐項確認後
  批准（2026-08-11）。偏差紀錄不因批准而移除。
- **W2（Medium，且比審查描述更嚴重）**:實測顯示不只覆寫文字,而是**讓刪除決定無聲失效**——
  `delete_node` 是軟刪除（留在圖上設 `deprecated`），而沿用判斷只看 `approved`,於是被刪除的概念
  會被 `MERGE … SET` 改回 `approved` 並覆寫。修法:新增一道針對 `deprecated` 的 409。
  已反向驗證（修正前復活、修正後 409 且刪除決定完好）。**已知缺口**:系統沒有「復原」動作。
- **W3（Medium）**:審閱者在核准當下看到的理解句由**提案的** label 渲染,圖上留下的是策展版本;
  沿用了哪些成員只能事後查稽核。舊行為在此情境是 409（強迫當場明示決定）。
  已記入 `api_contract.md` 的「已知限制」與 revision 5。
- **W4**:前端 flash 補上沿用成員的說明（`?v=20260811-2`）。
- **W5**:補「兩組共用概念都能核准」的實際測試,斷言圖上一個節點掛兩條關係。
- **W6**:列舉守衛加下限斷言——抓不到足夠 pattern id 即失敗,避免 renderer 改寫格式後守衛靜默失效。

### 附帶確認

抽取產生的 9 列 `curation_items` 全部 `group_id IS NULL`，未出現在群組審閱佇列——
這是 T2 之前的預期行為，非資料遺失（owner 一度以為靜默消失）。
