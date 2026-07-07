.PHONY: up down logs test health seed-sample eval

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm backend pytest tests ingestion/tests

health:
	curl -sf http://localhost:8000/health | python3 -m json.tool

seed-sample:
	docker compose run --rm backend python -m ingestion.pipeline.run

eval:
	docker compose run --rm backend python -m app.eval.runner
