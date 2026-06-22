"""The judge output contract.

``JUDGE_OUTPUT_SCHEMA`` is a hand-written, flat JSON schema (no ``$ref``/``$defs``,
no ``additionalProperties`` nesting) so it works as-is for Anthropic tool input
and, after light sanitizing, for Gemini's responseSchema. ``JudgeOutput`` is the
Pydantic model the gateway's structured content is validated into; ``confidence``
is clamped into [0, 1] so a mildly out-of-range model value degrades gracefully
rather than raising.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from veritas.domain.models import VerdictStatus

JUDGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail", "uncertain"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "evidence_span": {"type": "string"},
    },
    "required": ["verdict", "confidence", "reason"],
    "additionalProperties": False,
}


class JudgeOutput(BaseModel):
    """Validated structured output from a judge model."""

    model_config = ConfigDict(extra="ignore")

    verdict: VerdictStatus
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str
    evidence_span: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> Any:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return min(1.0, max(0.0, float(value)))
        return value
