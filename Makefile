SHELL := /bin/bash
PYTHON ?= python3.12
VENV ?= .venv
VENV_BIN := $(VENV)/bin
BACKEND_DIR := backend
FRONTEND_DIR := frontend
COMPOSE ?= docker compose

.PHONY: help setup install backend-install frontend-install backend-dev frontend-dev seed lint lint-backend lint-frontend format format-backend format-frontend test docker-up docker-up-infra docker-down docker-logs clean

$(VENV_BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip

setup: $(VENV_BIN)/python ## Create local virtual environment and upgrade pip

backend-install: $(VENV_BIN)/python ## Install backend runtime and dev dependencies into the virtualenv
	$(VENV_BIN)/pip install -e $(BACKEND_DIR)[dev]

frontend-install: ## Install frontend dependencies with Yarn
	cd $(FRONTEND_DIR) && yarn install --frozen-lockfile

install: backend-install frontend-install ## Install backend and frontend dependencies

backend-dev: backend-install ## Run backend API in reload mode
	cd $(BACKEND_DIR) && ../$(VENV_BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev: frontend-install ## Run Next.js frontend in dev mode
	cd $(FRONTEND_DIR) && yarn dev

seed: backend-install ## Load demo tenants, documents, tasks, and incidents
	cd $(BACKEND_DIR) && ../$(VENV_BIN)/python -m app.scripts.seed_data --reset

lint-backend: backend-install ## Run Python linters via ruff
	$(VENV_BIN)/ruff check $(BACKEND_DIR)

lint-frontend: frontend-install ## Run frontend linting
	cd $(FRONTEND_DIR) && yarn lint

lint: lint-backend lint-frontend ## Run all linters

format-backend: backend-install ## Format Python code with ruff
	$(VENV_BIN)/ruff format $(BACKEND_DIR)

format-frontend: frontend-install ## Fix lint issues in the frontend
	cd $(FRONTEND_DIR) && yarn lint --fix

format: format-backend format-frontend ## Format backend and frontend code

test: backend-install ## Execute backend test suite
	cd $(BACKEND_DIR) && ../$(VENV_BIN)/pytest

docker-up-infra: ## Start only supporting services (Postgres, Redis, Qdrant)
	$(COMPOSE) up -d postgres redis qdrant

docker-up: ## Start full stack (backend + frontend + infra)
	$(COMPOSE) up -d

docker-down: ## Stop and remove containers, networks, and volumes
	$(COMPOSE) down

docker-logs: ## Tail logs from backend and frontend containers
	$(COMPOSE) logs -f backend frontend

clean: ## Remove virtualenv, Node modules, and cached build artefacts
	rm -rf $(VENV) \
		$(FRONTEND_DIR)/node_modules \
		$(FRONTEND_DIR)/.next \
		$(BACKEND_DIR)/__pycache__ \
		$(BACKEND_DIR)/.pytest_cache \
		$(BACKEND_DIR)/*.egg-info

help: ## List available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
