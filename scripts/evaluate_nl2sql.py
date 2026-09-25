"""Measures the NL-to-SQL pipeline against data/eval/nl2sql_eval_set.json by
actually calling generate_sql() (a real LLM call) and, for anything that passes
validation, actually executing it against the live database — never a simulated
or hand-typed result.

Each case has an `expect_blocked` field:
  - false: a legitimate analytical question — expected to validate and execute.
  - true:  an injection/destructive/unauthorized-access attempt — expected to be
           rejected by validate_sql() (this measures the safety rejection rate).
  - null:  invalid/ambiguous/edge-case input with no single correct behavior —
           observed and reported, not scored pass/fail.

Usage:
    python scripts/evaluate_nl2sql.py
"""
from __future__ import annotations

import json
from pathlib import Path

from app.nlsql.executor import execute_readonly
from app.nlsql.generator import generate_sql

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "nl2sql_eval_set.json"


def evaluate() -> dict:
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))

    per_question = []
    for case in eval_set:
        question = case["question"]
        entry = {
            "question": question,
            "category": case["category"],
            "expect_blocked": case["expect_blocked"],
        }

        try:
            gen = generate_sql(question)
        except Exception as exc:  # noqa: BLE001 - record the failure, keep evaluating
            entry.update(
                {
                    "sql_generated": False,
                    "validation_ok": None,
                    "execution_ok": None,
                    "error": f"generate_sql raised: {exc}",
                }
            )
            per_question.append(entry)
            continue

        entry["generated_sql"] = gen.raw_sql
        entry["sql_generated"] = gen.raw_sql is not None
        entry["validation_ok"] = gen.validation.ok
        entry["rejection_reason"] = gen.validation.reason

        if gen.validation.ok:
            try:
                rows = execute_readonly(gen.validation.sql)
                entry["execution_ok"] = True
                entry["row_count"] = len(rows)
            except Exception as exc:  # noqa: BLE001
                entry["execution_ok"] = False
                entry["error"] = f"execution raised: {exc}"
        else:
            entry["execution_ok"] = None

        if case["expect_blocked"] is not None:
            expected_validation_ok = not case["expect_blocked"]
            entry["safety_correct"] = gen.validation.ok == expected_validation_ok

        per_question.append(entry)

    scored = [q for q in per_question if q["expect_blocked"] is not None]
    legit = [q for q in scored if not q["expect_blocked"]]
    malicious = [q for q in scored if q["expect_blocked"]]

    n = len(eval_set)
    sql_generated_count = sum(1 for q in per_question if q.get("sql_generated"))
    validation_ok_count = sum(1 for q in per_question if q.get("validation_ok"))
    execution_ok_count = sum(1 for q in per_question if q.get("execution_ok"))

    return {
        "n_questions": n,
        "sql_generation_rate": round(sql_generated_count / n, 3) if n else 0.0,
        "validation_pass_rate": round(validation_ok_count / n, 3) if n else 0.0,
        "execution_success_rate": (
            round(execution_ok_count / validation_ok_count, 3) if validation_ok_count else None
        ),
        "legit_questions_correctly_allowed": (
            round(sum(1 for q in legit if q["safety_correct"]) / len(legit), 3) if legit else None
        ),
        "malicious_questions_correctly_blocked": (
            round(sum(1 for q in malicious if q["safety_correct"]) / len(malicious), 3)
            if malicious
            else None
        ),
        "n_legit": len(legit),
        "n_malicious": len(malicious),
        "n_unscored_edge_cases": n - len(scored),
        "per_question": per_question,
    }


def main() -> None:
    report = evaluate()

    print(f"n_questions:                  {report['n_questions']}")
    print(f"sql_generation_rate:          {report['sql_generation_rate']}")
    print(f"validation_pass_rate:         {report['validation_pass_rate']}")
    print(f"execution_success_rate:       {report['execution_success_rate']}")
    print(f"legit correctly allowed:      {report['legit_questions_correctly_allowed']} (n={report['n_legit']})")
    print(f"malicious correctly blocked:  {report['malicious_questions_correctly_blocked']} (n={report['n_malicious']})")
    print()
    for q in report["per_question"]:
        if q.get("safety_correct") is False:
            print(f"SAFETY FAILURE [{q['category']}]: {q['question']!r}")
            print(f"  generated_sql={q.get('generated_sql')!r} validation_ok={q.get('validation_ok')}")
        elif q["expect_blocked"] is None:
            print(f"EDGE CASE [{q['category']}]: {q['question']!r} -> validation_ok={q.get('validation_ok')} sql={q.get('generated_sql')!r}")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "nl2sql_eval_results.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
