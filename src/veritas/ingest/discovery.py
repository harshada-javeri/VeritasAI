"""Configurable dataset discovery.

The dataset location is supplied via configuration (``DATASET_ROOT``); nothing
here knows a concrete path. Discovery walks the root for the configured glob
patterns (``*.jsonl``, ``*.ndjson`` by default), recursing into nested
directories, and fails *loudly but cleanly* when the root is unset or missing —
callers translate these exceptions into a graceful message rather than a stack
trace.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

DEFAULT_PATTERNS: tuple[str, ...] = ("*.jsonl", "*.ndjson")


class DatasetError(Exception):
    """Base class for dataset discovery failures."""


class DatasetNotConfiguredError(DatasetError):
    """``DATASET_ROOT`` was not provided."""


class DatasetMissingError(DatasetError):
    """``DATASET_ROOT`` was provided but does not point at a readable directory."""


def discover_dataset_files(
    root: Path | None,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
    *,
    recursive: bool = True,
) -> list[Path]:
    """Return the sorted, de-duplicated list of feed files under ``root``.

    Args:
        root: The dataset root, typically ``Settings.dataset_root``. ``None``
            means it was never configured.
        patterns: Filename glob patterns to match.
        recursive: Walk nested directories when ``True``.

    Returns:
        A sorted list of matching files. An empty list means the root exists but
        contains no matching files — the caller decides whether that is fatal.

    Raises:
        DatasetNotConfiguredError: ``root`` is ``None``.
        DatasetMissingError: ``root`` does not exist or is not a directory.
    """
    if root is None:
        raise DatasetNotConfiguredError(
            "DATASET_ROOT is not set. Provide it via the environment or a .env file."
        )
    if not root.exists():
        raise DatasetMissingError(f"Dataset root does not exist: {root}")
    if not root.is_dir():
        raise DatasetMissingError(f"Dataset root is not a directory: {root}")

    matches: set[Path] = set()
    for pattern in patterns:
        found = root.rglob(pattern) if recursive else root.glob(pattern)
        matches.update(path for path in found if path.is_file())
    return sorted(matches)
