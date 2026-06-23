"""Pipeline orchestration: rules gate → routing → escalation → remediation → final verdict."""

from veritas.pipeline.contracts import (
    EscalationResult,
    EscalationRouter,
    EventOutcome,
    FinalStatus,
    PipelineTraceSink,
    RemediationAction,
    RemediationProposal,
    Remediator,
    RouteAction,
    RoutingDecision,
    RoutingPolicy,
    VerdictSink,
)
from veritas.pipeline.escalation import (
    CheckJudges,
    TieredEscalationRouter,
    build_default_escalation_router,
)
from veritas.pipeline.remediation import HeuristicRemediator
from veritas.pipeline.routing import DefaultRoutingPolicy
from veritas.pipeline.runner import PipelineRunner, parse_error_outcome

__all__ = [
    "CheckJudges",
    "DefaultRoutingPolicy",
    "EscalationResult",
    "EscalationRouter",
    "EventOutcome",
    "FinalStatus",
    "HeuristicRemediator",
    "PipelineRunner",
    "PipelineTraceSink",
    "RemediationAction",
    "RemediationProposal",
    "Remediator",
    "RouteAction",
    "RoutingDecision",
    "RoutingPolicy",
    "TieredEscalationRouter",
    "VerdictSink",
    "build_default_escalation_router",
    "parse_error_outcome",
]
