# Garmin MCP — convenience targets (last verified: 2026-04-17)

.PHONY: up down logs test lint format sync backup shell validate

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	@if [ -f .venv/bin/python ]; then .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing; else python3 -m pytest tests/ -v --cov=src; fi

lint:
	@if [ -f .venv/bin/ruff ]; then .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests; else ruff check src tests && ruff format --check src tests; fi

format:
	@if [ -f .venv/bin/ruff ]; then .venv/bin/ruff format src tests; else ruff format src tests; fi

sync:
	.venv/bin/python scripts/sync_all.py

backup:
	curl -sS -X POST -H "X-API-Key: $${GARMIN_API_KEY}" http://127.0.0.1:8765/backup/all || (echo "Set GARMIN_API_KEY and ensure server is running (make up)"; exit 1)

shell:
	docker compose exec garmin-mcp bash

validate:
	TUNNEL_TOKEN=dummy docker compose config
	@if [ -f .venv/bin/python ]; then .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from config import load_config; load_config('config.yaml'); print('config ok')"; else python3 -c "import sys; sys.path.insert(0,'src'); from config import load_config; load_config('config.yaml'); print('config ok')"; fi
