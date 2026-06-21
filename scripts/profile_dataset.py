"""Profile the news-events feed.

Reproduces the dataset characteristics from README section 2 (record counts,
category distribution, confidence stats, date span, relationship presence,
amount sparsity, duplicates, one-article-many-events) by streaming the feed
discovered under ``DATASET_ROOT``. No file path is hardcoded; pointing it at the
real dataset is a config change, not a code change.

Usage:
    uv run python scripts/profile_dataset.py [--root PATH] [--top N] [--json OUT]

Memory: counters keyed on event_id and source-article-id are held in memory.
That is bounded and fine for the ~310K-record feed; at 100M+ records exact
duplicate detection would move to an external/approximate pass (noted, not
silently assumed).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Allow running directly (``python scripts/profile_dataset.py``) without an
# editable install by putting the package's ``src`` dir on the path first.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from veritas.config import get_settings
from veritas.domain.models import ParseError, ResolvedEvent
from veritas.ingest.discovery import DatasetError, discover_dataset_files
from veritas.ingest.parser import iter_records

logger = logging.getLogger("veritas.profile")

FINANCIAL_CATEGORIES = ("receives_financing", "acquires")


class Accumulator:
    """Streaming aggregates over the feed (single pass, bounded memory)."""

    def __init__(self) -> None:
        self.events = 0
        self.parse_errors: Counter[str] = Counter()

        self.categories: Counter[str] = Counter()
        self.missing_category = 0

        self.conf_n = 0
        self.conf_sum = 0.0
        self.conf_min = float("inf")
        self.conf_max = float("-inf")
        self.conf_zero = 0
        self.conf_unparseable = 0
        self.conf_buckets: Counter[str] = Counter()

        self.year_counts: Counter[int] = Counter()
        self.date_n = 0
        self.date_unparseable = 0

        self.has_company1 = 0
        self.has_company2 = 0
        self.has_source = 0
        self.with_unresolved = 0
        self.total_unresolved = 0

        # Relationship-id presence (declared in 'relationships', resolved or not).
        self.company1_id_present = 0
        self.company2_id_present = 0
        self.source_id_present = 0

        self.amount_present = 0
        self.amount_present_by_category: Counter[str] = Counter()

        self.event_ids: Counter[str] = Counter()
        self.source_ids: Counter[str] = Counter()

    def add_event(self, event: ResolvedEvent) -> None:
        self.events += 1

        if event.category is None:
            self.missing_category += 1
        else:
            self.categories[event.category] += 1

        raw_conf = event.attributes.get("confidence")
        if event.confidence is None:
            if raw_conf is not None:
                self.conf_unparseable += 1
        else:
            self.conf_n += 1
            self.conf_sum += event.confidence
            self.conf_min = min(self.conf_min, event.confidence)
            self.conf_max = max(self.conf_max, event.confidence)
            if event.confidence == 0.0:
                self.conf_zero += 1
            self.conf_buckets[_confidence_bucket(event.confidence)] += 1

        raw_found = event.attributes.get("found_at")
        if event.found_at is None:
            if raw_found is not None:
                self.date_unparseable += 1
        else:
            self.date_n += 1
            self.year_counts[event.found_at.year] += 1

        if event.company1_id is not None:
            self.company1_id_present += 1
        if event.company2_id is not None:
            self.company2_id_present += 1
        if event.source_article_id is not None:
            self.source_id_present += 1

        if event.company1 is not None:
            self.has_company1 += 1
        if event.company2 is not None:
            self.has_company2 += 1
        if event.source_article is not None:
            self.has_source += 1
        if event.unresolved_references:
            self.with_unresolved += 1
            self.total_unresolved += len(event.unresolved_references)

        if event.amount is not None:
            self.amount_present += 1
            if event.category is not None:
                self.amount_present_by_category[event.category] += 1

        self.event_ids[event.event_id] += 1
        if event.source_article_id is not None:
            self.source_ids[event.source_article_id] += 1

    def add_error(self, error: ParseError) -> None:
        self.parse_errors[error.error_type] += 1


def _confidence_bucket(value: float) -> str:
    if value < 0.0 or value > 1.0:
        return "out_of_range"
    index = min(int(value * 10), 9)
    low = index / 10
    high = low + 0.1
    return f"{low:.1f}-{high:.1f}"


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.1f}%" if whole else "n/a"


def build_report(acc: Accumulator, files: list[Path], *, top: int) -> dict[str, Any]:
    total_bytes = sum(path.stat().st_size for path in files)
    dup_ids = {eid: n for eid, n in acc.event_ids.items() if n > 1}
    multi_event_sources = {sid: n for sid, n in acc.source_ids.items() if n > 1}
    return {
        "files": len(files),
        "total_bytes": total_bytes,
        "events": acc.events,
        "parse_errors": dict(acc.parse_errors),
        "categories": {
            "distinct": len(acc.categories),
            "missing": acc.missing_category,
            "top": acc.categories.most_common(top),
        },
        "confidence": {
            "n": acc.conf_n,
            "mean": (acc.conf_sum / acc.conf_n) if acc.conf_n else None,
            "min": acc.conf_min if acc.conf_n else None,
            "max": acc.conf_max if acc.conf_n else None,
            "zero_count": acc.conf_zero,
            "unparseable": acc.conf_unparseable,
            "buckets": dict(sorted(acc.conf_buckets.items())),
        },
        "dates": {
            "n": acc.date_n,
            "unparseable": acc.date_unparseable,
            "min_year": min(acc.year_counts) if acc.year_counts else None,
            "max_year": max(acc.year_counts) if acc.year_counts else None,
            "by_year": dict(sorted(acc.year_counts.items())),
        },
        "relationships": {
            "company1_present": acc.has_company1,
            "company2_present": acc.has_company2,
            "source_present": acc.has_source,
            "with_unresolved_refs": acc.with_unresolved,
        },
        "amount": {
            "present": acc.amount_present,
            "present_by_financial_category": {
                category: acc.amount_present_by_category.get(category, 0)
                for category in FINANCIAL_CATEGORIES
            },
        },
        "duplicates": {
            "duplicate_event_ids": len(dup_ids),
            "articles_with_multiple_events": len(multi_event_sources),
        },
        "validation": {
            # Expected JSON:API structure & presence-of-data violations surface
            # as structural parse errors (a doc with no 'data' / no 'id').
            "structural_errors": dict(acc.parse_errors),
            # Relationship integrity (sampled across the whole stream): a target
            # id was declared but had no matching entity in 'included'.
            "records_with_dangling_refs": acc.with_unresolved,
            "total_dangling_refs": acc.total_unresolved,
            "relationship_resolution": {
                "company1": {"declared": acc.company1_id_present, "resolved": acc.has_company1},
                "company2": {"declared": acc.company2_id_present, "resolved": acc.has_company2},
                "source": {"declared": acc.source_id_present, "resolved": acc.has_source},
            },
            "integrity_ok_pct": _pct(acc.events - acc.with_unresolved, acc.events),
        },
    }


def print_report(report: dict[str, Any]) -> None:
    events = report["events"]
    out = sys.stdout.write

    out("\n=== VeritasAI dataset profile ===\n")
    out(f"files: {report['files']}   size: {report['total_bytes'] / 1e6:.1f} MB\n")
    out(f"events parsed: {events}   parse errors: {report['parse_errors'] or '{}'}\n")

    cats = report["categories"]
    out(f"\ncategories: {cats['distinct']} distinct (missing: {cats['missing']})\n")
    for name, count in cats["top"]:
        out(f"  {name:<28} {count:>8}  {_pct(count, events)}\n")

    conf = report["confidence"]
    mean = f"{conf['mean']:.3f}" if conf["mean"] is not None else "n/a"
    out(f"\nconfidence: n={conf['n']} mean={mean} ")
    out(f"min={conf['min']} max={conf['max']} zero={conf['zero_count']} ")
    out(f"unparseable={conf['unparseable']}\n")
    for bucket, count in conf["buckets"].items():
        out(f"  {bucket:<14} {count:>8}\n")

    dates = report["dates"]
    out(f"\ndates: n={dates['n']} span={dates['min_year']}-{dates['max_year']} ")
    out(f"unparseable={dates['unparseable']}\n")

    rel = report["relationships"]
    out("\nrelationship presence:\n")
    out(f"  company1 {_pct(rel['company1_present'], events)}   ")
    out(f"company2 {_pct(rel['company2_present'], events)}   ")
    out(f"source {_pct(rel['source_present'], events)}\n")
    out(f"  records with unresolved (dangling) refs: {rel['with_unresolved_refs']}\n")

    amount = report["amount"]
    out(f"\namount present: {_pct(amount['present'], events)} overall\n")
    for category, count in amount["present_by_financial_category"].items():
        out(f"  {category:<22} present in {count} events\n")

    dup = report["duplicates"]
    out(f"\nduplicate event ids: {dup['duplicate_event_ids']}\n")
    out(f"articles mapping to >1 event: {dup['articles_with_multiple_events']}\n")

    val = report["validation"]
    out("\nvalidation (JSON:API structure + relationship integrity):\n")
    out(f"  structural errors: {val['structural_errors'] or '{}'}\n")
    out(f"  records with dangling refs: {val['records_with_dangling_refs']} ")
    out(f"(total dangling ids: {val['total_dangling_refs']})\n")
    for rel_name, counts in val["relationship_resolution"].items():
        out(
            f"  {rel_name:<10} declared={counts['declared']:>8} "
            f"resolved={counts['resolved']:>8} "
            f"({_pct(counts['resolved'], counts['declared'])})\n"
        )
    out(f"  overall relationship integrity: {val['integrity_ok_pct']}\n")
    out("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile the news-events feed.")
    parser.add_argument("--root", type=Path, default=None, help="Override DATASET_ROOT.")
    parser.add_argument("--top", type=int, default=15, help="Top-N categories to show.")
    parser.add_argument("--json", type=Path, default=None, help="Write the report as JSON here.")
    parser.add_argument(
        "--progress-every", type=int, default=50_000, help="Log progress every N records."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)

    settings = get_settings()
    # Priority: --root flag > DATASET_ROOT env (folded into settings) > ./datasets.
    root: Path = args.root if args.root is not None else settings.dataset_root

    try:
        files = discover_dataset_files(
            root, settings.dataset_patterns, recursive=settings.dataset_recursive
        )
    except DatasetError as exc:
        logger.error("%s", exc)
        return 2

    if not files:
        logger.warning("No dataset files (%s) under %s", settings.dataset_patterns, root)
        return 1

    logger.info("Profiling %d file(s) under %s", len(files), root)
    acc = Accumulator()
    processed = 0
    for path in files:
        for result in iter_records(path):
            if isinstance(result, ResolvedEvent):
                acc.add_event(result)
            else:
                acc.add_error(result)
            processed += 1
            if args.progress_every and processed % args.progress_every == 0:
                logger.info("...%d records", processed)

    report = build_report(acc, files, top=args.top)
    print_report(report)

    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("Wrote JSON report to %s", args.json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
