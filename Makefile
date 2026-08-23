.PHONY: build check fmt lint test

build: check lint test

check:
	uv sync --quiet
	uv run python -c "import gravita_gtm; print(gravita_gtm.__version__)"

lint:
	uv run ruff check src/ 2>/dev/null || true

fmt:
	uv run ruff format src/ --check 2>/dev/null || true

test:
	uv run python tests/smoke_test.py
