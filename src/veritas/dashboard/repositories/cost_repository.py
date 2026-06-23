"""Cost & token aggregates over ``quality_verdicts``.

``cost_per_1k_events`` is NOT computed here with ``COUNT(DISTINCT event_id)`` (the
audit's anti-pattern); the service divides ``total_cost`` by the cheap
``EventRepository.count``. Escalation is a V1 proxy: distinct events carrying an
escalation-tier model verdict over distinct events with any LLM verdict.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import distinct, func, select

from veritas.dashboard.repositories.base import ReadRepository
from veritas.dashboard.repositories.rows import (
    CheckCost,
    DayCost,
    ModelCost,
    PromptCost,
    TokenTotals,
)
from veritas.store.models import QualityVerdictRow

_QV = QualityVerdictRow


class CostRepository(ReadRepository):
    def total_cost(self) -> float:
        with self._sm() as session:
            return float(session.scalar(select(func.coalesce(func.sum(_QV.cost_usd), 0.0))) or 0.0)

    def token_totals(self) -> TokenTotals:
        stmt = select(
            func.coalesce(func.sum(_QV.input_tokens), 0),
            func.coalesce(func.sum(_QV.output_tokens), 0),
        )
        with self._sm() as session:
            row = session.execute(stmt).one()
        return TokenTotals(input_tokens=int(row[0]), output_tokens=int(row[1]))

    def cost_per_verdict_by_model(self) -> list[ModelCost]:
        stmt = (
            select(
                _QV.model,
                func.count(),
                func.coalesce(func.sum(_QV.cost_usd), 0.0),
                func.coalesce(func.avg(_QV.cost_usd), 0.0),
            )
            .where(_QV.check_type == "llm")
            .group_by(_QV.model)
            .order_by(func.coalesce(func.sum(_QV.cost_usd), 0.0).desc())
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            ModelCost(
                model=str(r[0]), count=int(r[1]), total_cost=float(r[2]), avg_cost=float(r[3])
            )
            for r in rows
        ]

    def cost_by_check(self) -> list[CheckCost]:
        stmt = (
            select(_QV.check_name, func.coalesce(func.sum(_QV.cost_usd), 0.0))
            .group_by(_QV.check_name)
            .order_by(func.coalesce(func.sum(_QV.cost_usd), 0.0).desc())
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [CheckCost(check_name=str(r[0]), total_cost=float(r[1])) for r in rows]

    def cost_by_prompt_version(self) -> list[PromptCost]:
        stmt = (
            select(
                _QV.prompt_version,
                func.coalesce(func.sum(_QV.cost_usd), 0.0),
                func.coalesce(func.sum(_QV.input_tokens), 0),
                func.count(),
            )
            .where(_QV.prompt_version != "")
            .group_by(_QV.prompt_version)
            .order_by(_QV.prompt_version)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            PromptCost(
                prompt_version=str(r[0]),
                total_cost=float(r[1]),
                total_input_tokens=int(r[2]),
                count=int(r[3]),
            )
            for r in rows
        ]

    def cost_timeseries(self) -> list[DayCost]:
        day = func.date(_QV.created_at)
        stmt = (
            select(day, func.coalesce(func.sum(_QV.cost_usd), 0.0))
            .where(_QV.cost_usd.is_not(None))
            .group_by(day)
            .order_by(day)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [DayCost(day=str(r[0]), total_cost=float(r[1])) for r in rows]

    def escalation_event_counts(self, escalation_models: Collection[str]) -> tuple[int, int]:
        """Returns ``(escalated_events, llm_events)`` as distinct event counts."""
        models = list(escalation_models)
        with self._sm() as session:
            llm_events = int(
                session.scalar(
                    select(func.count(distinct(_QV.event_id))).where(_QV.check_type == "llm")
                )
                or 0
            )
            if not models:
                return 0, llm_events
            escalated = int(
                session.scalar(
                    select(func.count(distinct(_QV.event_id))).where(
                        _QV.check_type == "llm", _QV.model.in_(models)
                    )
                )
                or 0
            )
        return escalated, llm_events
