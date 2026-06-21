"""Tests for the configurable dataset discovery layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from veritas.ingest.discovery import (
    DatasetMissingError,
    DatasetNotConfiguredError,
    discover_dataset_files,
)

FEED_ROOT = Path(__file__).parent / "fixtures" / "feed"


def test_recursive_discovery_finds_jsonl_and_nested_ndjson() -> None:
    files = discover_dataset_files(FEED_ROOT)
    names = {path.name for path in files}
    assert names == {"part_a.jsonl", "part_b.ndjson"}


def test_non_recursive_excludes_nested_directories() -> None:
    files = discover_dataset_files(FEED_ROOT, recursive=False)
    assert {path.name for path in files} == {"part_a.jsonl"}


def test_pattern_filtering_is_respected() -> None:
    files = discover_dataset_files(FEED_ROOT, patterns=("*.ndjson",))
    assert {path.name for path in files} == {"part_b.ndjson"}


def test_results_are_sorted_and_deduplicated() -> None:
    # Overlapping patterns must not yield the same file twice.
    files = discover_dataset_files(FEED_ROOT, patterns=("*.jsonl", "*.jsonl"))
    assert files == sorted(files)
    assert len(files) == len(set(files))


def test_unconfigured_root_raises() -> None:
    with pytest.raises(DatasetNotConfiguredError):
        discover_dataset_files(None)


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(DatasetMissingError):
        discover_dataset_files(tmp_path / "does-not-exist")


def test_file_as_root_raises(tmp_path: Path) -> None:
    target = tmp_path / "feed.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(DatasetMissingError):
        discover_dataset_files(target)
