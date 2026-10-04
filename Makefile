.PHONY: dev test test-runtime lint e2e migrate install
install:
	python -m pip install -r requirements.lock
	python -m pip install -e . --no-deps
	cd apps/web && npm ci

dev:
	docker compose up --build

test:
	python -m pytest -q

test-runtime:
	cd runtimes && npm ci && node --test tests/*.test.cjs
	python infra/scripts/report_contract.py

lint:
	ruff check .
	ruff format --check .
	cd apps/web && npm run typecheck

migrate:
	docker compose run --rm init

e2e:
	python infra/scripts/e2e.py
