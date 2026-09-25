"""Measures end-to-end /investigate latency (total + per-stage: intent, SQL,
RAG, synthesis) by actually running run_investigation() for a representative
sample of questions — 2 per route type from data/eval/intent_eval_set.json, kept
small deliberately since each question can involve multiple real LLM calls and
CPU-based local inference (the default provider, see docs/LLM_STRATEGY.md) is
slow enough that a large sample would make this evaluation impractical to re-run.

Usage:
    python scripts/evaluate_e2e.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from app.services.investigation import run_investigation

INTENT_EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "intent_eval_set.json"


def _sample_questions(n_per_route: int = 2) -> list[dict]:
    eval_set = json.loads(INTENT_EVAL_SET_PATH.read_text(encoding="utf-8"))
    by_route: dict[str, list[dict]] = {}
    for case in eval_set:
        by_route.setdefault(case["expected_route"], []).append(case)
    sample = []
    for route, cases in by_route.items():
        sample.extend(cases[:n_per_route])
    return sample


def evaluate() -> dict:
    sample = _sample_questions()
    per_question = []

    for case in sample:
        question = case["question"]
        try:
            response = run_investigation(question)
            per_question.append(
                {
                    "question": question,
                    "expected_route": case["expected_route"],
                    "actual_route": response.route.value,
                    "total_latency_ms": response.latency_ms,
                    "stage_latency_ms": response.stage_latency_ms,
                    "synthesis_succeeded": response.synthesis is not None,
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - record and keep going
            per_question.append(
                {
                    "question": question,
                    "expected_route": case["expected_route"],
                    "error": str(exc),
                }
            )

    successes = [q for q in per_question if q.get("error") is None]
    total_latencies = [q["total_latency_ms"] for q in successes]
    stage_latencies: dict[str, list[int]] = {}
    for q in successes:
        for stage, ms in q["stage_latency_ms"].items():
            stage_latencies.setdefault(stage, []).append(ms)

    def _avg(values: list[int]) -> float | None:
        return round(statistics.mean(values), 1) if values else None

    def _percentile(values: list[int], pct: float) -> float | None:
        # A percentile computed from a handful of samples (this eval set is
        # deliberately small — see the module docstring) is not a statistically
        # robust p50/p95 in the sense a load-test with thousands of requests
        # would produce; it's reported as "the pct-th value of n samples" and the
        # sample size is always included alongside it so it's never read as more
        # precise than it is.
        if not values:
            return None
        return round(statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1], 1)

    return {
        "n_questions": len(sample),
        "n_succeeded": len(successes),
        "n_failed": len(per_question) - len(successes),
        "avg_total_latency_ms": _avg(total_latencies),
        "p50_total_latency_ms": _percentile(total_latencies, 50) if len(total_latencies) >= 2 else None,
        "p95_total_latency_ms": _percentile(total_latencies, 95) if len(total_latencies) >= 2 else None,
        "latency_sample_size": len(total_latencies),
        "avg_stage_latency_ms": {stage: _avg(values) for stage, values in stage_latencies.items()},
        "synthesis_success_rate": (
            round(sum(1 for q in successes if q["synthesis_succeeded"]) / len(successes), 3)
            if successes
            else None
        ),
        "per_question": per_question,
    }


def main() -> None:
    report = evaluate()

    print(f"n_questions:          {report['n_questions']}")
    print(f"n_succeeded:          {report['n_succeeded']}")
    print(f"n_failed:             {report['n_failed']}")
    print(f"avg_total_latency_ms: {report['avg_total_latency_ms']}")
    print("avg_stage_latency_ms:")
    for stage, ms in report["avg_stage_latency_ms"].items():
        print(f"  {stage:12} {ms} ms")
    print(f"synthesis_success_rate: {report['synthesis_success_rate']}")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "e2e_eval_results.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
