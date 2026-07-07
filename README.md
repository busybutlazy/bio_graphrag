# Biology GraphRAG Tutor

Domain-specific GraphRAG system for high-school biology. See `docs/graph_plan.md` for the full project plan and phase breakdown, `schema/` for the graph/DB schema, and `docs/api_contract.md` for the API contract.

## Quick Start

```bash
cp .env.example .env
make up
make health
make seed-sample
curl "http://localhost:8000/neighbors/hormone:insulin?depth=1"
```

`make seed-sample` runs the ingestion pipeline: parses the sample source files, validates them, embeds chunks, and loads Neo4j (44 nodes / 84 relationships), Qdrant (`biology_chunks` collection), and PostgreSQL (`documents`/`chunks`/`ingestion_jobs`) — safe to re-run.

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

## Tests

```bash
make test
```

## Project Layout

- `backend/` — FastAPI service
- `ingestion/` — ingestion pipeline (parse → normalize → build chunks → embed → load Neo4j/Qdrant/Postgres)
- `schema/` — Neo4j node/relationship types, DB schema, LLM extraction guidelines
- `prompts/` — LLM extraction prompt templates
- `docs/` — project plan and API contract
- `scripts/` — helper scripts (`wait_for_services.sh`)
- `data/sample/` — sample hormone-regulation concepts/edges/documents/chunks JSON
