# Graph & Data Schema

本文件是資料層的總覽,涵蓋 Neo4j、PostgreSQL、Qdrant 三個儲存,以及貫穿三者的 human curation 流程。Node/relationship 的完整清單見 `node_types.md`、`relationship_types.md`。

範圍與邊界的決策紀錄(為什麼沒有 `visibility` 欄位)見專案討論紀錄,此處只寫最終定案的 schema。

## 0. 治理原則

好的知識圖譜不應完全依賴 LLM 自動生成。**LLM 只負責提案,知識圖譜需要人工治理**:

```text
LLM extraction -> proposed graph changes -> human review -> approved graph -> retrieval
```

- LLM 產生的是 draft / proposed 節點與關係,結構規範見 `extraction_output_schema.json`,判斷準則見 `extraction_guidelines.md`。
- 人可以新增節點、補關係、刪除多餘節點、合併同義概念、調整關係類型。
- 只有 `approved` 狀態的節點與關係會進入正式 GraphRAG retrieval(見 1.2 節)。
- 每次人工修改都保留 provenance 與 change log(`curation_items` + `graph_change_logs`,見 2.4-2.6 節),方便追蹤知識圖譜品質。

架構上,這對應系統元件表裡的 **Curation Layer**(FastAPI admin endpoints,見 `docs/api_contract.md` 第 3 節)。

## 1. Neo4j

### 1.1 Constraints / Indexes

每個 node type 都需要在 `id` 屬性上建唯一約束,並在 `status` 上建索引(curation 查詢與 retrieval 過濾都會用到):

```cypher
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (n:Concept) REQUIRE n.id IS UNIQUE;

-- 對每個 node label 重複上述 constraint:
-- System, Process, Structure, Molecule, Hormone, Receptor,
-- PhysiologicalVariable, RegulatoryEffect, Interaction, FeedbackLoop,
-- Enzyme, Disease, Experiment, Misconception

CREATE INDEX node_status_idx IF NOT EXISTS
FOR (n:Concept) ON (n.status);
-- 對每個 node label 重複
```

### 1.2 Retrieval 只查 approved

所有面向 `/query`、`/neighbors`、`/concept-map` 的 Cypher template,都必須在 `MATCH` 之後加上:

```cypher
WHERE n.status = 'approved'
```

關係也一樣,只走 `status = 'approved'` 的邊。這是 retrieval 層唯一的資料過濾規則,取代原本考慮過的 DB 級 `visibility` 欄位。

## 2. PostgreSQL

版本控管:MVP 不建立 `graph_versions` 表。schema/資料版本追蹤交給 git log / git diff(sample seed JSON 本身就在版控裡),逐筆節點/關係層級的異動則由 `graph_change_logs`(2.5 節)記錄。

### 2.1 documents

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| doc_id | text, unique | 例如 `doc:sample:homeostasis` |
| title | text | |
| topic | text | 例如 `blood_glucose_regulation` |
| grade_level | text | 高一/高二/高三/通用 |
| source_type | text | `textbook_note` / `curated_note` / `sample` |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 2.2 chunks

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| chunk_id | text, unique | 例如 `chunk:sample:001` |
| doc_id | text, fk -> documents.doc_id | |
| content | text | chunk 原文(sample 資料集裡就是可公開的內容) |
| concept_ids | jsonb (string array) | 對應 Neo4j node id 列表 |
| topic | text | |
| grade_level | text | |
| source_type | text | |
| created_at | timestamptz | |

### 2.3 ingestion_jobs

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| job_id | text, unique | |
| status | text | `pending` / `running` / `success` / `failed` |
| source_path | text | ingestion 來源檔案路徑 |
| stats | jsonb | `{ "nodes": n, "edges": n, "chunks": n }` |
| error_message | text, nullable | |
| started_at | timestamptz | |
| finished_at | timestamptz, nullable | |

### 2.4 curation_items — 待審佇列

