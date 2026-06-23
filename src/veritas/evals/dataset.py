"""Labeled eval datasets and their recorded prediction sets.

A *dataset* is the versioned ground truth for one check (e.g.
``semantic_accuracy_v1``). Its ``predictions/<prompt_version>.json`` files hold
recorded ``Verdict``s for each prompt version, replayed via ``ReplayJudge`` — so
evaluation never calls a live model. Dataset version and prompt version are
orthogonal: hold the dataset fixed, vary the prompt to compare or detect drift.
"""

from __future__ import annotations

import json
import re
from importlib.resources.abc import Traversable
from typing import Any

from pydantic import BaseModel, ConfigDict

from veritas.domain.models import ResolvedEvent, Verdict, VerdictStatus
from veritas.judges.replay import ReplayJudge

try:  # importlib.resources.files lives in different spots across versions
    from importlib.resources import files
except ImportError:  # pragma: no cover
    from importlib_resources import files  # type: ignore[no-redef, import-not-found]

_PACKAGE = "veritas.evals"
_DATASETS_DIR = "datasets"
_VERSION_SUFFIX = re.compile(r"_v\d+$")


class EvalExample(BaseModel):
    """One labeled example: an input event and its gold verdict."""

    model_config = ConfigDict(extra="forbid")

    event: ResolvedEvent
    label: VerdictStatus
    note: str | None = None


class EvalDataset(BaseModel):
    """A versioned labeled set for a single check."""

    model_config = ConfigDict(extra="forbid")

    name: str
    check_name: str
    examples: list[EvalExample]


def check_name_for(dataset_name: str) -> str:
    """``semantic_accuracy_v1`` -> ``semantic_accuracy``."""
    return _VERSION_SUFFIX.sub("", dataset_name)


def _datasets_root() -> Traversable:
    return files(_PACKAGE) / _DATASETS_DIR


def list_datasets() -> list[str]:
    return sorted(entry.name for entry in _datasets_root().iterdir() if entry.is_dir())


def load_dataset(name: str) -> EvalDataset:
    text = (_datasets_root() / name / "dataset.jsonl").read_text(encoding="utf-8")
    examples = [
        EvalExample.model_validate_json(line) for line in text.splitlines() if line.strip()
    ]
    return EvalDataset(name=name, check_name=check_name_for(name), examples=examples)


def available_prompt_versions(name: str) -> list[str]:
    predictions = _datasets_root() / name / "predictions"
    return sorted(
        entry.name.removesuffix(".json")
        for entry in predictions.iterdir()
        if entry.name.endswith(".json")
    )


def load_predictions(name: str, prompt_version: str) -> dict[str, Verdict]:
    path = _datasets_root() / name / "predictions" / f"{prompt_version}.json"
    rows: Any = json.loads(path.read_text(encoding="utf-8"))
    verdicts = [Verdict.model_validate(row) for row in rows]
    return {verdict.event_id: verdict for verdict in verdicts}


def build_replay_judge(name: str, prompt_version: str) -> ReplayJudge:
    """A ReplayJudge that serves the recorded predictions for this prompt version."""
    return ReplayJudge(check_name_for(name), load_predictions(name, prompt_version))
