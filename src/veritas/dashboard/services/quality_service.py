"""Builds the Data Quality Intelligence view-model."""

from __future__ import annotations

from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.rows import CheckDayVerdictCount, CheckVerdictCount
from veritas.dashboard.repositories.verdict_repository import VerdictRepository
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.services.aggregation import build_distribution, group_check_histograms
from veritas.dashboard.services.scoring import RULE_BASELINES
from veritas.dashboard.viewmodels.common import Bucket, Sparkline
from veritas.dashboard.viewmodels.quality import (
    CategoryFailureVM,
    QualityIntelligenceVM,
    RuleStatVM,
)


class QualityService:
    def __init__(self, verdicts: VerdictRepository, events: EventRepository) -> None:
        self._verdicts = verdicts
        self._events = events

    def build(self) -> QualityIntelligenceVM:
        breakdown = self._verdicts.rule_breakdown()
        if not breakdown:
            return QualityIntelligenceVM(is_empty=True)

        timeseries = self._verdicts.rule_timeseries()
        rule_stats = self._rule_stats(breakdown, timeseries)

        category_rows = self._events.count_by_category()
        category_total = sum(r.count for r in category_rows) or 1
        categories = tuple(
            Bucket(label=(r.category or "—"), count=r.count, rate=r.count / category_total)
            for r in category_rows
        )

        cat_failures = self._verdicts.failures_by_category()
        conf_rows = self._verdicts.confidence_histogram_by_check()
        conf_by_check = tuple(
            build_distribution(check_name, bins)
            for check_name, bins in sorted(group_check_histograms(conf_rows).items())
        )

        return QualityIntelligenceVM(
            is_empty=False,
            rule_stats=rule_stats,
            categories=categories,
            failures_by_category=tuple(
                CategoryFailureVM(category=c.category, check_name=c.check_name, count=c.count)
                for c in cat_failures
            ),
            confidence_by_check=conf_by_check,
        )

    def _rule_stats(
        self,
        breakdown: list[CheckVerdictCount],
        timeseries: list[CheckDayVerdictCount],
    ) -> tuple[RuleStatVM, ...]:
        totals: dict[str, int] = {}
        fails: dict[str, int] = {}
        reviews: dict[str, int] = {}
        for row in breakdown:
            totals[row.check_name] = totals.get(row.check_name, 0) + row.count
            if row.verdict == "fail":
                fails[row.check_name] = fails.get(row.check_name, 0) + row.count
            if row.verdict in {"review", "uncertain"}:
                reviews[row.check_name] = reviews.get(row.check_name, 0) + row.count

        fail_series: dict[str, list[tuple[str, int]]] = {}
        for ts_row in timeseries:
            if ts_row.verdict == "fail":
                fail_series.setdefault(ts_row.check_name, []).append((ts_row.day, ts_row.count))

        stats: list[RuleStatVM] = []
        for check_name, total in totals.items():
            fail = fails.get(check_name, 0)
            fail_rate = fail / total if total else 0.0
            series = sorted(fail_series.get(check_name, []))
            stats.append(
                RuleStatVM(
                    check_name=check_name,
                    total=total,
                    fail=fail,
                    review=reviews.get(check_name, 0),
                    fail_rate=fail_rate,
                    fail_rate_display=fmt.pct(fail_rate),
                    baseline_rate=RULE_BASELINES.get(check_name),
                    spark=Sparkline(
                        points=tuple(float(count) for _, count in series),
                        labels=tuple(day for day, _ in series),
                    ),
                )
            )
        stats.sort(key=lambda s: s.fail_rate, reverse=True)  # worst-first
        return tuple(stats)
