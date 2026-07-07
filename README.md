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

`make seed-sample` loads the sample hormone-regulation graph (44 nodes / 84 relationships — blood glucose, water/osmolarity, calcium, and uterine-contraction feedback loops) into Neo4j.

## Tests

```bash
make test
```

## Project Layout

- `backend/` — FastAPI service
- `schema/` — Neo4j node/relationship types, DB schema, LLM extraction guidelines
- `prompts/` — LLM extraction prompt templates
- `docs/` — project plan and API contract
- `scripts/` — helper scripts (`wait_for_services.sh`, `seed_sample_graph.py`)
- `data/sample/` — sample hormone-regulation concept/edge JSON
