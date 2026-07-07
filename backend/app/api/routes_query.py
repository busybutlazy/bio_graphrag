import time

from fastapi import APIRouter

from app.db import query_logs
from app.llm import gateway
from app.rag import pipeline
from app.schemas.query import (
    CheckAnswerRequest,
    CheckAnswerResponse,
    QueryRequest,
    QueryResponse,
)

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest) -> QueryResponse:
    started = time.perf_counter()
    result = await pipeline.answer_query(
        body.question, body.top_k, body.graph_depth, body.include_debug
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    await query_logs.log_query(
        question=body.question,
        answer=result["answer"],
        retrieval_debug={
            "vector_hits": len(result["citations"]),
            "graph_nodes": len(result["supporting_nodes"]),
            "graph_depth": body.graph_depth,
        },
        latency_ms=latency_ms,
    )
    return QueryResponse(**result)


@router.post("/check-answer", response_model=CheckAnswerResponse)
async def check_answer(body: CheckAnswerRequest) -> CheckAnswerResponse:
    question = body.question or body.question_id or ""
    composed = await pipeline.retrieve(question, top_k=5, graph_depth=1)
    supporting_nodes = composed["supporting_nodes"]
    misconception_nodes = [n for n in supporting_nodes if n["type"] == "Misconception"]

    verdict = gateway.check_misconception(
        composed["context_text"], question, body.student_answer, misconception_nodes
    )
    return CheckAnswerResponse(
        is_correct=verdict["is_correct"],
        misconceptions_detected=verdict["misconceptions_detected"],
        feedback=verdict["feedback"],
        supporting_nodes=supporting_nodes,
    )
