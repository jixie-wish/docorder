.PHONY: quality

quality:
	uv run ruff check src examples
	uv run python examples/hello/run.py
