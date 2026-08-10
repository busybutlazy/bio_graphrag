# API Contract

對應 `docs/graph_plan.md` 第 5 節,DTO 以 Pydantic 概念表示。所有 request 都會被驗證,超出上限的參數回傳 422,不會被 silently clamp。

## 1. 共同上限

| 參數 | 上限 | 用途 |
|---|---|---|
| `question` 長度 | 500 字元 | 防止過長 prompt |
| `top_k` | 10 | 向量檢索筆數上限 |
| `graph_depth` | 2 | 圖擴展深度上限 |
| 回傳 nodes | 30 | 單次回應節點數上限 |
| 回傳 chunks | 10 | 單次回應 chunk 數上限 |

這些上限是目前(local demo only)唯一的存取控管手段,取代原本考慮過的 rate-limit middleware——真的要公開部署時才需要加真正的 rate limiter。

## 2. 公開 API

### `GET /health`

回傳每個依賴(Postgres / Neo4j / Qdrant)的連線狀態。

```python
class DependencyStatus(BaseModel):
    name: str
    ok: bool
    detail: str | None = None

class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    dependencies: list[DependencyStatus]
```

### `POST /query`

```python
class QueryRequest(BaseModel):
    question: str = Field(max_length=500)
    top_k: int = Field(default=5, le=10)
    graph_depth: int = Field(default=1, le=2)
    include_debug: bool = False  # 僅 local/dev 環境允許為 True

class NodeRef(BaseModel):
    id: str
    label: str
    type: str

class RelationshipRef(BaseModel):
    source: str
    relation: str
    target: str

class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    snippet: str

class RetrievalDebug(BaseModel):
    vector_hits: int
    graph_nodes: int
    graph_depth: int

class QueryResponse(BaseModel):
    answer: str
    supporting_nodes: list[NodeRef]
    relationships_used: list[RelationshipRef]
    citations: list[Citation]
    retrieval_debug: RetrievalDebug | None = None
```

### `GET /nodes/{node_id}`

```python
class NodeDetailResponse(BaseModel):
    id: str
    type: str
    label: str
    description: str | None = None
    properties: dict  # 該 node type 特有屬性,例如 interaction_type / feedback_type
```

只回傳 `status = approved` 的節點,其餘回 404。

### `GET /neighbors/{node_id}`

Query params: `depth: int = 1 (le=2)`, `limit: int = 30`

```python
class NeighborsResponse(BaseModel):
    center_node: NodeRef
    nodes: list[NodeRef]
    edges: list[RelationshipRef]
    depth: int
```

### `POST /concept-map`

```python
class ConceptMapRequest(BaseModel):
    node_ids: list[str] | None = None
    topic: str | None = None  # node_ids 與 topic 至少擇一
    depth: int = Field(default=1, le=2)

class ConceptMapResponse(BaseModel):
    nodes: list[NodeRef]
    edges: list[RelationshipRef]
```

### `POST /check-answer`

```python
class CheckAnswerRequest(BaseModel):
    question_id: str | None = None
    question: str | None = None  # question_id 與 question 至少擇一
    student_answer: str = Field(max_length=1000)

class CheckAnswerResponse(BaseModel):
    is_correct: bool
    misconceptions_detected: list[NodeRef]
    feedback: str
    supporting_nodes: list[NodeRef]
```

## 3. Admin / Curation API

僅供本機或受信任環境使用,不對外公開 demo。

### `GET /admin/curation/items`

Query params: `status: str | None`, `item_type: str | None`

```python
class CurationItemResponse(BaseModel):
    item_id: str
    item_type: str  # node | edge
    action: str  # create | update | delete | merge
    payload: dict
    status: str
    proposed_by: str
    reviewed_by: str | None = None
    reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
```

### `POST /admin/curation/items`

```python
class CurationItemCreate(BaseModel):
    item_type: str  # node | edge
    action: str  # create | update | delete | merge
    payload: dict
    reason: str | None = None
```

寫入 `curation_items`,狀態預設 `proposed`。

### `POST /admin/curation/groups`

手工建構一個**提案群組**(一個生物陳述的 nodes+edges),共用一個 `group_id` 一起送進群組審閱佇列(`GET /admin/review/groups`)。這是 propose 側「人工建構」的入口,與 LLM 抽取共用同一條治理管線。

```python
class CurationGroupCreate(BaseModel):
    proposed_nodes: list[dict] = []
    proposed_edges: list[dict] = []
    reason: str | None = None
    possible_schema_gap: bool = False
```

