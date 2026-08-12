# Verification Report: extraction-prompt-inline-pattern-rules

補寫說明：本變更未依流程先產 IMPLEMENTATION_PLAN，驗證證據原本只存在 commit message
與對話中（REVIEW_REPORT M3 的指摘成立）。本檔補記當時實際執行的命令與數據，未執行過的
項目一律標示為未執行，不回填推測值。

## 1. 環境與姿態

- 全部在 Docker 內執行，host 未安裝任何套件。
- 抽取模型 `gpt-4o-mini`（`ingestion/extract/llm_client.py:EXTRACTION_MODEL`），
  `response_format={"type": "json_object"}`，未設 `max_tokens`。
- `runner._extract_chunk(retries=1)`：每個 chunk 最多兩次呼叫，第二次會把上一次的
  驗證錯誤原文附回 user prompt 要求修正。下列「失敗 chunk」都是**重試後仍失敗**。
- 輸入章節 `data/private/chapters/endocrine_demo_v1.md`（gitignored，帶
  `extraction_profile: endocrine_v1`，故 system prompt = base + 私有 profile overlay）。
  審查者無法取得此輸入，本節數據不可獨立複驗；可複驗的部分是命令與程式行為。

## 2. 抽取前後對照（三次真實抽取）

命令（`INGEST_OWNER_SECRET` 取自 `.env`）：

```bash
curl -s -X POST localhost:8080/admin/ingest/run \
  -H 'Content-Type: application/json' \
  -H "X-Ingest-Owner-Token: $TOKEN" \
  -d '{"source":"data/private/chapters/endocrine_demo_v1.md","strategy":"markdown_header"}'
```

每次抽取前都 `docker compose up -d backend` 重啟，因為 `build_extraction_prompt`
以 `lru_cache(maxsize=1)` 快取模板，`prompts/` 雖掛 volume，跑著的 uvicorn 進程不會重讀。

| 次序 | 當時的 prompt 狀態 | chunks | failed_chunks | tokens | 失敗原因 |
|---|---|---|---|---|---|
| 基線 | 修改前（交接記錄） | — | — | — | 抽取語意錯誤：四條邊全部 `RegulatoryEffect ─HAS_EFFECT→ PhysiologicalVariable`；無 Hormone 節點、無方向邊。所有 LLM 群組 `fail_pattern` |
| 1 | +rules 7/8/9（方向與三段式） | 4 | 3 | 24304 | 全部為 `'id' is a required property` |
| 2 | +rule 6 內聯輸出形狀 | 4 | 3 | 24024 | 同上 |
| 3 | +user prompt 末尾逐條檢查 | 4 | 2（chunk 001、002） | 20808 | 同上 |

### 2.1 語意面：已修正（直接證據）

第 1 次抽取起，失敗 chunk 的錯誤 payload 中即可觀察到目標結構，例如：

```
{'source': 'regulatory_effect:adh_increases_blood_volume',
 'target': 'physiological_variable:blood_volume',
 'type': 'ON_VARIABLE', ...}
```

即 `RegulatoryEffect ─ON_VARIABLE→ PhysiologicalVariable`，正是規則 7 要求的位置；
基線的 `HAS_EFFECT` 誤用未再出現。節點 id 亦改用 `regulatory_effect:` / `hormone:` 前綴。

### 2.2 Gate 面：出現 pass，但通過的不是調控陳述

第 3 次抽取後查詢 `GET /admin/review/groups`：

- LLM 群組 2 組，`schema_gate.result` 皆為 `pass`（基線為全部 `fail_pattern`）。
- **但兩組都是 residual 概念群組**（`chunk:000` / `chunk:003`），
  例如 `concept:homeostasis`、`system:endocrine_system`、`molecule:hormone`，`proposed_edges: []`。
- 真正的調控段落（chunk 001 血糖、002 ADH）整段被丟棄，未進入佇列。

**因此「fail_pattern → pass」成立，但不等於調控三段式已通過 gate。**
REVIEW_REPORT M3 要求排除的替代解釋（P2 語句被包成形式合格的 P1 而推高 pass 率）
在本次數據中不成立：pass 的兩組完全沒有邊，不含任何 pattern。

### 2.3 未解的阻斷點（歸因證據）

三次都失敗的 chunk，每次都只有**一條** edge 不合格，且發生在輸出靠後的位置：

| chunk | 失敗的 edge |
|---|---|
| 000 | `system:endocrine_system → concept:homeostasis`，`type: REGULATES_SECRETION_OF`，缺 `id` |
| 001 | `regulatory_effect:insulin_... → regulatory_effect:glucagon_...`，欄位寫成 `relationship`，缺 `id` |
| 002 | `regulatory_effect:adh_... → physiological_variable:blood_osmolarity`，欄位寫成 `relationship`，缺 `id` |

排除 truncation：`llm_client` 未設 `max_tokens`，且輸出為合法 JSON 僅缺 key。
排除 prompt 措辭不足：要求已同時出現在 system prompt（rule 6，含最小 JSON 範例）、
user prompt 末行（recency 最高），以及重試時附回的錯誤原文；失敗 chunk 仍只從 3 降到 2。

**結論：prompt 層已到頂，`json_schema` + `strict`（backlog #1）是這條路徑的 binding constraint。**

## 3. 自動化測試

```bash
docker compose build backend      # 測試檔未掛 volume,不重建會跑到舊測試
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
```

- 修補前：**200 passed**。
- 補上 REVIEW_REPORT H1/H2/M1/L3 修補與 S1 守衛測試後：**202 passed**（新增 2 項）。

`test_qdrant_payload_is_queryable` 的歸因更正見 REVIEW_REPORT 附錄。

### 3.1 新增守衛的有效性（對照驗證）

S1 守衛 `test_base_prompt_covers_every_rule_card_signature` 會先剝除規則 2 的型別白名單
再比對，因為白名單只是一串沒有方向資訊的名字——原始 bug 本身。實測把守衛套在
修補前的 prompt（`git show HEAD:prompts/graph_extraction_prompt.md`）上：

```
守衛套在修補前的 prompt 上會判定缺少: ['SECRETES', 'REGULATES_SECRETION_OF']
```

即該守衛確實會在當初擋下 H1（P2 分泌觸發缺席），非事後裝飾。

## 4. 未執行 / 未驗證

- **H1/H2/M1/L3 修補後未再跑真實抽取**：本輪修補（新增 P2 規則、`interaction_type`、
  RegulatoryEffect 成立條件、佔位符措辭）只經過離線測試與模板組裝驗證，
  **沒有**付費抽取證據。合併前建議補一次，重點看 P2 語句是否不再被包成 RegulatoryEffect。
- `make eval`（22 題黃金題）未執行。本變更不觸及 retrieval 路徑。
- 非 `gpt-4o-mini` 模型、非 `markdown_header` 切塊策略下的表現未評估。

## 5. 一個會誤導後續驗證的環境事實

抽取產生的 staging 列會被測試清掉：integration 測試會清 `curation_items`，
本次就是這樣把兩組已通過 gate 的 LLM 群組洗掉的。**跑完真實抽取後不要再跑 `make test`**，
否則佇列會空掉並看似抽取失敗。
