"""Classification metrics for judge evaluation.

The labels are three classes (pass / fail / uncertain), so precision/recall/F1
are computed one-vs-rest per class and **macro-averaged** over the classes that
actually appear in the gold labels (an absent class does not drag the average).
Accuracy is exact-match over all examples. Zero-division yields 0.0 by
convention (documented in ``docs/evaluation-strategy.md``).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from veritas.domain.models import VerdictStatus

Pair = tuple[VerdictStatus, VerdictStatus]  # (gold, predicted)
_CLASSES: tuple[VerdictStatus, ...] = (
    VerdictStatus.PASS,
    VerdictStatus.FAIL,
    VerdictStatus.UNCERTAIN,
)


class ClassMetrics(BaseModel):
    label: str
    precision: float
    recall: float
    f1: float
    support: int


class Metrics(BaseModel):
    n: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: list[ClassMetrics]

    def tracked(self) -> dict[str, float]:
        """The metrics regression detection watches."""
        return {
            "accuracy": self.accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
        }


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def score(pairs: Sequence[Pair]) -> Metrics:
    total = len(pairs)
    correct = sum(1 for gold, pred in pairs if gold == pred)

    per_class: list[ClassMetrics] = []
    macro_p = macro_r = macro_f = 0.0
    counted = 0
    for cls in _CLASSES:
        tp = sum(1 for gold, pred in pairs if gold == cls and pred == cls)
        fp = sum(1 for gold, pred in pairs if gold != cls and pred == cls)
        fn = sum(1 for gold, pred in pairs if gold == cls and pred != cls)
        support = sum(1 for gold, _ in pairs if gold == cls)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_class.append(
            ClassMetrics(
                label=cls.value, precision=precision, recall=recall, f1=f1, support=support
            )
        )
        if support > 0:
            macro_p += precision
            macro_r += recall
            macro_f += f1
            counted += 1

    return Metrics(
        n=total,
        accuracy=_safe_div(correct, total),
        macro_precision=_safe_div(macro_p, counted),
        macro_recall=_safe_div(macro_r, counted),
        macro_f1=_safe_div(macro_f, counted),
        per_class=per_class,
    )