副作用:每個成員以 `status='proposed'`、`proposed_by='human'`、共用 `group_id`(`group:human:{uuid}`)寫入 `curation_items`,置於**單一交易**內(任一元素失敗則整組 rollback)。**不**寫 Neo4j、不寫 `graph_change_logs`(提案階段不算圖變更;核准/退回時才記)。缺 `source_chunk_id` 的元素會補上 namespaced provenance 標記 `"manual:{proposed_by}"`(手工知識的來源即作者本人;namespaced 以免與真實 chunk id 相撞),以通過 Schema gate。`reason` 若有,存入各成員 `schema_check.propose_reason`(以免被核准/退回時覆蓋 `curation_items.reason`),並由 `GET /admin/review/groups` 以 `propose_reason` 回傳、顯示在審閱卡上。成功回傳 `201 {group_id, nodes, edges}`。

驗證(皆回 `422`,遵循 `{"error":{code,message}}` 契約):

| 情況 | 回應 |
| --- | --- |
| 空群組(0 nodes 且 0 edges) | `422 invalid_request` |
| 元素型別不在白名單(injection guard) | `422 invalid_request` |
| 元素總數超過上限(`MAX_GROUP_ELEMENTS = 20`) | `422 invalid_request` |
| 群組內重複 id(node+edge 合併集合) | `422 invalid_request` |
| edge 端點無法解析(既非本群組提案節點、也非既有 approved 節點) | `422 invalid_request` |

此端點依 CLAUDE.md 契約回 `{"error":{code,message}}`(較舊的 `/admin/curation/items` 仍回 `{"detail"}`)。

### `POST /admin/curation/items/{item_id}/approve`

```python
class ReviewDecision(BaseModel):
    reviewer: str
    reason: str | None = None
```

副作用:`curation_items.status -> approved`;寫入 Neo4j(狀態 `approved`);寫入一筆 `graph_change_logs`(`action = approve`)。

### `POST /admin/curation/items/{item_id}/reject`

同 `ReviewDecision` payload。副作用:`curation_items.status -> rejected`;**不**寫入 Neo4j;寫入一筆 `graph_change_logs`(`action = reject`)。

### `POST /admin/graph/merge-nodes`

```python
class MergeNodesRequest(BaseModel):
    source_node_id: str
    target_node_id: str
    reason: str
```

副作用:`source_node_id` 狀態改為 `merged`,帶 `merged_into = target_node_id`;所有指向/來自 `source_node_id` 的關係改指向 `target_node_id`;寫入一筆 `graph_change_logs`(`action = merge`)。

### `POST /admin/graph/delete-node`

```python
class DeleteNodeRequest(BaseModel):
    node_id: str
    reason: str
```

副作用:軟刪除(`status -> deprecated`),不做實體刪除;寫入一筆 `graph_change_logs`(`action = delete`, `target_type = node`)。

### `POST /admin/graph/delete-edge`

```python
class DeleteEdgeRequest(BaseModel):
    edge_id: str
    reason: str
```

副作用同上,`target_type = edge`。

### `GET /admin/review/groups`

統一兩道 gate 的 review 出口(admin key 保護)。回傳每個**提案群組**(共用 `group_id` 的 `curation_items` = 一個生物陳述的 nodes+edges)一筆,附上**當場計算**的:

- `proposal`:`{proposed_nodes, proposed_edges}`(由群組成員組裝,已去除 curation 內部 `status` 欄位)。
- `schema_gate`:`engineer_gate.evaluate` 的形式判定(`{result, checks[]}`)。
- `understanding`:`back_translation` 的白話「系統理解」(`{pattern, is_gap, text}`)。
- `propose_reason`:提案時的理由(`str | None`;來自成員 `schema_check.propose_reason`),供審閱者在專家 gate 前看見提案動機。

只列 `status='proposed'` 的群組;唯讀。

### `POST /admin/review/groups/{group_id}/approve`

以一次交易核准整個群組:把所有成員 node/edge 寫入 Neo4j 為 `approved`、翻各 item 狀態、`graph_change_logs` 追加一列(`action='approve'`、`target_type='proposal_group'`、`target_id=group_id`,`after_state` 含**完整 payload** 與 `item_ids`,足以重建進圖內容)。Request `{reviewer, reason?}`。成功回傳 `{group_id, status:'approved', nodes, edges}`。

