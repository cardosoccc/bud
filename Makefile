.PHONY: venv setup install build test watch lint clean

PYTHON := python3
UV := uv

venv:
	$(UV) venv

setup: venv
	$(UV) sync

install:
	$(UV) tool install .

build:
	docker compose build

test:
	$(UV) run pytest tests/ -v

watch:
	$(UV) run uvicorn bud.main:app --reload --host 0.0.0.0 --port 8000

lint:
	$(UV) run ruff check bud/
	$(UV) run ruff format --check bud/

clean:
	rm -rf .venv __pycache__ dist build .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete

migrate:
	$(UV) run alembic upgrade head

migrations:
	$(UV) run alembic revision --autogenerate -m "$(msg)"

up:
	docker compose up -d

down:
	docker compose down
