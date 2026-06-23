"""View-models for the Platform Health workspace."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM, Bucket, Sparkline, TableSizeVM


class LatencyVM(VM):
    model: str
    p50_ms: int
    p90_ms: int
    p99_ms: int
    count: int
    display: str


class PlatformHealthVM(VM):
    is_empty: bool
    latency: tuple[LatencyVM, ...] = ()
    latency_trend: Sparkline = Sparkline()
    throughput: Sparkline = Sparkline()
    storage: tuple[TableSizeVM, ...] = ()
    stage_volume: tuple[Bucket, ...] = ()
    unavailable_note: str
