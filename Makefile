# Makefile for Weatherbot
.PHONY: help install install-dev test test-cov lint format clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in production mode
	pip install -e .

install-dev: ## Install the package with development dependencies
	pip install -e ".[dev]"

test: ## Run tests
	python -m pytest tests/

test-cov: ## Run tests with coverage
	python -m pytest tests/ --cov=weatherbot --cov-report=html --cov-report=term

lint: ## Run linting
	ruff check src/ tests/
	mypy src/weatherbot

security: ## Run security scans
	bandit -r src/weatherbot
	safety check

format: ## Format code
	black src/ tests/
	ruff check src/ tests/ --fix

clean: ## Clean up build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

pre-commit: ## Install pre-commit hooks
	pre-commit install

run: ## Run weatherbot
	python -m weatherbot run

run-once: ## Run weatherbot once
	python -m weatherbot run --once

test-alert: ## Test alert system
	python -m weatherbot test-alert
