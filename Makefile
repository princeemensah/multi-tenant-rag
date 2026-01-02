PYTHON ?= python3
PIP ?= pip

.PHONY: setup install test format lint

setup: ## Create local virtual environment
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && $(PIP) install --upgrade pip

install: ## Install backend and frontend dependencies (placeholder)
	@echo "TODO: implement dependency installation"

lint: ## Run linters
	@echo "TODO: add lint command"

test: ## Run automated tests
	@echo "TODO: add test command"

format: ## Run code formatters
	@echo "TODO: add format command"

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
