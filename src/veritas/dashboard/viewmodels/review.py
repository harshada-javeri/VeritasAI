"""View-models for the Review Viewer (read-only; the workflow itself is V2)."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM


class ReviewItemVM(VM):
    event_id: str
    category: str | None
    summary_excerpt: str
    found_at_display: str
    status: str
    confidence_display: str


class ReviewQueueVM(VM):
    status: str
    is_empty: bool
    items: tuple[ReviewItemVM, ...] = ()
    total_shown: int = 0
    order_label: str = ""
    sort_note: str = ""
