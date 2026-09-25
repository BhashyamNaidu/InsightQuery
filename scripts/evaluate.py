"""Runs every evaluation (RAG retrieval, intent classification, NL-to-SQL, and
end-to-end latency) and writes a single combined summary to
docs/evaluation_results.json, alongside each evaluation's own detailed report
(docs/rag_eval_results.json, docs/intent_eval_results.json,
docs/nl2sql_eval_results.json, docs/e2e_eval_results.json).

This is the one command to run for a full, current set of measured numbers:

    python scripts/evaluate.py

Requires a live database (for RAG/NL-to-SQL/e2e) and a working LLM_PROVIDER (for
intent/NL-to-SQL/e2e — RAG retrieval alone needs no LLM, it's local embeddings).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def main() -> None:
    settings = get_settings()
    summary: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llm_provider": settings.llm_provider,
    }

    print("=" * 60)
    print("1/4  RAG retrieval evaluation")
    print("=" * 60)
    import evaluate_rag

    rag_report = evaluate_rag.evaluate(top_k=5)
    (DOCS_DIR / "rag_eval_results.json").write_text(json.dumps(rag_report, indent=2), encoding="utf-8")
    summary["rag"] = {"recall_at_5": rag_report["recall_at_5"], "mrr": rag_report["mrr"]}
    print(f"recall@5={rag_report['recall_at_5']}  mrr={rag_report['mrr']}\n")

    print("=" * 60)
    print("2/4  Intent classification evaluation")
    print("=" * 60)
    import evaluate_intent

    intent_report = evaluate_intent.evaluate()
    (DOCS_DIR / "intent_eval_results.json").write_text(json.dumps(intent_report, indent=2), encoding="utf-8")
    summary["intent"] = {
        "accuracy": intent_report["accuracy"],
        "rejected_rate": intent_report["rejected_rate"],
    }
    print(f"accuracy={intent_report['accuracy']}\n")

    print("=" * 60)
    print("3/4  NL-to-SQL evaluation")
    print("=" * 60)
    import evaluate_nl2sql

    nl2sql_report = evaluate_nl2sql.evaluate()
    (DOCS_DIR / "nl2sql_eval_results.json").write_text(json.dumps(nl2sql_report, indent=2), encoding="utf-8")
    summary["nl2sql"] = {
        "sql_generation_rate": nl2sql_report["sql_generation_rate"],
        "validation_pass_rate": nl2sql_report["validation_pass_rate"],
        "execution_success_rate": nl2sql_report["execution_success_rate"],
        "malicious_questions_correctly_blocked": nl2sql_report["malicious_questions_correctly_blocked"],
    }
    print(f"malicious_blocked={nl2sql_report['malicious_questions_correctly_blocked']}\n")

    print("=" * 60)
    print("4/4  End-to-end latency evaluation")
    print("=" * 60)
    import evaluate_e2e

    e2e_report = evaluate_e2e.evaluate()
    (DOCS_DIR / "e2e_eval_results.json").write_text(json.dumps(e2e_report, indent=2), encoding="utf-8")
    summary["e2e"] = {
        "avg_total_latency_ms": e2e_report["avg_total_latency_ms"],
        "avg_stage_latency_ms": e2e_report["avg_stage_latency_ms"],
        "n_succeeded": e2e_report["n_succeeded"],
        "n_failed": e2e_report["n_failed"],
    }
    print(f"avg_total_latency_ms={e2e_report['avg_total_latency_ms']}\n")

    out_path = DOCS_DIR / "evaluation_results.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"Combined summary written to {out_path}")
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
