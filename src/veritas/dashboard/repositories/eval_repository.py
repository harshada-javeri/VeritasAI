"""Access to the offline eval harness (packaged fixtures — not the database).

Wraps ``evals/`` so the judge-performance service never touches async itself.
Cost is independent of DB size; the constraint is statistical (small ``n``).
"""

from __future__ import annotations

import asyncio

from veritas.config import Settings, get_settings
from veritas.evals import (
    ComparisonResult,
    EvalResult,
    available_prompt_versions,
    compare_prompts,
    list_datasets,
    run_dataset,
)


class EvalRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings if settings is not None else get_settings()

    def datasets(self) -> list[str]:
        return list_datasets()

    def prompt_versions(self, dataset: str) -> list[str]:
        return available_prompt_versions(dataset)

    def scorecard(self, dataset: str, prompt_version: str) -> EvalResult:
        return asyncio.run(run_dataset(dataset, prompt_version))

    def compare(
        self, dataset: str, baseline_version: str, candidate_version: str
    ) -> ComparisonResult:
        threshold = self._settings.evals.regression_threshold
        return asyncio.run(
            compare_prompts(dataset, baseline_version, candidate_version, threshold)
        )