**核准前的四道防線**(任一不過即拒絕,不寫入任何東西):

| 情況 | 狀態碼 |
|---|---|
| 群組不存在 | `404 not_found` |
| 沒有 `proposed` 成員(含重複核准) | `409 conflict` |
| 成員 `action` 不是 `create`(此路徑只實作 create) | `422 invalid_request` |
| **Schema gate 未通過**(`result != 'pass'`,含 `needs_schema_extension`)— gate 為**強制**,形式不合格的提案不得進入圖譜 | `409 conflict` |
| **成員 id 已存在於 approved 圖**(核准會 MERGE 覆蓋既有策展知識)— 必須改走明確的 update 決策 | `409 conflict` |

錯誤 body 遵循 `{"error": {"code", "message"}}`(新端點依 CLAUDE.md 契約;較舊的 `/admin/curation/*` 仍回 `{"detail"}`)。列出時 `FOR UPDATE` 鎖列,兩個併發核准不會同時看到 `proposed`。

### `POST /admin/review/groups/{group_id}/reject`

翻整個群組為 `rejected`,**不寫 Neo4j**,`graph_change_logs` 追加 `action='reject'` 一列。Request/錯誤碼同上,回傳 `{group_id, status:'rejected'}`。

### `POST /admin/review/groups/{group_id}/gap`

第三種處置:提案本身可能是對的,但**現行 schema 表達不了它**。這與「退回」語意不同——退回是形式有問題,gap 是知識結構不夠用。把整組成員翻成 `status='schema_gap'`(離開審閱佇列)、**不寫 Neo4j**,`graph_change_logs` 追加一列 `action='schema_gap'`、`target_type='proposal_group'`,`after_state` 含 `{schema_gap_type, item_ids}`。

```python
class SchemaGapRequest(BaseModel):
    reviewer: str
    reason: str | None = None
    schema_gap_type: str
```

成功回傳 `{group_id, status:'schema_gap', schema_gap_type}`。`reviewer` 與 `reason` 一併寫入該筆稽核列(`actor` / `reason`)與各成員 `curation_items`(`reviewed_by` / `reason` / `reviewed_at`)。

`schema_gap_type` 必須是下列 6 個之一(白名單,見 `docs/schema-gap-policy.md`;專家在 UI 上看到的是白話敘述,前端才映射成代碼)。以白名單擋住自由文字,是為了讓稽核語意可歸類、可排序——之後才回答得出「哪一類 gap 最多、該優先擴充什麼」:

`permissive_effect`、`antagonistic_or_synergistic_interaction`、`pathway_or_cascade`、`conditional_effect`、`threshold_effect`、`unknown`

**四道防線**(任一不過即拒絕,狀態與稽核都不寫):

| 情況 | 狀態碼 |
|---|---|
| 群組不存在 | `404 not_found` |
| 沒有 `proposed` 成員(含重複記錄) | `409 conflict` |
| Schema gate 結果不是 `needs_schema_extension`(gap 只給真正的 schema 缺口,形式問題請走 reject) | `409 conflict` |
| `schema_gap_type` 不在白名單,或 `reviewer` 空白 | `422 invalid_request` |

狀態 UPDATE 與稽核 INSERT 在**同一個交易**內,兩者同生共死(不會出現翻了狀態卻沒有稽核紀錄)。

目前**尚無 backlog 檢視介面**:記下的 gap 只存在於 `graph_change_logs` 的 `action='schema_gap'` 資料列。完整的 backlog 生命週期(累積、排序、接受/駁回、`proposed_schema_change`)是後續獨立變更。`make demo-reset` 會把 demo 來源的 `schema_gap` 群組還原成 `proposed`,方便重複展示。

## 4. 不提供的 API

`POST /cypher`、`GET /all-nodes`、`GET /all-edges`、`GET /export-all`、`GET /raw-source/{id}` 一律不實作,理由見 `docs/graph_plan.md` 5.3 節。

## 5. LLM Gateway(內部介面,非對外 API)

`/query`、`/check-answer` 內部透過一個 provider-agnostic 的 gateway 呼叫 LLM,第一版只接 OpenAI:

```python
class LLMGateway(Protocol):
    def generate_answer(self, context: str, question: str) -> str: ...
    def check_misconception(self, context: str, student_answer: str) -> CheckAnswerResponse: ...
```

第一版實作用單一模組內的 provider 分支(`if provider == "openai": ...`),不做 plugin registry;等真的要接第二個 provider 時再抽介面。
