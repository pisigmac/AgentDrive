.PHONY: install test lint format clean

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=vault --cov-report=html

lint:
	ruff check vault/
	black --check --target-version py311 vault/

format:
	ruff check --fix vault/
	black --target-version py311 vault/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	python -m build

publish:
	python -m twine upload dist/*
