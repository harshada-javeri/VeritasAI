"""Builds the Platform Health view-model (processing telemetry that exists today)."""

from __future__ import annotations

from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.trace_repository import TraceRepository
from veritas.dashboard.repositories.verdict_repository import VerdictRepository
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.services.aggregation import percentile
from veritas.dashboard.viewmodels.common import Bucket, Sparkline, TableSizeVM
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
