"""View-models for the Cost & Efficiency workspace."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM, Band, MetricVM, MoneyVM, RateVM, Sparkline


class ModelCostVM(VM):
    model: str
    count: int
    total_display: str
    avg_display: str


class CheckCostVM(VM):
    check_name: str
    total_usd: float
    total_display: str
    is_zero: bool


class PromptCostVM(VM):
    prompt_version: str
    total_display: str
    avg_input_tokens: int
    count: int


class BudgetVM(VM):
    spent_usd: float
    limit_usd: float
    consumed_pct: float
    display: str
    band: Band


class TokenVM(VM):
    input_tokens: int
    output_tokens: int
    per_verdict_input: float
    display: str


class CostHighlightVM(VM):
    """One executive emphasis card: what is costing money, at a glance."""

    label: str
    value: str
    detail: str


class CostEfficiencyVM(VM):
    is_empty: bool
    total_spend: MoneyVM
    budget: BudgetVM
    cost_per_1k_events: MetricVM
    cost_per_verdict: tuple[ModelCostVM, ...] = ()
    cost_by_check: tuple[CheckCostVM, ...] = ()
    cost_by_prompt: tuple[PromptCostVM, ...] = ()
    spend_trend: Sparkline = Sparkline()
    escalation_rate: RateVM
    tokens: TokenVM
    efficiency_statement: str
    highlights: tuple[CostHighlightVM, ...] = ()  # largest drivers (executive cards)
