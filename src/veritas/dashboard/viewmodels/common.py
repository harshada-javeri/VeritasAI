"""Shared view-model atoms used across every workspace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Trend = Literal["up", "down", "flat"]
Severity = Literal["trusted", "caution", "blocked"]


class VM(BaseModel):
    """Base for every view-model: immutable and closed."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Sparkline(VM):
    """A small ordered series for trend-in-context rendering."""

    points: tuple[float, ...] = ()
    labels: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return len(self.points) == 0


class Delta(VM):
    """A signed change against an explicit baseline.

    ``is_improvement`` is semantic, not directional: a falling cost is an
    improvement even though its direction is ``down``.
    """

    value: float
    direction: Trend
    vs_baseline: str
    is_improvement: bool
    display: str


class Bucket(VM):
    """A labelled count with its share of the whole."""

    label: str
    count: int
    rate: float


class Band(VM):
    """A severity verdict with a human-readable cause."""

    severity: Severity
    reason: str


class MetricVM(VM):
    """A single headline metric: value + formatted display + optional trend."""

    label: str
    value: float
    display: str
    unit: str = ""
    spark: Sparkline | None = None
    delta: Delta | None = None


class MoneyVM(VM):
    value_usd: float
    display: str


class RateVM(VM):
    value: float
    display: str
    note: str | None = None


class DistributionBin(VM):
    lower: float
    upper: float
    count: int


class DistributionVM(VM):
    """A binned distribution (e.g. confidence). Empty when nothing was measured."""

    label: str
    bins: tuple[DistributionBin, ...] = ()
    total: int = 0

    @property
    def is_empty(self) -> bool:
        return self.total == 0


class SeriesPoint(VM):
    label: str
    value: float


class NamedSeries(VM):
    """A named series for small-multiples (e.g. one rule's failure trend)."""

    name: str
    points: tuple[SeriesPoint, ...] = ()


class TableSizeVM(VM):
    table: str
    rows: int


class HighlightVM(VM):
    """A reusable executive emphasis card: label + big value + supporting detail."""

    label: str
    value: str
    detail: str
