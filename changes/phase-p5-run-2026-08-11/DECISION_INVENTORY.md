# Decision Inventory

## Scope

抽取路徑（`ingestion/extract/runner.py` → `load_postgres.stage_extraction_output`）的 **per-group
staging**：讓 LLM 抽取結果進入群組審閱佇列。範圍限定 G1–G3 及 P5 的 phase 邊界；不含 schema-gap
backlog 生命週期（已拆出）。

會期日期：2026-08-11。Repo：`main` @ `0a3e5be`，工作區乾淨。

## Decision Dependency Map

```
G4 (P5 邊界拆分) ──> 決定本次 scope
        │
G1 (分組規則) ──┬──> I1 (group_id 命名/冪等)
                ├──> I2 (殘餘組規則)
                └──> G2 (item_id 去重) ──> I3 (approved 判定時機)
G3 (跨 chunk)  ──> 確認 runner 迴圈結構不動
```

## Decisions

### F1 — 抽取路徑目前完全未分組（事實）
- Classification: fact
- Evidence: `load_postgres.py:109 stage_extraction_output` 每個 node/edge 各寫一列，
  `item_id = f"curation:{node['id']}"`（全域），**不寫 `group_id`**；`list_groups` 只取
  `group_id IS NOT NULL`，故永遠看不到。`frontend/app.js:928` 對使用者揭露了這個斷點。
- Current status: 已確認

### F2 — 一個群組含兩個 pattern 時，專家 lens 只描述第一個（事實，決定性）
- Classification: fact
- Evidence: 容器內實測。單一陳述與「胰島素+升糖素」兩陳述的 proposal，
  `render_understanding` 皆回 `P1 / 「胰島素會造成一個調控效果:使血糖下降。」`，
  升糖素陳述**被靜默丟棄**，而 `evaluate` 仍回 `pass`。機制：`back_translation.py:72`
  `edges_of(rel)[0]` 只取第一條。
- Affected scope: 淘汰 G1 的 (a) 一個 chunk 一組 與 (b) 連通元件——本例兩陳述共用「血糖」節點，
  連通元件會把它們併成一組。
- Rationale: 專家會在只讀到一半描述的情況下核准寫入，違反治理主軸。

### F3 — pattern 的判定規則是確定性的（事實）
- Classification: fact
- Evidence: `engineer_gate.py:42 _pattern_check` 只認兩種：`RegulatoryEffect`（需 HAS_EFFECT 入邊、
  ON_VARIABLE 出邊、INCREASES/DECREASES 出邊）與 `Interaction`（≥2 條 USES_EFFECT、1 條 ON_VARIABLE）。
- Affected scope: G1=(c) 可被確定性實作，無需 LLM 或啟發式。

### F4 — 抽取路徑可離線零成本測試（事實）
- Classification: fact
- Evidence: `ingestion/tests/test_document_ingest.py` 以注入的 `fake_extract` 搭配 `pg_conn` /
  `qdrant_client` fixtures 跑完整 run（`test_full_run_stages_proposed_and_writes_chunks`、
  `test_full_run_is_idempotent_on_chunk_count`）。
- Affected scope: 本變更的驗收可完全離線，不需 token。上述兩個測試需同步更新。

### F5 — DB 內沒有任何既有的未分組 llm items（事實）
- Classification: fact
- Evidence: `SELECT proposed_by, group_id IS NULL, status, count(*)` → 僅 `demo`(19)、`human`(8)，
  全部 `group_id NOT NULL`；`proposed_by='llm'` 為 0 列。
- Affected scope: 不需要 backfill/migration。

### F6 — runner 已持有 Neo4j driver 並已查詢既有概念（事實）
- Classification: fact
- Evidence: `runner.py:90 _fetch_existing_concepts(neo4j_driver, limit)`，回傳 approved/proposed
  節點的 `id: label` 清單餵給 prompt。
- Affected scope: G2 的「已 approved 只引用」無需新增資料來源。

### G1 — 抽取路徑的分組規則
- Classification: user-owned — **RESOLVED**
- Owner: owner（2026-08-11）
- Depends on: F2, F3
- Resolution: **(c) pattern instance 切分**。每個 `RegulatoryEffect` / `Interaction` 實例連同其
  必要邊與端點節點成一組；不屬於任何 pattern 的殘餘每 chunk 歸為一組。
- Rationale: 完全重用 `_pattern_check` 既有語意，不改 contract、不花 token；且與專家 lens 的兩種
  形態一一對應（pattern → P1 精確句；殘餘 → P0 plain summary）。F2 已淘汰 (a)(b)；(d) 需變更
  `extraction_output_schema`（`additionalProperties: false`）與 prompt，且分組可靠度只能花錢驗證。

### G2 — item_id 命名與共用概念的去重語意
- Classification: user-owned — **RESOLVED**
- Owner: owner（2026-08-11）
- Depends on: G1, F6
- Resolution: **已在 approved 圖的節點只被引用、不重新提案；尚未核准者各組重複提案。**
  item_id 改為群組範圍 `curation:{group_id}:{elem_id}`（與 demo/手工路徑一致）。
- 已知並接受的後果：同一次執行內兩組都需要同一個**未核准**節點時，兩組各自提案；先核准者寫入圖，
  後核准者會命中 `approve_group` 的「成員 id 已存在於 approved 圖」→ **409**，需退回重提。
  跨 chunk 的重複提案同理（今日的全域去重會消失）。
- Rationale: 沿用手工路徑既有機制，不弱化 B1 guard（該 guard 是防「核准 MERGE 覆蓋既有策展知識」）。

