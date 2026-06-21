"""Ingest layer: dataset discovery and tolerant JSON:API parsing."""

from veritas.ingest.discovery import (
    DatasetError,
    DatasetMissingError,
    DatasetNotConfiguredError,
    discover_dataset_files,
)
from veritas.ingest.parser import (
    MalformedRecordError,
    iter_dataset,
    iter_records,
    parse_document,
)

__all__ = [
    "DatasetError",
    "DatasetMissingError",
    "DatasetNotConfiguredError",
    "MalformedRecordError",
    "discover_dataset_files",
    "iter_dataset",
    "iter_records",
    "parse_document",
]
