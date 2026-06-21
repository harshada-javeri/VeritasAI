"""Tests for the tolerant JSON:API parser.

These assert the central design contract: structural problems become
``ParseError``; content problems are tolerated and preserved for the rules.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from veritas.domain.models import ParseError, ResolvedEvent
from veritas.ingest.parser import iter_dataset, iter_records

FEED_ROOT = Path(__file__).parent / "fixtures" / "feed"
PART_A = FEED_ROOT / "part_a.jsonl"
PART_B = FEED_ROOT / "nested" / "part_b.ndjson"


def _split(path: Path) -> tuple[list[ResolvedEvent], list[ParseError]]:
    events: list[ResolvedEvent] = []
    errors: list[ParseError] = []
    for result in iter_records(path):
        (events if isinstance(result, ResolvedEvent) else errors).append(result)  # type: ignore[arg-type]
    return events, errors


def test_part_a_event_and_error_counts() -> None:
    events, errors = _split(PART_A)
    # 7 single-event lines + 1 line carrying 2 events = 9 events.
    assert len(events) == 9
    # broken JSON + no-data + missing-id = 3 structural errors.
    assert len(errors) == 3


def test_error_types_are_classified() -> None:
    _, errors = _split(PART_A)
    by_type = sorted(error.error_type for error in errors)
    assert by_type == ["json_decode", "malformed_record", "malformed_record"]
    decode = next(e for e in errors if e.error_type == "json_decode")
    assert decode.source_line is not None
    assert decode.excerpt is not None


def _by_id(path: Path) -> dict[str, ResolvedEvent]:
    events, _ = _split(path)
    return {event.event_id: event for event in events}


def test_clean_event_is_fully_resolved() -> None:
    event = _by_id(PART_A)["11111111-1111-1111-1111-111111111111"]
    assert event.category == "launches"
    assert event.confidence == 0.91
    assert event.found_at == datetime.fromisoformat("2024-03-12T09:00:00+00:00")
    assert event.human_approved is True
    assert event.company1 is not None and event.company1.name == "Acme Inc"
    assert event.company2 is None  # "data": null
    assert event.source_article is not None
    assert event.source_article.url == "https://news.example.com/acme-launch"
    assert event.unresolved_references == []


def test_zero_confidence_is_preserved_not_dropped() -> None:
    event = _by_id(PART_A)["22222222-2222-2222-2222-222222222222"]
    assert event.confidence == 0.0
    assert event.company2 is not None and event.company2.domain == "cmha.ca"


def test_unparseable_confidence_is_none_but_raw_is_retained() -> None:
    event = _by_id(PART_A)["66666666-6666-6666-6666-666666666666"]
    assert event.confidence is None
    assert event.attributes["confidence"] == "high"  # raw value kept for the rules


def test_dangling_reference_is_recorded_not_dropped() -> None:
    event = _by_id(PART_A)["55555555-5555-5555-5555-555555555555"]
    assert event.company1 is None
    assert event.company1_id == "cmissing"
    assert "cmissing" in event.unresolved_references


def test_non_uuid_id_still_parses_as_content_for_rules() -> None:
    event = _by_id(PART_A)["not-a-uuid-1"]
    assert event.category == "frobnicates"  # novel category tolerated here


def test_data_array_yields_multiple_events_sharing_included() -> None:
    by_id = _by_id(PART_A)
    first = by_id["88888888-0000-0000-0000-000000000001"]
    second = by_id["88888888-0000-0000-0000-000000000002"]
    assert first.source_article_id == second.source_article_id == "a8"
    assert first.company1 is not None and first.company1.name == "Pied Piper"


def test_financing_event_amount_is_coerced() -> None:
    event = _by_id(PART_A)["33333333-3333-3333-3333-333333333333"]
    assert event.amount == 5_000_000.0
    assert event.found_at is not None and event.found_at.year == 2011


def test_iter_dataset_concatenates_files() -> None:
    files = sorted([PART_A, PART_B])
    events = [r for r in iter_dataset(files) if isinstance(r, ResolvedEvent)]
    assert len(events) == 11  # 9 from part_a + 2 from part_b
    ids = {event.event_id for event in events}
    assert "99999999-9999-9999-9999-999999999999" in ids
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in ids
