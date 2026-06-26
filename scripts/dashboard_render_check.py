"""Headless render check for the dashboard (no browser required).

Seeds a throwaway SQLite DB, then drives every workspace through Streamlit's
``AppTest`` harness, asserting each renders without raising. This is the basis
for the screenshot list: each workspace below corresponds to one captured view.

Run:  uv run python scripts/dashboard_render_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_DB = Path(tempfile.mkdtemp()) / "veritas_demo.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"

from veritas.store.base import Base
from veritas.store.models import EventCleanRow, QualityVerdictRow, TraceLogRow

WORKSPACES = (
    "Trust Center",
    "Cost & Efficiency",
    "Data Quality Intelligence",
    "Human Review Queue",
    "Platform Health",
    "AI Judge Performance",
    "Event Detail",
)


def _seed() -> None:
    when = datetime(2026, 6, 23, 9, 0, tzinfo=UTC)
    engine = create_engine(f"sqlite:///{_DB}")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        session.add_all(
            [
                EventCleanRow(
                    event_id="e1", category="launches", summary="A launches B", found_at=when,
                    company1_id="c1", company2_id="c2", status="clean", updated_at=when,
                ),
                EventCleanRow(
                    event_id="e2", category="hires", summary="A hires D", found_at=when,
                    company1_id="c1", company2_id=None, status="review", updated_at=when,
                ),
                QualityVerdictRow(
                    event_id="e1", check_name="referential_integrity", check_type="rule",
                    prompt_version="", model="", verdict="pass", confidence=None, reason="ok",
                    evidence_span=None, input_tokens=None, output_tokens=None, cost_usd=None,
                    latency_ms=None, ts=when, created_at=when,
                ),
                QualityVerdictRow(
                    event_id="e2", check_name="semantic_accuracy", check_type="llm",
                    prompt_version="v1", model="claude-haiku-4-5-20251001", verdict="uncertain",
                    confidence=0.5, reason="maybe", evidence_span="e", input_tokens=400,
                    output_tokens=60, cost_usd=0.001, latency_ms=900, ts=when, created_at=when,
                ),
                TraceLogRow(
                    event_id="e1", trace_id="t1", stage="rules", payload_hash="h", created_at=when
                ),
            ]
        )
        session.commit()
    engine.dispose()


def main() -> int:
    _seed()
    from streamlit.testing.v1 import AppTest

    app = str(Path(__file__).resolve().parents[1] / "src" / "veritas" / "dashboard" / "app.py")
    failures = 0
    for workspace in WORKSPACES:
        at = AppTest.from_file(app, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value(workspace).run()
        ok = not at.exception
        failures += 0 if ok else 1
        print(f"{'OK ' if ok else 'FAIL'}  {workspace}")
    print("ALL WORKSPACES RENDERED CLEAN" if not failures else f"{failures} workspace(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
