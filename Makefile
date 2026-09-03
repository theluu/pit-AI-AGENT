.PHONY: install dev test lint up down eval
install:
	python -m pip install -e '.[dev]'
dev:
	uvicorn agentops.api:app --reload
test:
	pytest -q
lint:
	ruff check .
up:
	docker compose up -d --build
down:
	docker compose down
eval:
	curl -s -X POST http://localhost:8000/api/v1/evaluation-runs

