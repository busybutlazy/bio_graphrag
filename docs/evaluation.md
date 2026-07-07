# Evaluation

Phase 5 turns "it runs" into "it runs at a measured quality". The runner
(`backend/app/eval/`) replays a set of golden questions through the exact same
hybrid-retrieval pipeline the `/query` endpoint uses, scores each one, and
persists the run.

## How to run

```bash
make up
make seed-sample
make eval        # docker compose run --rm backend python -m app.eval.runner
```

`make eval` prints a Markdown report, writes `reports/evaluation_report.{md,json}`
(gitignored), persists a row to `evaluation_runs` and one per question to
`evaluation_items`, and exits non-zero if the run fails any threshold — so it can
gate CI. The metrics are also asserted in `tests/integration/test_evaluation.py`.

## Golden questions

`data/sample/sample_questions.json` — 22 questions over the sample endocrine
graph. Each carries the ground truth used for scoring:

| Field | Meaning |
|---|---|
| `expected_chunk_ids` | chunks a correct retrieval must surface (recall) |
| `expected_node_ids` | supporting nodes a grounded answer must include |

## Metrics

- **Recall@k** — fraction of `expected_chunk_ids` present in the top-`k` retrieved
  chunks, averaged over all questions.
- **Grounded pass rate** — fraction of questions whose answer's `supporting_nodes`
  contain every `expected_node_id`. This checks the answer is actually anchored in
  the graph, not just plausible prose.
- **Latency P95 / mean** — wall-clock of the full `answer_query` call per question.

| Metric | Threshold |
|---|---|
| Recall@5 | ≥ 0.80 |
| Grounded pass rate | ≥ 0.75 |
| Latency P95 | ≤ 5000 ms |

A per-question item `passed` only when it both retrieves the right chunk and
grounds the required nodes; failing items are flagged in `evaluation_items` so
low-quality answers are visible, not averaged away.

## Honest reading of the numbers

- The public sample corpus is intentionally small (8 chunks). With `top_k=5` the
  recall metric is easy to satisfy; it is meant to prove the *harness* is correct
  and wired to real retrieval, not to claim a hard benchmark. On a larger private
  graph the same metric becomes genuinely discriminating.
- Without `OPENAI_API_KEY` the pipeline runs in **offline mode**: ingestion used
  deterministic hash embeddings, so retrieval falls back to lexical (character
  bigram) matching and answers are extractive. Numbers under offline mode measure
  the retrieval/grounding harness, not an LLM's answer quality. Set a key to
  evaluate semantic embeddings + generated answers.
