"""Builds the Review Viewer view-model — read-only triage list.

V1 is a *viewer*: it sorts by fields that exist (recency, judge confidence),
never by an "impact" model (that is a V2 lineage contract). No assignment,
claim, decision capture, or bulk actions — those are the V2 review system.
"""

from __future__ import annotations

from veritas.dashboard.repositories.event_repository import EventRepository, OrderBy
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.viewmodels.review import ReviewItemVM, ReviewQueueVM

_ORDER_LABELS: dict[OrderBy, str] = {
    "recent": "most recent first",
    "confidence": "lowest judge confidence first",
}
_SORT_NOTE = (
    "Ordered by available fields only. Impact ranking and SLA aging require the "
    "lineage/impact model and a review-workflow store (V2)."
)


class ReviewService:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    def build(
        self, status: str, *, order_by: OrderBy = "confidence", limit: int = 50
    ) -> ReviewQueueVM:
        items = self._events.list_by_status(status, limit=limit, order_by=order_by)
        return ReviewQueueVM(
            status=status,
            is_empty=not items,
            items=tuple(
                ReviewItemVM(
                    event_id=item.event_id,
                    category=item.category,
                    summary_excerpt=fmt.excerpt(item.summary),
                    found_at_display=fmt.dt(item.found_at),
                    status=item.status,
                    confidence_display=(
                        fmt.pct(item.min_llm_confidence)
                        if item.min_llm_confidence is not None
                        else "—"
                    ),
                )
                for item in items
            ),
            total_shown=len(items),
            order_label=_ORDER_LABELS[order_by],
            sort_note=_SORT_NOTE,
        )
