"""Tests for the versioned prompt registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from veritas.prompt_registry import PromptNotFoundError, PromptRegistry


def test_default_registry_loads_shipped_prompts() -> None:
    registry = PromptRegistry.default()
    assert {"semantic_accuracy", "source_credibility", "entity_resolution"} <= set(registry.names())
    spec = registry.get("semantic_accuracy")
    assert spec.owner == "data-quality-team"
    assert spec.model.startswith("claude")
    assert spec.output_schema == "judge_output"
    assert spec.version == "v1"
    assert spec.system is not None


def test_entity_resolution_pins_sonnet() -> None:
    spec = PromptRegistry.default().get("entity_resolution")
    assert spec.model == "claude-sonnet-4-6"


def test_render_substitutes_placeholders() -> None:
    spec = PromptRegistry.default().get("semantic_accuracy")
    rendered = spec.render(
        {"category": "launches", "summary": "X launches Y", "article_sentence": "X launched Y."}
    )
    assert "launches" in rendered
    assert "$category" not in rendered


def test_get_unknown_prompt_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        PromptRegistry.default().get("does_not_exist")


def test_get_unknown_version_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        PromptRegistry.default().get("semantic_accuracy", "v99")


def test_from_directory(tmp_path: Path) -> None:
    (tmp_path / "p.yaml").write_text(
        "name: p\nversion: v1\nowner: me\n"
        "model: claude-haiku-4-5-20251001\nschema: judge_output\ntemplate: 'hi $x'\n",
        encoding="utf-8",
    )
    registry = PromptRegistry.from_directory(tmp_path)
    assert registry.get("p").render({"x": "there"}) == "hi there"
