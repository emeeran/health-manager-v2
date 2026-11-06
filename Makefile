BACKEND := backend
UV      := uv
VERSION := $(shell grep -m1 '^version' $(BACKEND)/pyproject.toml | sed 's/version = "\(.*\)"/\1/')

.PHONY: help setup sync-version test coverage e2e lint run clean

help:
	@echo ""
	@echo "  health-manager-v2"
	@echo "  ─────────────────────────────────────────"
	@echo "  make setup        Install / sync backend deps"
	@echo "  make sync-version Sync version (pyproject.toml) to frontend + desktop"
	@echo "  make test         Backend tests + frontend tests"
	@echo "  make coverage     Tests with coverage ratchets enforced"
	@echo "  make e2e          Playwright suite (spins up both dev servers)"
	@echo "  make lint         Ruff + mypy + eslint + tsc"
	@echo "  make run          Start dev servers (same as ./dev.sh)"
	@echo "  make clean        Remove caches"
	@echo ""

setup:
	cd $(BACKEND) && $(UV) sync
	cd frontend && npm ci

sync-version:
	packaging/sync-version.sh

test:
	cd $(BACKEND) && $(UV) run pytest -q
	cd frontend && npm test

coverage:
	cd $(BACKEND) && $(UV) run pytest -q --cov=app --cov-report=term-missing --cov-fail-under=88
	cd frontend && npm test -- --coverage

e2e:
	cd frontend && npx playwright test

lint:
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run mypy app/
	cd frontend && npm run lint && npx tsc --noEmit

run:
	./dev.sh

clean:
	find . -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" \) -exec rm -rf {} + 2>/dev/null || true
