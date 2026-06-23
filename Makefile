.PHONY: eval test lint typecheck check

# Run the evaluation harness (replay-only; no live model calls).
# Prints summary metrics, worst failures, and a regression report; exits
# non-zero if a tracked metric regressed beyond the configured threshold.
eval:
	uv run python -m veritas.evals

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy

check: lint typecheck test
