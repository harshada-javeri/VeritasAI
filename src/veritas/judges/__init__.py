"""LLM judges: the semantic/contextual checks rules can't settle.

Every judge implements ``LLMJudge.evaluate(event) -> Verdict``. ``ReplayJudge``
needs no API; ``AnthropicJudge`` / ``GeminiJudge`` route through the gateway.
"""

from veritas.judges.anthropic import AnthropicJudge
from veritas.judges.base import BaseLLMJudge, default_prompt_vars
from veritas.judges.gemini import GeminiJudge
from veritas.judges.protocol import LLMJudge
from veritas.judges.replay import ReplayJudge, ReplayMiss
from veritas.judges.schema import JUDGE_OUTPUT_SCHEMA, JudgeOutput

__all__ = [
    "JUDGE_OUTPUT_SCHEMA",
    "AnthropicJudge",
    "BaseLLMJudge",
    "GeminiJudge",
    "JudgeOutput",
    "LLMJudge",
    "ReplayJudge",
    "ReplayMiss",
    "default_prompt_vars",
]
