# ContextForge developer workflow.
#
# Uses a project-local virtualenv at backend/.venv (Python 3.14+) and the
# frontend's own node_modules. `make install` sets both up from scratch.

PYTHON ?= python3
PY      := backend/.venv/bin/python
PIP     := backend/.venv/bin/pip
RUFF    := backend/.venv/bin/ruff
NPM     := npm --prefix frontend

.PHONY: help install lint lint-backend lint-frontend format test test-backend \
	test-frontend build dev-backend dev-frontend clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Create the venv and install backend + frontend dependencies
	$(PYTHON) -m venv backend/.venv
	$(PIP) install -U pip
	$(PIP) install -r backend/requirements.txt
	$(PIP) install "ruff>=0.16,<1.0" "pytest>=8,<9" "pytest-asyncio>=0.24,<1.0"
	$(NPM) install

lint: lint-backend lint-frontend ## Run every linter

lint-backend: ## Ruff lint + format check (backend)
	$(RUFF) check backend
	$(RUFF) format --check backend

lint-frontend: ## ESLint + Prettier check (frontend)
	$(NPM) run lint
	$(NPM) run format:check

format: ## Auto-format backend and frontend
	$(RUFF) check backend --fix
	$(RUFF) format backend
	$(NPM) run format

test: test-backend test-frontend ## Run every test suite

test-backend: ## Backend pytest suite
	cd backend && ./.venv/bin/python -m pytest tests/ -q

test-frontend: ## Frontend Vitest suite
	$(NPM) test

build: ## Build the frontend production bundle
	$(NPM) run build

dev-backend: ## Run the FastAPI dev server (port 8000)
	cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run the Vite dev server (port 5173)
	$(NPM) run dev

clean: ## Remove frontend build artifacts
	rm -rf frontend/dist
