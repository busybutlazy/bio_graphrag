from pydantic import BaseModel, Field, model_validator

from app.schemas.graph import NodeRef, RelationshipRef

# Shared access limits (see docs/api_contract.md section 1). These are the only
# access-control mechanism for the local demo; oversized params return 422.
MAX_QUESTION_LEN = 500
MAX_TOP_K = 10
MAX_GRAPH_DEPTH = 2
MAX_STUDENT_ANSWER_LEN = 1000


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    snippet: str


class RetrievalDebug(BaseModel):
    vector_hits: int
    graph_nodes: int
    graph_depth: int


class QueryRequest(BaseModel):
    question: str = Field(max_length=MAX_QUESTION_LEN, min_length=1)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    graph_depth: int = Field(default=1, ge=1, le=MAX_GRAPH_DEPTH)
    include_debug: bool = False  # only honoured in local/dev env


class QueryResponse(BaseModel):
    answer: str
    supporting_nodes: list[NodeRef]
    relationships_used: list[RelationshipRef]
    citations: list[Citation]
    retrieval_debug: RetrievalDebug | None = None


class NodeDetailResponse(BaseModel):
    id: str
    type: str
    label: str
    description: str | None = None
    properties: dict


class ConceptMapRequest(BaseModel):
    node_ids: list[str] | None = None
    topic: str | None = None
    depth: int = Field(default=1, ge=1, le=MAX_GRAPH_DEPTH)

    @model_validator(mode="after")
    def _require_seed(self) -> "ConceptMapRequest":
        if not self.node_ids and not self.topic:
            raise ValueError("node_ids or topic is required")
        return self


class ConceptMapResponse(BaseModel):
    nodes: list[NodeRef]
    edges: list[RelationshipRef]


class CheckAnswerRequest(BaseModel):
    question_id: str | None = None
    question: str | None = None
    student_answer: str = Field(max_length=MAX_STUDENT_ANSWER_LEN, min_length=1)

    @model_validator(mode="after")
    def _require_question(self) -> "CheckAnswerRequest":
        if not self.question_id and not self.question:
            raise ValueError("question_id or question is required")
        return self


class CheckAnswerResponse(BaseModel):
    is_correct: bool
    misconceptions_detected: list[NodeRef]
    feedback: str
    supporting_nodes: list[NodeRef]
