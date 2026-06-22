"""Application configuration.

All runtime configuration is sourced from the environment (or a local ``.env``
file). Dataset locations are *never* hardcoded — the feed is discovered under
``DATASET_ROOT``. Model IDs are pinned to exact versions on purpose: a data
quality judge that silently floats to ``*-latest`` is an unmonitored model
change waiting to happen.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: src/veritas/config.py -> parents[2]. Used for the default dataset
# location so the feed is discovered out of the box without any env setup.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "datasets"


class ModelPins(BaseModel):
    """Pinned model IDs. Do not float to ``*-latest`` in production.

    Anthropic IDs are exact (Haiku 4.5 / Sonnet 4.6); the Gemini pin keeps the
    judge layer vendor-agnostic without changing any calling code.
    """

    model_config = ConfigDict(protected_namespaces=())

    haiku: str = "claude-haiku-4-5-20251001"
    sonnet: str = "claude-sonnet-4-6"
    gemini_flash: str = "gemini-2.5-flash"


class Thresholds(BaseModel):
    """Decision thresholds shared across rules and judges (consumed in later phases)."""

    confidence_floor: float = Field(0.15, ge=0.0, le=1.0)
    """Below this raw event confidence, auto-quarantine (deterministic rule)."""

    llm_fail_min_confidence: float = Field(0.70, ge=0.0, le=1.0)
    """An LLM ``fail`` is only treated as hard-fail above this judge confidence."""

    min_event_year: int = Field(2000, ge=1900, le=2100)
    """Events dated before this year are implausible and flagged by the date rule."""


class CostBudget(BaseModel):
    """Cost guardrails. The trace log's ``cost_usd`` is metered against this."""

    monthly_budget_usd: float = Field(500.0, gt=0.0)


class Settings(BaseSettings):
    """Top-level settings. Field names map to env vars (``dataset_root`` -> ``DATASET_ROOT``)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Resolution priority: DATASET_ROOT env var first, else ./datasets at the
    # repo root. pydantic-settings sources env over the default_factory, so the
    # env override wins automatically.
    dataset_root: Path = Field(
        default_factory=lambda: DEFAULT_DATASET_ROOT,
        description="Feed root. DATASET_ROOT env var overrides; defaults to <repo>/datasets.",
    )
    dataset_patterns: tuple[str, ...] = ("*.jsonl", "*.ndjson")
    dataset_recursive: bool = True

    # SQLite today; the URL is the only thing that changes to move to async Postgres.
    database_url: str = "sqlite+aiosqlite:///./veritas.db"

    models: ModelPins = ModelPins()
    thresholds: Thresholds = Thresholds()
    cost: CostBudget = CostBudget()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance (read from env / ``.env`` once)."""
    return Settings()
