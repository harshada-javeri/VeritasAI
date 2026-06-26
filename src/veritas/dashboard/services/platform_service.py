"""Builds the Platform Health view-model (processing telemetry that exists today)."""

from __future__ import annotations

from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.trace_repository import TraceRepository
from veritas.dashboard.repositories.verdict_repository import VerdictRepository
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.services.aggregation import percentile
from veritas.dashboard.viewmodels.common import Bucket, HighlightVM, Sparkline, TableSizeVM
from veritas.dashboard.viewmodels.platform import LatencyVM, PlatformHealthVM

_UNAVAILABLE = (
    "V1 shows LLM latency only (rule-stage timing is not recorded). Provider "
    "failure rate, alert history, per-stage latency, and storage-growth trends "
    "require V2 data contracts (provider-call + metrics-history persistence)."
)


class PlatformService:
    def __init__(
        self,
        verdicts: VerdictRepository,
        traces: TraceRepository,
        events: EventRepository,
    ) -> None:
        self._verdicts = verdicts
        self._traces = traces
        self._events = events

    def build(self) -> PlatformHealthVM:
        latency_rows = self._verdicts.latency_by_model()
        throughput_rows = self._traces.throughput()
        storage = (
            TableSizeVM(table="events_clean", rows=self._events.count()),
            TableSizeVM(table="quality_verdicts", rows=self._verdicts.count()),
            TableSizeVM(table="trace_logs", rows=self._traces.count()),
        )
        is_empty = all(t.rows == 0 for t in storage)

        latency = tuple(
            LatencyVM(
                model=m.model,
                p50_ms=percentile(m.values, 0.50),
                p90_ms=percentile(m.values, 0.90),
                p99_ms=percentile(m.values, 0.99),
                count=len(m.values),
                display=(
                    f"p50 {fmt.latency_ms(percentile(m.values, 0.50))} · "
                    f"p90 {fmt.latency_ms(percentile(m.values, 0.90))} · "
                    f"p99 {fmt.latency_ms(percentile(m.values, 0.99))}"
                ),
            )
            for m in latency_rows
        )

        stage_volume = self._stage_volume()

        return PlatformHealthVM(
            is_empty=is_empty,
            latency=latency,
            latency_trend=self._latency_trend(),
            throughput=Sparkline(
                points=tuple(float(d.count) for d in throughput_rows),
                labels=tuple(d.day for d in throughput_rows),
            ),
            storage=storage,
            stage_volume=stage_volume,
            unavailable_note=_UNAVAILABLE,
            highlights=self._highlights(latency, stage_volume),
        )

    @staticmethod
    def _highlights(
        latency: tuple[LatencyVM, ...], stage_volume: tuple[Bucket, ...]
    ) -> tuple[HighlightVM, ...]:
        """Scannable headlines derived from data already computed above."""
        measured = [m for m in latency if m.count > 0]
        slowest = max(measured, key=lambda m: m.p90_ms, default=None)
        fastest = min(measured, key=lambda m: m.p90_ms, default=None)
        worst_tail = max(measured, key=lambda m: m.p99_ms, default=None)
        busiest = max(stage_volume, key=lambda b: b.count, default=None)
        return (
            HighlightVM(
                label="Slowest model (p90)",
                value=slowest.model if slowest else "—",
                detail=fmt.latency_ms(slowest.p90_ms) if slowest else "no LLM telemetry",
            ),
            HighlightVM(
                label="Fastest model (p90)",
                value=fastest.model if fastest else "—",
                detail=fmt.latency_ms(fastest.p90_ms) if fastest else "no LLM telemetry",
            ),
            HighlightVM(
                label="Worst tail (p99)",
                value=worst_tail.model if worst_tail else "—",
                detail=fmt.latency_ms(worst_tail.p99_ms) if worst_tail else "no LLM telemetry",
            ),
            HighlightVM(
                label="Highest-volume stage",
                value=busiest.label if busiest else "—",
                detail=f"{busiest.count:,} traces" if busiest else "no traces",
            ),
        )

    def _stage_volume(self) -> tuple[Bucket, ...]:
        rows = self._traces.count_by_stage()
        total = sum(r.count for r in rows) or 1
        return tuple(
            Bucket(label=r.stage, count=r.count, rate=r.count / total) for r in rows
        )

    def _latency_trend(self) -> Sparkline:
        samples = self._verdicts.latency_samples_by_day()
        by_day: dict[str, list[int]] = {}
        for day, value in samples:
            by_day.setdefault(day, []).append(value)
        days = sorted(by_day)
        return Sparkline(
            points=tuple(float(percentile(by_day[day], 0.90)) for day in days),
            labels=tuple(days),
        )
