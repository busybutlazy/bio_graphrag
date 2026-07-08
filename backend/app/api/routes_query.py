import time

import anyio
from fastapi import APIRouter, Depends

from app.api.auth import require_vendor
from app.db import query_logs
from app.db import vendors as vendors_db
from app.db.vendors import Vendor
from app.llm import gateway
from app.llm.usage import UsageAccumulator
from app.rag import pipeline
from app.schemas.query import (
    CheckAnswerRequest,
    CheckAnswerResponse,
    QueryRequest,
    QueryResponse,
)

router = APIRouter()


async def _record_usage_safe(vendor_code: str, tokens: int, endpoint: str) -> None:
    """Best-effort usage write: a DB hiccup here must not fail an answer that was
    already produced (and paid for). Mirrors query_logs.log_query's stance."""
    try:
        await vendors_db.record_usage(vendor_code, tokens, endpoint)
    except Exception:
        pass


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, vendor: Vendor = Depends(require_vendor)) -> QueryResponse:
    started = time.perf_counter()
    # Request-level tally: recorded in `finally` so tokens already spent are
    # billed even if a later stage fails.
    usage = UsageAccumulator()
    try:
        result = await pipeline.answer_query(
            body.question, body.top_k, body.graph_depth, body.include_debug, usage
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
    finally:
        if usage.total > 0:
            await _record_usage_safe(vendor.vendor_code, usage.total, "/query")


@router.post("/check-answer", response_model=CheckAnswerResponse)
async def check_answer(
    body: CheckAnswerRequest, vendor: Vendor = Depends(require_vendor)
) -> CheckAnswerResponse:
    usage = UsageAccumulator()
    try:
        question = body.question or body.question_id or ""
        composed = await pipeline.retrieve(question, top_k=5, graph_depth=1, acc=usage)
        supporting_nodes = composed["supporting_nodes"]
        misconception_nodes = [n for n in supporting_nodes if n["type"] == "Misconception"]

        verdict, check_usage = await anyio.to_thread.run_sync(
            gateway.check_misconception,
            composed["context_text"], question, body.student_answer, misconception_nodes,
        )
        usage.add(check_usage)
        return CheckAnswerResponse(
            is_correct=verdict["is_correct"],
            misconceptions_detected=verdict["misconceptions_detected"],
            feedback=verdict["feedback"],
            supporting_nodes=supporting_nodes,
        )
    finally:
        if usage.total > 0:
            await _record_usage_safe(vendor.vendor_code, usage.total, "/check-answer")
