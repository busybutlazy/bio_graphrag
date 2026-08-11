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

### 附帶確認

抽取產生的 9 列 `curation_items` 全部 `group_id IS NULL`，未出現在群組審閱佇列——
這是 T2 之前的預期行為，非資料遺失（owner 一度以為靜默消失）。
