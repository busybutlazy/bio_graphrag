"""Evaluation runner (Phase 5).

Runs the hybrid retrieval pipeline over the golden questions in
data/sample/sample_questions.json, computes retrieval recall@k, grounded-answer
pass rate and latency, persists a run to Postgres (evaluation_runs /
evaluation_items) and renders a Markdown + JSON report.

Metrics are computed against the same retrieval the /query endpoint uses, so the
numbers reflect real API behaviour (in offline mode, the lexical fallback).
"""

import asyncio
import json
import time
import uuid
from pathlib import Path

from app.core.config import settings
from app.db.pool import connection
from app.eval import metrics
from app.rag import pipeline
from ingestion.pipeline.parse_source import DATA_DIR

QUESTIONS_PATH = DATA_DIR / "sample_questions.json"

# Pass thresholds (docs/graph_plan.md Phase 5).
RECALL_THRESHOLD = 0.8
GROUNDED_THRESHOLD = 0.75
LATENCY_P95_MS = 5000

TOP_K = 5
GRAPH_DEPTH = 1


def load_questions() -> list[dict]:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


async def _evaluate_question(question: dict) -> dict:
    started = time.perf_counter()
    result = await pipeline.answer_query(
        question["question"], TOP_K, GRAPH_DEPTH, include_debug=False
    )
    latency_ms = (time.perf_counter() - started) * 1000

    retrieved_chunk_ids = [c["chunk_id"] for c in result["citations"]]
    supporting_node_ids = [n["id"] for n in result["supporting_nodes"]]

    recall = metrics.recall_at_k(question["expected_chunk_ids"], retrieved_chunk_ids)
    grounded = metrics.grounded_pass(question["expected_node_ids"], supporting_node_ids)

    return {
        "question_id": question["question_id"],
        "question": question["question"],
        "expected_chunk_ids": question["expected_chunk_ids"],
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "expected_node_ids": question["expected_node_ids"],
        "recall_at_k": recall,
        "grounded_pass": grounded,
        "latency_ms": round(latency_ms, 1),
        # An item "passes" only when it retrieves the right chunk AND grounds the
        # answer in the required nodes — low-quality answers are flagged here.
        "passed": recall >= RECALL_THRESHOLD and grounded,
    }


async def run_evaluation(persist: bool = True) -> dict:
    questions = load_questions()
    items = [await _evaluate_question(q) for q in questions]

    recalls = [it["recall_at_k"] for it in items]
    latencies = [it["latency_ms"] for it in items]
    mean_recall = sum(recalls) / len(recalls)
    grounded_rate = sum(1 for it in items if it["grounded_pass"]) / len(items)
    p95_latency = metrics.percentile(latencies, 95)

    summary = {
        "run_id": f"eval:{uuid.uuid4()}",
        "num_questions": len(items),
        "recall_at_k": round(mean_recall, 3),
        "grounded_pass_rate": round(grounded_rate, 3),
        "latency_p95_ms": round(p95_latency, 1),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 1),
        "top_k": TOP_K,
        "graph_depth": GRAPH_DEPTH,
        # Mirror the retrieval/gateway condition so the reported mode matches the
        # path actually taken (both require provider AND key).
        "mode": "openai" if (settings.llm_provider == "openai" and settings.openai_api_key) else "offline",
        "thresholds": {
            "recall_at_k": RECALL_THRESHOLD,
            "grounded_pass_rate": GROUNDED_THRESHOLD,
            "latency_p95_ms": LATENCY_P95_MS,
        },
    }
    summary["passed"] = (
        mean_recall >= RECALL_THRESHOLD
        and grounded_rate >= GROUNDED_THRESHOLD
        and p95_latency <= LATENCY_P95_MS
    )
    report = {"summary": summary, "items": items}

    if persist:
        await _persist(report)
    return report


async def _persist(report: dict) -> None:
    summary = report["summary"]
    try:
        async with connection() as conn:
            run_uuid = await conn.fetchval(
                """
                INSERT INTO evaluation_runs (run_id, finished_at, metrics, notes)
                VALUES ($1, now(), $2, $3)
                RETURNING id
                """,
                summary["run_id"],
                json.dumps(summary),
                f"mode={summary['mode']} passed={summary['passed']}",
            )
            for it in report["items"]:
                await conn.execute(
                    """
                    INSERT INTO evaluation_items
                        (run_id, question_id, question, expected_nodes, retrieved_nodes, passed, notes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    run_uuid,
                    it["question_id"],
                    it["question"],
                    json.dumps(it["expected_node_ids"]),
                    json.dumps(it["retrieved_chunk_ids"]),
                    it["passed"],
                    f"recall={it['recall_at_k']} grounded={it['grounded_pass']} latency_ms={it['latency_ms']}",
                )
    except Exception:
        # Persistence is best-effort; a missing/unreachable DB must not fail eval.
        return


def to_markdown(report: dict) -> str:
    s = report["summary"]
    check = "✅" if s["passed"] else "❌"
    lines = [
        "# Evaluation Report",
        "",
        f"- Run: `{s['run_id']}`",
        f"- Mode: **{s['mode']}**  ·  Questions: **{s['num_questions']}**  ·  top_k={s['top_k']}, graph_depth={s['graph_depth']}",
        f"- Recall@{s['top_k']}: **{s['recall_at_k']}** (threshold {s['thresholds']['recall_at_k']})",
        f"- Grounded pass rate: **{s['grounded_pass_rate']}** (threshold {s['thresholds']['grounded_pass_rate']})",
        f"- Latency P95: **{s['latency_p95_ms']} ms** (threshold {s['thresholds']['latency_p95_ms']} ms)  ·  mean {s['latency_mean_ms']} ms",
        f"- Overall: {check} **{'PASS' if s['passed'] else 'FAIL'}**",
        "",
        "| # | recall@k | grounded | latency ms | passed |",
        "|---|---|---|---|---|",
    ]
    for it in report["items"]:
        lines.append(
            f"| {it['question_id']} | {it['recall_at_k']} | "
            f"{'yes' if it['grounded_pass'] else 'no'} | {it['latency_ms']} | "
            f"{'✅' if it['passed'] else '❌'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    import sys

    report = asyncio.run(run_evaluation())
    markdown = to_markdown(report)
    print(markdown)

    out_dir = Path(__file__).resolve().parents[3] / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "evaluation_report.md").write_text(markdown, encoding="utf-8")
    (out_dir / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Reports written to {out_dir}")
    sys.exit(0 if report["summary"]["passed"] else 1)


if __name__ == "__main__":
    main()