### G3 — 跨 chunk 的陳述
- Classification: user-owned — **RESOLVED**
- Owner: owner（2026-08-11）
- Resolution: **分組限縮在單一 chunk 內**，`runner.py` 逐 chunk 迴圈結構不變。
- 已知並接受的後果：被切斷的 pattern 會被 Schema gate 判 `fail_pattern` 而由專家退回，不會靜默進圖譜。
- Evidence: 實測 `markdown_header` 切塊 = 一個小節（本語料 ~83–157 字），陳述極少跨節。

### G4 — P5 的 phase 邊界
- Classification: user-owned — **RESOLVED**
- Owner: owner（2026-08-11）
- Resolution: **拆開。本次只交付抽取路徑分組**；`live schema-gap backlog (D2)` 另列獨立 phase/change。
- Rationale: 兩者唯一關聯是同列於一行 roadmap bullet；backlog 另有未決的生命週期決定（見 DF1）。

### I1 — group_id 命名必須是確定性的（實作預設）
- Classification: implementation-owned
- Depends on: G1, G2
- Implementation default: `group:llm:{chunk_id}:{anchor_node_id}`，殘餘組為
  `group:llm:{chunk_id}:residual`。
- Rationale: item_id 改為群組範圍後，若 group_id 用隨機 uuid，重跑同一章節會產生**全新的 item_id**，
  `ON CONFLICT DO NOTHING` 失效 → 審閱佇列被重複灌入。確定性命名可保住今日既有的重跑冪等性。
  現有 `test_full_run_is_idempotent_on_chunk_count` 只斷言 chunk 數，抓不到這件事——本變更應補上
  對 `curation_items` 的冪等斷言。

### I2 — 殘餘組的產生條件（實作預設）
- Classification: implementation-owned
- Implementation default: 該 chunk 若無殘餘元素則**不產生**殘餘組；殘餘組僅含未被任何 pattern 佔用的
  節點與邊。
- 已知後果：一個 4-chunk 章節大致產生 6–8 個待審群組（審閱負載，非缺陷）。

### I3 — 「已 approved」的判定時機（實作預設）
- Classification: implementation-owned
- Depends on: G2, F6
- Implementation default: staging 當下以 `runner.py` 既有的 Neo4j driver 查詢 approved 節點；
  沿用 `service._existing_approved_ids` 的查法，不新增資料來源。

### I4 — 既有 `group_id IS NULL` 的資料（實作預設）
- Classification: implementation-owned
- Depends on: F5
- Implementation default: 不做 backfill、不做 migration。DB 內無此類資料；`list_groups` 本就忽略它們。

### I5 — 抽取路徑不設 `possible_schema_gap`（實作預設）
- Classification: implementation-owned
- Implementation default: 不設（維持 falsy）。`extraction_output_schema` 沒有對應欄位，LLM 無從表達；
  真正的 schema gap 由專家在審閱時以「記為 gap」判定。

### DF1 — schema-gap backlog 生命週期
- Classification: intentionally deferred
- Owner: owner
- Safe-deferral rationale: 本次的下游產物（抽取分組的 implementation plan）可在不假設任何 backlog
  答案的情況下完整寫出；它不改變本次 scope、契約或驗收條件的意義。
- Becomes blocking when: 開始對**真實章節**（非 demo 來源）記錄 gap 時（`REVIEW_REPORT.md` L2 已載明
  同一觸發條件），或宣告 P5 完成時。
- 內含未決項：gap 的 accept/reject/**復原**、`possible_schema_gap` 的有稽核 engineer override（L3）、
  `schema_gap_backlog.json` 去留（S3）。

### DF2 — 「gold 改打真實抽取輸出」
- Classification: intentionally deferred
- Owner: owner
- Evidence: `backend/tests/gold/test_gold_examples.py` docstring 自陳「MVP 先打 cases.json 裡的固定
  proposal；未來換真 pipeline 時，gold 從『打固定 proposal』切成『打真實抽取輸出』」。regression 網
  已存在且全綠（6 tests）。
- Safe-deferral rationale: 本次交付不依賴它；現有 gold 仍是有效的 renderer 回歸網。
- Becomes blocking when: 宣告 P5 完成時，或要以真實抽取輸出作為 golden 基準時。

## Inventory Coverage

- Areas examined: roadmap（`unified-two-gate-review` §Roadmap 及其 R3 延後條款、P2/P3 的對應註記）、
  `ingestion/extract/{runner,parse_document,chunkers}.py`、`ingestion/pipeline/load_postgres.py`、
  `backend/app/graph/{engineer_gate,back_translation}.py`、`backend/app/curation/service.py`、
  `schema/extraction_output_schema.json`、`prompts/graph_extraction_prompt.md`、
  `ingestion/tests/test_document_ingest.py`、`docs/api_contract.md`、
  `changes/group-review-gap-outcome/REVIEW_REPORT*.md`、Postgres 現況、live `/admin/ingest/{options,preview}`。
- Known gaps:
  - 未實際跑過一次真實 LLM 抽取來觀察單一 chunk 的產出規模（會花 token）；分組規則的行為以
    `_pattern_check` 的確定性語意推導，實作階段應以離線 `fake_extract` 覆蓋多 pattern / 純殘餘 / 混合三種形態。
  - 無 ADR 目錄、無 glossary/CONTEXT 檔（本 repo 未採用），故未寫 ADR；`提案群組` 一詞已在
    `docs/api_contract.md` 定義，本次沿用未改變其意義。
- Last checked against repository and documents: 2026-08-11，`main` @ `0a3e5be`。
