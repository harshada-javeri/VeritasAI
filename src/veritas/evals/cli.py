"""``make eval`` entry point.

Outputs summary metrics, worst failures, and (when two prompt versions exist or
``--compare`` is given) a regression report. Exits non-zero if any tracked metric
drops more than the configured threshold. Replay-only — no live model calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from veritas.config import get_settings
from veritas.evals.dataset import available_prompt_versions, list_datasets
from veritas.evals.report import format_comparison, format_result
from veritas.evals.runner import compare_prompts, run_dataset


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="veritas-eval", description="Evaluate judge prompts.")
    parser.add_argument("--dataset", action="append", help="Dataset (repeatable; default all).")
    parser.add_argument("--prompt-version", help="Evaluate a single prompt version.")
    parser.add_argument("--compare", action="store_true", help="Compare two prompt versions.")
    parser.add_argument("--baseline", help="Baseline prompt version for comparison.")
    parser.add_argument("--candidate", help="Candidate prompt version for comparison.")
    parser.add_argument("--threshold", type=float, help="Regression threshold.")
    parser.add_argument("--top", type=int, default=5, help="Worst failures to show per dataset.")
    parser.add_argument("--json", type=Path, help="Also write the full report as JSON here.")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> tuple[str, int, list[dict[str, Any]]]:
    settings = get_settings()
    default_threshold = settings.evals.regression_threshold
    threshold = args.threshold if args.threshold is not None else default_threshold
    names: list[str] = args.dataset if args.dataset else list_datasets()

    blocks: list[str] = []
    payload: list[dict[str, Any]] = []
    exit_code = 0

    for name in names:
        versions = available_prompt_versions(name)
        has_pair = args.baseline is not None and args.candidate is not None
        explicit_compare = args.compare or has_pair

        if args.prompt_version:
            result = await run_dataset(name, args.prompt_version)
            blocks.append(format_result(result, top=args.top))
            payload.append(result.model_dump(mode="json"))
        elif explicit_compare or len(versions) >= 2:
            if len(versions) < 2 and not (args.baseline and args.candidate):
                blocks.append(f"## {name}: only one prompt version {versions}; comparison skipped")
                continue
            baseline = args.baseline or versions[-2]
            candidate = args.candidate or versions[-1]
            comparison = await compare_prompts(name, baseline, candidate, threshold)
            blocks.append(format_comparison(comparison, top=args.top))
            payload.append(comparison.model_dump(mode="json"))
            if comparison.regression.regressed:
                exit_code = 1
        else:
            version = versions[-1]
            result = await run_dataset(name, version)
            blocks.append(format_result(result, top=args.top))
            payload.append(result.model_dump(mode="json"))

    return "\n\n".join(blocks), exit_code, payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    text, exit_code, payload = asyncio.run(_run(args))
    sys.stdout.write(text + "\n")
    if args.json is not None:
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if exit_code:
        sys.stdout.write("\nEVAL FAILED: a tracked metric regressed beyond the threshold.\n")
    return exit_code
