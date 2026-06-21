"""Tolerant JSON:API parser.

Each feed line is a JSON:API document::

    {"data": [ {news_event} ], "included": [ {company}, {company}, {news_article} ]}

``data`` may also be a single object. This module flattens each ``news_event``
into a :class:`ResolvedEvent`, resolving the ``relationships`` ids against the
``included`` array.

Failure policy (see ``domain.models`` for the rationale):

* **Structural** failure -> :class:`ParseError`. The line is not JSON, has no
  ``data`` envelope, or an event has no ``id`` — it cannot be keyed at all.
* **Content** problems are *not* failures here. They are tolerated, the raw
  value is preserved in ``ResolvedEvent.attributes``, and the Phase 1 rules
  flag them. The parser never decides quality.

Everything streams line by line; a 1.2 GB feed is never held in memory.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from veritas.domain.models import Article, Company, ParseError, ResolvedEvent

MAX_EXCERPT = 200

# A single line yields zero-or-more events, or one structural error.
RecordResult = ResolvedEvent | ParseError


class MalformedRecordError(ValueError):
    """A JSON document that is well-formed JSON but not a usable ``news_event``."""


def _index_included(included: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """Index the ``included`` array by ``(type, id)`` for O(1) resolution."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(included, list):
        return index
    for resource in included:
        if (
            isinstance(resource, dict)
            and isinstance(resource.get("type"), str)
            and isinstance(resource.get("id"), str)
        ):
            index[(resource["type"], resource["id"])] = resource
    return index


def _resolve(
    relationship: Any,
    index: dict[tuple[str, str], dict[str, Any]],
    unresolved: list[str],
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve one relationship block to ``(target_id, resource)``.

    Records the target id in ``unresolved`` when it was declared but no matching
    entity exists in ``included`` (a dangling reference — flagged by rules).
    """
    if not isinstance(relationship, dict):
        return None, None
    data = relationship.get("data")
    if not isinstance(data, dict):
        return None, None  # ``"data": null`` -> relationship simply absent
    target_id = data.get("id")
    target_type = data.get("type")
    if not isinstance(target_id, str):
        return None, None
    resource = index.get((target_type, target_id)) if isinstance(target_type, str) else None
    if resource is None:
        unresolved.append(target_id)
    return target_id, resource


def _build_company(resource: dict[str, Any]) -> Company:
    attrs = resource.get("attributes")
    attrs = attrs if isinstance(attrs, dict) else {}
    # Real feed uses ``company_name``; README §2 documented it as ``name``. Read
    # the real key first, fall back to the documented one for resilience.
    return Company(
        id=resource["id"],
        name=attrs.get("company_name") or attrs.get("name"),
        domain=attrs.get("domain"),
        ticker=attrs.get("ticker"),
        attributes=attrs,
    )


def _build_article(resource: dict[str, Any]) -> Article:
    attrs = resource.get("attributes")
    attrs = attrs if isinstance(attrs, dict) else {}
    return Article(
        id=resource["id"],
        title=attrs.get("title"),
        body=attrs.get("body"),
        url=attrs.get("url"),
        published_at=attrs.get("published_at"),
        attributes=attrs,
    )


def _build_event(
    event: Any,
    index: dict[tuple[str, str], dict[str, Any]],
    *,
    source_file: str | None,
    source_line: int | None,
) -> ResolvedEvent:
    if not isinstance(event, dict):
        raise MalformedRecordError("event is not a JSON object")
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise MalformedRecordError("event is missing a string 'id'")

    attributes = event.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    relationships = event.get("relationships")
    relationships = relationships if isinstance(relationships, dict) else {}

    raw_type = event.get("type")
    event_type = raw_type if isinstance(raw_type, str) else "news_event"

    unresolved: list[str] = []
    company1_id, company1_res = _resolve(relationships.get("company1"), index, unresolved)
    company2_id, company2_res = _resolve(relationships.get("company2"), index, unresolved)
    source_id, source_res = _resolve(
        relationships.get("most_relevant_source"), index, unresolved
    )

    return ResolvedEvent(
        event_id=event_id,
        type=event_type,
        category=attributes.get("category"),
        summary=attributes.get("summary"),
        article_sentence=attributes.get("article_sentence"),
        confidence=attributes.get("confidence"),
        found_at=attributes.get("found_at"),
        human_approved=attributes.get("human_approved"),
        amount=attributes.get("amount"),
        attributes=attributes,
        company1_id=company1_id,
        company2_id=company2_id,
        source_article_id=source_id,
        company1=_build_company(company1_res) if company1_res is not None else None,
        company2=_build_company(company2_res) if company2_res is not None else None,
        source_article=_build_article(source_res) if source_res is not None else None,
        unresolved_references=unresolved,
        source_file=source_file,
        source_line=source_line,
    )


def parse_document(
    raw: Any,
    *,
    source_file: str | None = None,
    source_line: int | None = None,
) -> list[ResolvedEvent]:
    """Flatten one JSON:API document into its ``ResolvedEvent``(s).

    Raises:
        MalformedRecordError: the document is not an object, has no ``data``, or
            an event lacks an ``id``.
    """
    if not isinstance(raw, dict):
        raise MalformedRecordError("document is not a JSON object")
    if "data" not in raw:
        raise MalformedRecordError("document is missing the 'data' member")

    data = raw["data"]
    events = data if isinstance(data, list) else [data]
    index = _index_included(raw.get("included"))
    return [
        _build_event(event, index, source_file=source_file, source_line=source_line)
        for event in events
    ]


def iter_records(path: Path) -> Iterator[RecordResult]:
    """Stream one file, yielding a ``ResolvedEvent`` per event or a ``ParseError``."""
    source = str(path)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                yield ParseError(
                    source_file=source,
                    source_line=line_number,
                    error_type="json_decode",
                    reason=str(exc),
                    excerpt=text[:MAX_EXCERPT],
                )
                continue
            try:
                yield from parse_document(raw, source_file=source, source_line=line_number)
            except MalformedRecordError as exc:
                yield ParseError(
                    source_file=source,
                    source_line=line_number,
                    error_type="malformed_record",
                    reason=str(exc),
                    excerpt=text[:MAX_EXCERPT],
                )


def iter_dataset(files: Iterable[Path]) -> Iterator[RecordResult]:
    """Stream many files in order, concatenating their record streams."""
    for path in files:
        yield from iter_records(path)
