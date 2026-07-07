.PHONY: up down logs test health

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm backend pytest

health:
	curl -sf http://localhost:8000/health | python3 -m json.tool
