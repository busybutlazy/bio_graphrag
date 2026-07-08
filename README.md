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

### Per-company access & token quotas

The token-spending tutor endpoints (`POST /query`, `POST /check-answer`) are gated per company so a shared demo can't burn tokens uncontrolled. Browsing (library / graph / node detail) stays open — no login needed.

- **Closed by default.** With no account (or an unknown/expired/disabled/over-quota key) the token endpoints return a structured error and stay closed. There is no "open when unconfigured" fallback — safe for a public deployment.
- Accounts live in the `vendors` table, hand-maintained via a small CLI:

  ```bash
  docker compose exec backend python -m scripts.manage_vendors \
      add --code acme --name "Acme Corp" --quota 50000 --expires 2026-08-01
  docker compose exec backend python -m scripts.manage_vendors list      # api_key shown masked
  docker compose exec backend python -m scripts.manage_vendors update --code acme --quota 100000
  docker compose exec backend python -m scripts.manage_vendors disable --code acme
  ```

  `--quota` is required (non-negative integer; `0` = no token access). The `api_key` is auto-generated and printed once on `add`; give it to the company. Usage (embedding + completion tokens) is tallied per request in `vendor_usage` and checked against the quota; the quota is a **soft cap** — it is checked at the *start* of a request, so both concurrent requests and the single request that crosses the threshold can overshoot by up to roughly one request's worth of tokens.
- Companies log in from the header control (the key is sent as `X-API-Key`, stored in `localStorage`). Errors use `{"error": {"code", "message"}}` — the UI maps `login_required` / `quota_exceeded` / `account_expired` / `account_disabled` to a prompt while browsing keeps working.

> These are **demo-grade access keys**: `api_key` is stored in plaintext and the `X-API-Key` header is never written to logs, but this is not a production credential store (no hashing, rotation, or per-vendor rate limiting). Per-vendor accounts here replace the earlier "deferred" note; hardening the store remains future work.
>
> The vendor key is a **low-value, disposable credential** (worst case if leaked: that company's token quota is spent — it cannot mutate the graph or reach `/admin`). A static SPA must keep the key somewhere its own JS can read, so making it un-stealable would require a server-side session layer that is out of scope here. The security posture is therefore **blast-radius control, not prevention** — the per-vendor quota, expiry, and `disable` switch bound the damage — plus **enabling TLS on any exposed deployment** so the header isn't sniffable in transit.

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
