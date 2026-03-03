.PHONY: venv setup build test watch lint clean auto-update-install auto-update-uninstall auto-update-status

PYTHON := python3
UV := uv

venv:
	$(UV) venv

setup: venv
	$(UV) sync

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

auto-update-install:
	mkdir -p $(HOME)/.config/systemd/user
	cp scripts/bud-auto-update.service $(HOME)/.config/systemd/user/
	cp scripts/bud-auto-update.timer $(HOME)/.config/systemd/user/
	systemctl --user daemon-reload
	systemctl --user enable --now bud-auto-update.timer
	@echo "auto-update timer installed and started"

auto-update-uninstall:
	systemctl --user disable --now bud-auto-update.timer || true
	rm -f $(HOME)/.config/systemd/user/bud-auto-update.service
	rm -f $(HOME)/.config/systemd/user/bud-auto-update.timer
	systemctl --user daemon-reload
	@echo "auto-update timer removed"

auto-update-status:
	systemctl --user status bud-auto-update.timer
	@echo "---"
	systemctl --user list-timers bud-auto-update.timer
