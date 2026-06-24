"""Seed a populated **demo** SQLite database for the dashboard.

This exists so a reviewer can launch the Decision Intelligence Console and see
every workspace lit up with representative data in under a minute — *without*
any live model calls, API keys, or a full pipeline run over the 620K-record
feed.

The data is **synthetic and clearly labelled as such** (event ids are prefixed
``demo-``). It is shaped to mirror the real feed's profile (≈83% clean / 6%
review / 11% quarantined, the same rule and LLM check names, Haiku/Sonnet cost
and latency bands) so the tiles, trends, and review queue are meaningful — but
no number here is a measured production result. For real numbers, run the
pipeline against the feed (see the README) and point ``DATABASE_URL`` at that
database instead.

Deterministic: a fixed RNG seed makes every run produce the same database, so
screenshots are reproducible.

Run:
    uv run python scripts/seed_demo_db.py            # writes ./veritas-demo.db
    uv run python scripts/seed_demo_db.py out.db     # custom path

Then point the dashboard at it:
    DATABASE_URL="sqlite+aiosqlite:///./veritas-demo.db" \\
        uv run streamlit run src/veritas/dashboard/app.py
"""

from __future__ import annotations

import hashlib
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from veritas.store.base import Base
from veritas.store.models import EventCleanRow, QualityVerdictRow, TraceLogRow

# A fixed anchor instead of datetime.now() so the seeded data — and therefore any
# screenshots taken from it — are byte-for-byte reproducible across machines.
ANCHOR = datetime(2026, 6, 24, 9, 0, tzinfo=UTC)
DAYS = 14
EVENTS_PER_DAY = 12

CATEGORIES = (
    "launches",
    "partners_with",
    "hires",
    "acquires",
    "receives_financing",
    "recognized_as",
)

# Rough mirror of the real feed's rollup mix (see docs/data-quality-findings.md).
STATUS_WEIGHTS = (("clean", 0.83), ("quarantined", 0.11), ("review", 0.06))

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# (check_name, model, prompt_version, input_tok, output_tok, cost_usd, latency_ms)
LLM_CHECKS = {
    "semantic_accuracy": (HAIKU, "v1", 410, 58, 0.00052, 880),
    "source_credibility": (HAIKU, "v1", 620, 64, 0.00071, 940),
    "entity_resolution": (SONNET, "v1", 470, 72, 0.00249, 1620),
}

QUARANTINE_REASONS = (
    ("confidence_floor", "confidence 0.04 below floor 0.15"),
    ("date_sanity", "found_at 2027-01-12 is in the future"),
    ("category_known", "category 'rebrands_as' not in known set"),
)


def _pick(rng: random.Random, weighted: tuple[tuple[str, float], ...]) -> str:
    roll = rng.random()
    cumulative = 0.0
    for value, weight in weighted:
        cumulative += weight
        if roll <= cumulative:
            return value
    return weighted[-1][0]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _rows() -> tuple[list[EventCleanRow], list[QualityVerdictRow], list[TraceLogRow]]:
    rng = random.Random(1729)  # deterministic
    events: list[EventCleanRow] = []
    verdicts: list[QualityVerdictRow] = []
    traces: list[TraceLogRow] = []

    seq = 0
    for day in range(DAYS):
        when_day = ANCHOR - timedelta(days=DAYS - 1 - day)
        for _ in range(EVENTS_PER_DAY):
            seq += 1
            eid = f"demo-{seq:04d}"
            ts = when_day + timedelta(minutes=rng.randint(0, 540))
            category = rng.choice(CATEGORIES)
            status = _pick(rng, STATUS_WEIGHTS)
            company2 = f"c{rng.randint(1, 40)}" if rng.random() > 0.55 else None

            events.append(
                EventCleanRow(
                    event_id=eid,
                    category=category,
                    summary=f"Demo {category.replace('_', ' ')} event {seq}",
                    found_at=ts,
                    company1_id=f"c{rng.randint(1, 40)}",
                    company2_id=company2,
                    status=status,
                    updated_at=ts,
                )
            )
            traces.append(
                TraceLogRow(
                    event_id=eid,
                    trace_id=_hash(eid),
                    stage="rules",
                    payload_hash=_hash(eid + category),
                    created_at=ts,
                )
            )

            # Every event carries the cheap rule verdicts (free, $0).
            verdicts.append(
                QualityVerdictRow(
                    event_id=eid, check_name="referential_integrity", check_type="rule",
                    prompt_version="", model="", verdict="pass" if company2 else "uncertain",
                    confidence=None, reason="ok" if company2 else "company2 absent",
                    evidence_span=None, input_tokens=None, output_tokens=None, cost_usd=None,
                    latency_ms=None, ts=ts, created_at=ts,
                )
            )

            if status == "quarantined":
                # Hard rule fail — quarantined with no LLM spend (the triage gate).
                check_name, reason = rng.choice(QUARANTINE_REASONS)
                verdicts.append(
                    QualityVerdictRow(
                        event_id=eid, check_name=check_name, check_type="rule",
                        prompt_version="", model="", verdict="fail", confidence=None,
                        reason=reason, evidence_span=None, input_tokens=None,
                        output_tokens=None, cost_usd=None, latency_ms=None, ts=ts, created_at=ts,
                    )
                )
                traces.append(
                    TraceLogRow(event_id=eid, trace_id=_hash(eid), stage="quarantine",
                                payload_hash=_hash(eid + "q"), created_at=ts)
                )
                continue

            # Clean + review events escalate to the LLM judges.
            for check_name, (model, pv, itok, otok, cost, latency) in LLM_CHECKS.items():
                # Reviews surface as uncertain LLM verdicts; clean events pass.
                if status == "review" and check_name == "semantic_accuracy":
                    verdict, conf = "uncertain", round(rng.uniform(0.4, 0.6), 2)
                    reason = "summary is ambiguous between two event types"
                else:
                    verdict = "pass" if rng.random() > 0.08 else "fail"
                    conf = round(rng.uniform(0.78, 0.97), 2)
                    reason = "text supports the labelled category" if verdict == "pass" \
                        else "summary describes a different event type"
                jitter = rng.uniform(0.85, 1.15)
                verdicts.append(
                    QualityVerdictRow(
                        event_id=eid, check_name=check_name, check_type="llm",
                        prompt_version=pv, model=model, verdict=verdict, confidence=conf,
                        reason=reason, evidence_span=f"…{category}…",
                        input_tokens=itok, output_tokens=otok,
                        cost_usd=round(cost * jitter, 6), latency_ms=int(latency * jitter),
                        ts=ts, created_at=ts,
                    )
                )
            traces.append(
                TraceLogRow(event_id=eid, trace_id=_hash(eid), stage="escalation",
                            payload_hash=_hash(eid + "e"), created_at=ts)
            )

    return events, verdicts, traces


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "veritas-demo.db")
    if out.exists():
        out.unlink()

    engine = create_engine(f"sqlite:///{out}")
    Base.metadata.create_all(engine)
    events, verdicts, traces = _rows()
    with sessionmaker(engine)() as session:
        session.add_all(events)
        session.add_all(verdicts)
        session.add_all(traces)
        session.commit()
    engine.dispose()

    print(f"Seeded {out} with synthetic demo data:")
    print(f"  events_clean     {len(events):>4}")
    print(f"  quality_verdicts {len(verdicts):>4}")
    print(f"  trace_logs       {len(traces):>4}")
    print()
    print("Launch the dashboard against it:")
    print(f'  DATABASE_URL="sqlite+aiosqlite:///./{out}" \\')
    print("      uv run streamlit run src/veritas/dashboard/app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
