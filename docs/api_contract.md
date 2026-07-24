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

只列 `status='proposed'` 的群組;唯讀。

### `POST /admin/review/groups/{group_id}/approve`

以一次交易核准整個群組:把所有成員 node/edge 寫入 Neo4j 為 `approved`、翻各 item 狀態、`graph_change_logs` 追加一列(`action='approve'`、`target_type='proposal_group'`、`target_id=group_id`)。Request `{reviewer, reason?}`。回傳 `{group_id, status:'approved', nodes, edges}`。未知群組 → 404;無 proposed 成員 → 409。

### `POST /admin/review/groups/{group_id}/reject`

翻整個群組為 `rejected`,**不寫 Neo4j**,`graph_change_logs` 追加 `action='reject'` 一列。Request/錯誤碼同上,回傳 `{group_id, status:'rejected'}`。

### `GET /admin/expert-demo/cases`

Expert-in-the-loop governance demo 的**唯讀**資料出口(admin key 保護,同其他 `/admin/*`)。回傳 `data/sample/expert_demo/cases.json` 的固定 demo 案例;每筆額外附上**當場計算、不落地**的兩個欄位:

- `system_understanding`:`{pattern, rule_id, is_gap, text}` — 由 deterministic 反向翻譯器(`app/graph/back_translation.py`,無 LLM)算出的白話「系統理解」。
- `engineer_gate`:`{result, checks[]}` — 由 `app/graph/engineer_gate.py` 複用既有 schema/型別驗證算出的形式判定,`result ∈ {pass, fail_schema, fail_pattern, fail_testability, needs_schema_extension}`。

此 `GET` **唯讀**:不寫任何 store、不碰 approved 圖、不繞過 curation;無副作用。

### `POST /admin/expert-demo/reviews`

把一位 demo 觀看者的專家 gate 決定寫成 **append-only 稽核列**(admin key 保護,同其他 `/admin/*`)。Request:

```
{
  case_id: str,                         # 必填,1–200 字
  decision: "agree" | "doubt" | "cannot",  # 必填;非此三者 → 422
  schema_gap_type: str | null,          # 選填,僅 decision="cannot" 有意義
  notes: str | null                     # 選填,≤2000 字
}
```

回傳 `201 { change_id, status: "recorded" }`。副作用**僅**在 `graph_change_logs` 追加一列(`action='expert_review'`、`target_type='expert_demo_case'`、`target_id=case_id`、`actor='demo-viewer'`、`after_state={decision, schema_gap_type}`);**不碰 approved 圖、不寫 Neo4j、不繞過 curation**。作者權威審查另行 seed。設計與唯讀→附加式寫入的變更說明見 `docs/expert-in-the-loop-plan.md` 五.4 與 `changes/expert-gate-integrity/`。

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
