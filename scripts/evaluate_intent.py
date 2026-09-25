"""Measures intent-classification accuracy against data/eval/intent_eval_set.json
by actually calling classify_intent() (a real LLM call under whatever LLM_PROVIDER
is configured) for every question — never a hand-typed or simulated result.

Usage:
    python scripts/evaluate_intent.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.services.intent import classify_intent

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "intent_eval_set.json"


def evaluate() -> dict:
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))

    correct = 0
    confusion: Counter[tuple[str, str]] = Counter()
    per_question = []

    for case in eval_set:
        question = case["question"]
        expected = case["expected_route"]

        result = classify_intent(question)
        actual = result.route.value
        is_correct = actual == expected
        correct += int(is_correct)
        confusion[(expected, actual)] += 1

        per_question.append(
            {
                "question": question,
                "expected_route": expected,
                "actual_route": actual,
                "reasoning": result.reasoning,
                "correct": is_correct,
            }
        )

    n = len(eval_set)
    rejected_count = sum(1 for c in per_question if c["actual_route"] == "rejected")

    return {
        "n_questions": n,
        "accuracy": round(correct / n, 3) if n else 0.0,
        "rejected_rate": round(rejected_count / n, 3) if n else 0.0,
        "confusion_matrix": [
            {"expected": e, "actual": a, "count": c} for (e, a), c in sorted(confusion.items())
        ],
        "per_question": per_question,
    }


def main() -> None:
    report = evaluate()

    print(f"n_questions: {report['n_questions']}")
    print(f"accuracy:    {report['accuracy']}")
    print(f"rejected_rate: {report['rejected_rate']}")
    print()
    print("confusion matrix (expected -> actual : count):")
    for row in report["confusion_matrix"]:
        marker = "  " if row["expected"] == row["actual"] else "**"
        print(f"  {marker} {row['expected']:10} -> {row['actual']:10} : {row['count']}")
    print()
    for q in report["per_question"]:
        if not q["correct"]:
            print(f"MISS  expected={q['expected_route']:10} actual={q['actual_route']:10} {q['question']!r}")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "intent_eval_results.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
