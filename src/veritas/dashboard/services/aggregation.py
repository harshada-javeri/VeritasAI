"""Shared, portable aggregation helpers (histograms, percentiles).

Lives in the service layer because these computations cannot be expressed
portably in SQL across SQLite and Postgres (see the query audit). Repositories
return raw/bucketed rows; these functions finish the math.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from veritas.dashboard.repositories.rows import CheckHistogramBin, HistogramBin
from veritas.dashboard.viewmodels.common import DistributionBin, DistributionVM

_BINS = 10


def build_distribution(label: str, bins: Iterable[HistogramBin]) -> DistributionVM:
    """Fold integer buckets (0..10) into ten [0,1] bins; bucket 10 merges into 9."""
    counts = [0] * _BINS
    for b in bins:
        index = min(b.bucket, _BINS - 1)
        if 0 <= index < _BINS:
            counts[index] += b.count
    total = sum(counts)
    if total == 0:
        return DistributionVM(label=label, bins=(), total=0)
    rendered = tuple(
        DistributionBin(lower=i / _BINS, upper=(i + 1) / _BINS, count=counts[i])
        for i in range(_BINS)
    )
    return DistributionVM(label=label, bins=rendered, total=total)


def group_check_histograms(rows: Iterable[CheckHistogramBin]) -> dict[str, list[HistogramBin]]:
    grouped: dict[str, list[HistogramBin]] = {}
    for row in rows:
        grouped.setdefault(row.check_name, []).append(
            HistogramBin(bucket=row.bucket, count=row.count)
        )
    return grouped


def percentile(values: Sequence[int], q: float) -> int:
    """Linear-interpolation percentile (``q`` in [0,1]); 0 for an empty input."""
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = q * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    frac = rank - low
    return round(ordered[low] * (1 - frac) + ordered[high] * frac)
