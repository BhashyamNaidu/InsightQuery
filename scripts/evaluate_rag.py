"""Measure retrieval quality against the hand-written evaluation set
(data/rag_eval_set.json) with recall@k and MRR — an honest, small-scale
measurement, not a claim of exhaustive coverage. Requires the document
corpus to already be ingested (scripts/ingest_documents.py).

Usage:
    python scripts/evaluate_rag.py [--top-k 5]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.rag.retrieval import retrieve

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "rag_eval_set.json"


def evaluate(top_k: int = 5) -> dict:
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))

    hits_at_k = 0
    reciprocal_ranks: list[float] = []
    per_question_results = []

    with SessionLocal() as session:
        for case in eval_set:
            question = case["question"]
            expected = case["expected_document"]

            results = retrieve(session, question, top_k=top_k)
            titles = [r.document_title for r in results]

            rank = titles.index(expected) + 1 if expected in titles else None
            hit = rank is not None
            hits_at_k += int(hit)
            reciprocal_ranks.append(1.0 / rank if hit else 0.0)

            per_question_results.append(
                {
                    "question": question,
                    "expected_document": expected,
                    "retrieved_titles": titles,
                    "rank": rank,
                    "hit": hit,
                }
            )

    n = len(eval_set)
    recall_at_k = hits_at_k / n if n else 0.0
    mrr = sum(reciprocal_ranks) / n if n else 0.0

    return {
        "top_k": top_k,
        "n_questions": n,
        f"recall_at_{top_k}": round(recall_at_k, 3),
        "mrr": round(mrr, 3),
        "per_question": per_question_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    report = evaluate(top_k=args.top_k)
    recall_key = f"recall_at_{report['top_k']}"

    print(f"n_questions:     {report['n_questions']}")
    print(f"recall@{report['top_k']}:      {report[recall_key]}")
    print(f"MRR:             {report['mrr']}")
    print()
    for r in report["per_question"]:
        status = "HIT " if r["hit"] else "MISS"
        print(f"[{status}] rank={r['rank']}  {r['question']!r}")
        if not r["hit"]:
            print(f"         expected: {r['expected_document']!r}")
            print(f"         got:      {r['retrieved_titles']}")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "rag_eval_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
