"""Loading and resolving versioned prompt specs.

Prompts live as ``*.yaml`` files (one spec each). The registry indexes by
``(name, version)`` and tracks the highest version per name as the default, so
``get(name)`` returns latest and ``get(name, version)`` pins exactly.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from veritas.prompt_registry.spec import PromptSpec

_PROMPTS_PACKAGE = "veritas.prompt_registry"
_PROMPTS_DIR = "prompts"


class PromptNotFoundError(KeyError):
    """No prompt registered under the requested name/version."""


class PromptRegistry:
    def __init__(self, specs: Iterable[PromptSpec]) -> None:
        self._by_key: dict[tuple[str, str], PromptSpec] = {}
        self._latest: dict[str, PromptSpec] = {}
        for spec in specs:
            self._add(spec)

    def _add(self, spec: PromptSpec) -> None:
        self._by_key[(spec.name, spec.version)] = spec
        current = self._latest.get(spec.name)
        if current is None or spec.version > current.version:
            self._latest[spec.name] = spec

    def get(self, name: str, version: str | None = None) -> PromptSpec:
        if version is None:
            try:
                return self._latest[name]
            except KeyError:
                raise PromptNotFoundError(f"no prompt named {name!r}") from None
        try:
            return self._by_key[(name, version)]
        except KeyError:
            raise PromptNotFoundError(f"no prompt {name!r} at version {version!r}") from None

    def names(self) -> list[str]:
        return sorted(self._latest)

    @staticmethod
    def _parse(text: str) -> PromptSpec:
        raw: Any = yaml.safe_load(text)
        return PromptSpec.model_validate(raw)

    @classmethod
    def from_directory(cls, directory: Path) -> PromptRegistry:
        paths = sorted(directory.glob("*.yaml"))
        return cls([cls._parse(path.read_text(encoding="utf-8")) for path in paths])

    @classmethod
    def default(cls) -> PromptRegistry:
        """Load the prompts packaged with VeritasAI."""
        resource = files(_PROMPTS_PACKAGE) / _PROMPTS_DIR
        specs: list[PromptSpec] = []
        for entry in sorted(resource.iterdir(), key=lambda item: item.name):
            if entry.name.endswith(".yaml"):
                specs.append(cls._parse(entry.read_text(encoding="utf-8")))
        return cls(specs)
