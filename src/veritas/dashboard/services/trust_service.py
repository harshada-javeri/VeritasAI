"""Builds the Trust Center view-model (snapshot-first, transparent index)."""

from __future__ import annotations

from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.rows import DayCount
from veritas.dashboard.repositories.verdict_repository import VerdictRepository
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.services.aggregation import build_distribution
from veritas.dashboard.services.scoring import band_for_index, compute_index
from veritas.dashboard.viewmodels.common import Band, Bucket, MetricVM, Sparkline
from veritas.dashboard.viewmodels.trust import (
    ComponentVM,
    DriverVM,
    IndexVM,
    TrustCenterVM,
)

_MAX_DRIVERS = 6


class TrustService:
    def __init__(self, events: EventRepository, verdicts: VerdictRepository) -> None:
        self._events = events
        self._verdicts = verdicts

    def build(self) -> TrustCenterVM:
        status_rows = self._events.count_by_status()
        total = sum(r.count for r in status_rows)

        empty_metric = MetricVM(label="", value=0.0, display="—")
        empty_band = Band(severity="caution", reason="no data ingested yet")
        if total == 0:
            return TrustCenterVM(
                is_empty=True,
                duplicate=empty_metric,
                integrity=empty_metric,
                judge_confidence=build_distribution("judge confidence", []),
                banner=empty_band,
            )

        status_composition = tuple(
            Bucket(label=r.status, count=r.count, rate=r.count / total) for r in status_rows
        )
        clean = next((r.count for r in status_rows if r.status.lower() == "clean"), 0)
        clean_rate = clean / total

        dup_fail = self._verdicts.count_by_check("exact_duplicate", "fail")
        dup_trend = self._verdicts.timeseries_by_check("exact_duplicate", "fail")
        dup_rate = min(1.0, dup_fail / total)
        duplicate = MetricVM(
            label="Duplicate events",
            value=float(dup_fail),
            display=fmt.count(dup_fail),
            unit=f"({fmt.pct(dup_rate)})",
            spark=self._spark(dup_trend),
        )

        integrity_pass_rate, integrity_metric = self._integrity()

        dup_ok_rate = max(0.0, 1.0 - dup_rate)
        index = compute_index(
            clean_rate=clean_rate,
            integrity_pass_rate=integrity_pass_rate,
            duplicate_ok_rate=dup_ok_rate,
        )
        severity = band_for_index(index.value)
        index_vm = IndexVM(
            value=index.value,
            display=f"{index.value:.1f}",
            components=tuple(
                ComponentVM(
                    name=c.name,
                    rate=c.rate,
                    weight=c.weight,
                    contribution=c.contribution,
                    display=f"{fmt.pct(c.rate)} x {c.weight:.2f} = {c.contribution:+.1f}",
                )
                for c in index.components
            ),
            formula_label="weighted blend: clean*0.50 + integrity*0.30 + dup-ok*0.20, x100",
            band=Band(severity=severity, reason=f"data quality index {index.value:.1f}/100"),
        )

        judge_conf = build_distribution(
            "judge confidence", self._verdicts.confidence_histogram("llm")
        )
        drivers = self._drivers()

        return TrustCenterVM(
            is_empty=False,
            status_composition=status_composition,
            data_quality_index=index_vm,
            duplicate=duplicate,
            integrity=integrity_metric,
            judge_confidence=judge_conf,
            drivers=drivers,
            banner=Band(
                severity=severity,
                reason=f"trust index {index.value:.1f}/100 — {severity}",
            ),
        )

    def _integrity(self) -> tuple[float, MetricVM]:
        rows = [r for r in self._verdicts.breakdown() if r.check_name == "referential_integrity"]
        total = sum(r.count for r in rows)
        passed = sum(r.count for r in rows if r.verdict == "pass")
        pass_rate = passed / total if total else 1.0
        review_trend = self._verdicts.timeseries_by_check("referential_integrity", "review")
        metric = MetricVM(
            label="Referential integrity (pass rate)",
            value=pass_rate,
            display=fmt.pct(pass_rate),
            spark=self._spark(review_trend),
        )
        return pass_rate, metric

    def _drivers(self) -> tuple[DriverVM, ...]:
        rows = [r for r in self._verdicts.breakdown() if r.verdict != "pass"]
        total = sum(r.count for r in rows)
        rows.sort(key=lambda r: r.count, reverse=True)
        return tuple(
            DriverVM(
                check_name=r.check_name,
                verdict=r.verdict,
                count=r.count,
                share=(r.count / total if total else 0.0),
            )
            for r in rows[:_MAX_DRIVERS]
        )

    @staticmethod
    def _spark(trend: list[DayCount]) -> Sparkline:
        return Sparkline(
            points=tuple(float(d.count) for d in trend),
            labels=tuple(d.day for d in trend),
        )
