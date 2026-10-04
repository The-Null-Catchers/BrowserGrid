.PHONY: dev test lint e2e migrate install
install:
	python -m pip install -r requirements.lock
	python -m pip install -e . --no-deps
	cd apps/web && npm ci

dev:
	docker compose up --build

test:
	python -m pytest -q

lint:
	ruff check .
	ruff format --check .
	cd apps/web && npm run typecheck

migrate:
	docker compose run --rm init

e2e:
	python infra/scripts/e2e.py
