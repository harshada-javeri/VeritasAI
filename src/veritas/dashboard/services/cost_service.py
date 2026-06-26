"""Builds the Cost & Efficiency view-model (the executive workspace)."""

from __future__ import annotations

from veritas.config import Settings, get_settings
from veritas.dashboard.repositories.cost_repository import CostRepository
from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.rows import CheckCost, ModelCost, PromptCost
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.services.scoring import band_for_budget
from veritas.dashboard.viewmodels.common import Band, MetricVM, MoneyVM, RateVM, Sparkline
from veritas.dashboard.viewmodels.cost import (
    BudgetVM,
    CheckCostVM,
    CostEfficiencyVM,
    CostHighlightVM,
    ModelCostVM,
    PromptCostVM,
    TokenVM,
)


class CostService:
    def __init__(
        self,
        cost: CostRepository,
        events: EventRepository,
        settings: Settings | None = None,
    ) -> None:
        self._cost = cost
        self._events = events
        self._settings = settings if settings is not None else get_settings()

    def build(self) -> CostEfficiencyVM:
        event_count = self._events.count()
        total = self._cost.total_cost()
        tokens = self._cost.token_totals()
        by_model = self._cost.cost_per_verdict_by_model()
        by_check = self._cost.cost_by_check()
        by_prompt = self._cost.cost_by_prompt_version()
        trend = self._cost.cost_timeseries()

        escalation_models = {self._settings.models.sonnet}
        escalated, llm_events = self._cost.escalation_event_counts(escalation_models)

        is_empty = event_count == 0 and not by_check

        limit = self._settings.cost.monthly_budget_usd
        consumed = total / limit if limit else 0.0
        budget = BudgetVM(
            spent_usd=total,
            limit_usd=limit,
            consumed_pct=consumed,
            display=f"{fmt.money(total)} / {fmt.money(limit)} ({fmt.pct(consumed)})",
            band=Band(
                severity=band_for_budget(consumed),
                reason=f"{fmt.pct(consumed)} of monthly budget consumed",
            ),
        )

        per_1k_value = (total / event_count * 1000.0) if event_count else 0.0
        cost_per_1k = MetricVM(
            label="Cost per 1,000 events",
            value=per_1k_value,
            display=fmt.money(per_1k_value),
            unit="/1k",
        )

        esc_rate = (escalated / llm_events) if llm_events else 0.0
        escalation = RateVM(
            value=esc_rate,
            display=fmt.pct(esc_rate),
            note="proxy: distinct events with an escalation-tier verdict ÷ events judged by LLM",
        )

        per_verdict_input = (tokens.input_tokens / llm_events) if llm_events else 0.0
        token_vm = TokenVM(
            input_tokens=tokens.input_tokens,
            output_tokens=tokens.output_tokens,
            per_verdict_input=per_verdict_input,
            display=(
                f"{fmt.tokens(tokens.input_tokens)} in / "
                f"{fmt.tokens(tokens.output_tokens)} out"
            ),
        )

        return CostEfficiencyVM(
            is_empty=is_empty,
            total_spend=MoneyVM(value_usd=total, display=fmt.money(total)),
            budget=budget,
            cost_per_1k_events=cost_per_1k,
            cost_per_verdict=tuple(
                ModelCostVM(
                    model=m.model,
                    count=m.count,
                    total_display=fmt.money(m.total_cost),
                    avg_display=fmt.money(m.avg_cost),
                )
                for m in by_model
            ),
            cost_by_check=tuple(
                CheckCostVM(
                    check_name=c.check_name,
                    total_usd=c.total_cost,
                    total_display=fmt.money(c.total_cost),
                    is_zero=c.total_cost == 0.0,
                )
                for c in by_check
            ),
            cost_by_prompt=tuple(
                PromptCostVM(
                    prompt_version=p.prompt_version,
                    total_display=fmt.money(p.total_cost),
                    avg_input_tokens=int(p.total_input_tokens / p.count) if p.count else 0,
                    count=p.count,
                )
                for p in by_prompt
            ),
            spend_trend=Sparkline(
                points=tuple(d.total_cost for d in trend),
                labels=tuple(d.day for d in trend),
            ),
            escalation_rate=escalation,
            tokens=token_vm,
            efficiency_statement=self._efficiency_statement(event_count, total, per_1k_value),
            highlights=self._highlights(by_check, by_model, by_prompt),
        )

    @staticmethod
    def _highlights(
        by_check: list[CheckCost],
        by_model: list[ModelCost],
        by_prompt: list[PromptCost],
    ) -> tuple[CostHighlightVM, ...]:
        """Largest cost drivers — derived from aggregates already fetched above
        (no extra queries). Each card answers "what is costing money?" directly.
        """
        top_check = next((c for c in by_check if c.total_cost > 0.0), None)
        top_model = next((m for m in by_model if m.total_cost > 0.0), None)
        top_prompt = max(by_prompt, key=lambda p: p.total_cost, default=None)
        top_tokens = max(by_prompt, key=lambda p: p.total_input_tokens, default=None)
        return (
            CostHighlightVM(
                label="Largest cost driver",
                value=top_check.check_name if top_check else "—",
                detail=fmt.money(top_check.total_cost) if top_check else "no LLM spend yet",
            ),
            CostHighlightVM(
                label="Highest-cost model",
                value=top_model.model if top_model else "—",
                detail=(
                    f"{fmt.money(top_model.total_cost)} · {fmt.money(top_model.avg_cost)}/verdict"
                    if top_model
                    else "no LLM spend yet"
                ),
            ),
            CostHighlightVM(
                label="Highest-cost prompt",
                value=top_prompt.prompt_version if top_prompt else "—",
                detail=fmt.money(top_prompt.total_cost) if top_prompt else "no LLM spend yet",
            ),
            CostHighlightVM(
                label="Largest token consumer",
                value=top_tokens.prompt_version if top_tokens else "—",
                detail=(
                    f"{fmt.tokens(top_tokens.total_input_tokens)} in"
                    if top_tokens
                    else "no tokens yet"
                ),
            ),
        )

    def _efficiency_statement(self, event_count: int, total: float, per_1k: float) -> str:
        status = self._events.count_by_status()
        total_events = sum(s.count for s in status) or event_count
        clean = next((s.count for s in status if s.status.lower() == "clean"), 0)
        clean_pct = (clean / total_events) if total_events else 0.0
        return (
            f"Rules auto-cleared {fmt.pct(clean_pct)} of {fmt.count(total_events)} events at $0; "
            f"LLM judgment cost {fmt.money(total)} so far — "
            f"{fmt.money(per_1k)} per 1,000 events."
        )