代表一筆「尚待處理」的候選變更。這張表只描述**目前狀態**,不記錄歷史——歷史交給 `graph_change_logs`。

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| item_id | text, unique | |
| item_type | text | `node` / `edge` |
| action | text | `create` / `update` / `delete` / `merge` |
| payload | jsonb | 候選節點或關係的完整內容(對應 Neo4j 屬性結構) |
| status | text | `proposed` / `approved` / `rejected` / `deprecated` / `merged` |
| proposed_by | text | `llm` 或人工使用者名稱 |
| reviewed_by | text, nullable | |
| reason | text, nullable | |
| created_at | timestamptz | |
| reviewed_at | timestamptz, nullable | |

若 `payload` 來源是 LLM extraction(而非人工手動新增),其結構必須符合 `schema/extraction_output_schema.json`;不符合者由 ingestion pipeline 直接拒絕,不寫入這張表(判斷準則見 `schema/extraction_guidelines.md`)。

### 2.5 graph_change_logs — 不可變操作日誌

代表一筆「已經發生」的操作,寫入後不再更新(append-only)。

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| change_id | text, unique | |
| curation_item_id | uuid, fk -> curation_items.id, nullable | 若此操作源自審核流程則帶入 |
| action | text | `create` / `approve` / `reject` / `delete` / `merge` |
| target_type | text | `node` / `edge` |
| target_id | text | 對應 Neo4j node/edge id |
| actor | text | 執行者 |
| reason | text, nullable | |
| before_state | jsonb, nullable | |
| after_state | jsonb, nullable | |
| created_at | timestamptz | |

### 2.6 curation_items 與 graph_change_logs 的職責分工

```text
LLM/person proposes change
  -> curation_items 記錄待審狀態(pending queue)
  -> approve/reject/merge/delete
  -> graph_change_logs 記錄已發生操作(immutable log)
  -> approved graph 才進 retrieval
```

規則:

- `curation_items` 不存操作日誌,只存「現在的審核狀態」。
- `graph_change_logs` 不存審核狀態機,只存「發生過什麼操作」,寫入後不可修改。
- 同一件事不會同時在兩張表存完整的 diff/歷史——`curation_items.payload` 是候選內容本身,`graph_change_logs.before_state/after_state` 是操作發生當下的前後快照。

### 2.7 query_logs

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| query_id | text, unique | |
| question | text | |
| answer | text | |
| retrieval_debug | jsonb | `{ vector_hits, graph_nodes, graph_depth }` |
| latency_ms | integer | |
| created_at | timestamptz | |

### 2.8 evaluation_runs

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| run_id | text, unique | |
| started_at | timestamptz | |
| finished_at | timestamptz, nullable | |
| metrics | jsonb | `{ recall_at_5, grounded_pass_rate, ... }` |
| notes | text, nullable | |

### 2.9 evaluation_items

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | uuid, pk | |
| run_id | uuid, fk -> evaluation_runs.id | |
| question_id | text | |
| question | text | |
| expected_nodes | jsonb | |
| retrieved_nodes | jsonb | |
| passed | boolean | |
| notes | text, nullable | |

## 3. Qdrant

Collection: `biology_chunks`

| Payload 欄位 | 說明 |
|---|---|
| chunk_id | 對應 PostgreSQL `chunks.chunk_id` |
| doc_id | 對應 `documents.doc_id` |
| concept_ids | 相關 Neo4j node id 列表 |
| topic | |
| grade_level | |
| source_type | `textbook_note` / `curated_note` / `sample` |

## 4. Curation Workflow 狀態機

| Status | 意義 |
|---|---|
| proposed | LLM 或人工提出,尚未審核 |
| approved | 已審核,可進入正式 retrieval |
| rejected | 已拒絕,不進入 retrieval |
| deprecated | 曾經使用,但後來被淘汰 |
| merged | 已合併到其他節點(僅節點適用) |

節點合併時,原節點狀態改為 `merged` 並帶 `merged_into` 屬性指向目標節點 id;原節點上的關係由 curation workflow 改寫為指向目標節點,而不是留著指向一個已合併節點的斷鏈。
