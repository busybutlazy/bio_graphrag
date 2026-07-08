# Biology GraphRAG Tutor

Domain-specific GraphRAG system for high-school biology. See `docs/graph_plan.md` for the full project plan and phase breakdown, `schema/` for the graph/DB schema, and `docs/api_contract.md` for the API contract.

## Quick Start

```bash
cp .env.example .env
make up
make health
make seed-sample
# then open the demo UI:
open http://localhost:8000/        # served by the FastAPI backend
```

`make seed-sample` runs the ingestion pipeline: parses the sample source files, validates them, embeds chunks, and loads Neo4j (44 nodes / 84 relationships), Qdrant (`biology_chunks` collection), and PostgreSQL (`documents`/`chunks`/`ingestion_jobs`) — safe to re-run.

## Demo UI

A static single-page UI (vanilla HTML/CSS/JS, no build step) is served by the backend at `http://localhost:8000/` — every screen is backed by a real endpoint, over the actual sample endocrine graph. The visual system reuses a supplied design handoff (本草 HONZŌ). Five screens:

| Screen | Endpoint(s) | What it shows |
|---|---|---|
| **問答 Chat** | `POST /query` | Hybrid retrieval Q&A: grounded answer + citation chips + supporting nodes + relationships. Deep-link a question: `/?ask=...#chat` |
| **圖譜 Graph** | `GET /neighbors`, `POST /concept-map` | Force-directed subgraph of a node or topic; click a node for detail. Deep-link: `/?node=hormone:insulin#graph` |
| **典藏 Library** | `GET /library` | Approved nodes grouped by topic; click through to the graph |
| **審訂 Curation** | `GET/POST /admin/curation/*` | Human-in-the-loop: propose a node/edge → review queue → approve/reject into the graph |
| **評估 Evaluation** | `GET /admin/evaluation/latest` | Live recall@k / grounded / P95-latency dashboard over the golden questions |

With no `OPENAI_API_KEY` the demo runs fully offline (lexical retrieval + an extractive, clearly-labelled answer), so a fresh clone works with no secrets.

![Chat](docs/screenshots/chat.png)
![Graph](docs/screenshots/graph.png)
![Library](docs/screenshots/library.png)
![Evaluation](docs/screenshots/evaluation.png)

## API

All request limits (question length, `top_k`, `graph_depth`, returned nodes/chunks) are enforced by request validation — oversized params return `422`. There is no arbitrary-Cypher or bulk-export endpoint. See `docs/api_contract.md` for full schemas.

```bash
# Hybrid retrieval Q&A (vector search + graph expansion + grounded answer)
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" \
  -d '{"question":"胰島素如何降低血糖?","top_k":5,"graph_depth":1}'

# Single approved node
curl "http://localhost:8000/nodes/interaction:insulin_glucagon_blood_glucose"

# Local subgraph
curl "http://localhost:8000/neighbors/hormone:insulin?depth=1"

# Concept map from node ids or a topic
curl -X POST http://localhost:8000/concept-map -H "Content-Type: application/json" \
  -d '{"topic":"blood_glucose_regulation","depth":1}'

# Check a student's answer for misconceptions
curl -X POST http://localhost:8000/check-answer -H "Content-Type: application/json" \
  -d '{"question":"血糖如何調節?","student_answer":"胰島素降低血糖,升糖素提高血糖。"}'
```

`/query` and `/check-answer` call an LLM through a provider-agnostic gateway (`app/llm/gateway.py`). With `OPENAI_API_KEY` set, retrieval uses OpenAI embeddings + chat; **without a key the demo runs fully offline** — lexical bigram retrieval plus an extractive, clearly-labelled answer — so a fresh clone works with no secrets.

Retrieval only ever reads `status = 'approved'` nodes/edges. New nodes/edges go through human curation first:

```bash
curl -X POST http://localhost:8000/admin/curation/items \
  -H "Content-Type: application/json" \
  -d '{"item_type":"node","action":"create","payload":{"id":"hormone:example","type":"Hormone","label":"Example","description":"..."},"reason":"why"}'

curl -X POST http://localhost:8000/admin/curation/items/curation:hormone:example/approve \
  -H "Content-Type: application/json" -d '{"reviewer":"you","reason":"looks correct"}'
```

Every approve/reject/merge/delete is recorded in `graph_change_logs` with actor, action, and reason.

### Securing `/admin`

The `/admin/*` endpoints (curation + evaluation) accept a named API key. Configure keys as a comma-separated `vendor:key` list:

```bash
# .env
ADMIN_API_KEYS=acme:key1,globex:key2
```

Requests must then send `X-API-Key: key1`; the matched vendor name is attributed to the action. **When `ADMIN_API_KEYS` is empty (the default) auth is disabled**, so a fresh clone and the test suite run open — set it in any exposed deployment. The demo UI reads its key from `localStorage.setItem('adminApiKey', '<key>')`.

> Per-vendor accounts with usage quotas and expiry are intentionally out of scope for this demo (physical DB isolation and rate limiting are deferred); the named-key gate is the minimal control that keeps the destructive graph-mutation endpoints from being open to anyone who can reach the API.

## Tests

```bash
make test
```

## Evaluation

```bash
make eval
```

Replays 22 golden questions (`data/sample/sample_questions.json`) through the
`/query` retrieval pipeline and scores retrieval recall@k, grounded-answer pass
rate, and latency against fixed thresholds (recall@5 ≥ 0.8, grounded ≥ 0.75, P95
≤ 5s). Results persist to `evaluation_runs`/`evaluation_items` and a Markdown/JSON
report; the command gates on the thresholds so it can run in CI. Methodology and
an honest reading of the numbers are in `docs/evaluation.md`.

## Project Layout

- `backend/` — FastAPI service
- `ingestion/` — ingestion pipeline (parse → normalize → build chunks → embed → load Neo4j/Qdrant/Postgres)
- `schema/` — Neo4j node/relationship types, DB schema, LLM extraction guidelines
- `prompts/` — LLM extraction prompt templates
- `docs/` — project plan and API contract
- `scripts/` — helper scripts (`wait_for_services.sh`)
- `data/sample/` — sample hormone-regulation concepts/edges/documents/chunks JSON
