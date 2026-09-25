# Evaluation

This is the consolidated evaluation report: what was measured, how, and the actual
numbers from the last full run of `python scripts/evaluate.py`. Each evaluation also has
its own detailed per-question report (`docs/*_eval_results.json`) and its own script,
runnable independently. The Metrics page (`/metrics` in the dashboard) reads these same
files live, so what's shown there and what's written here are the same numbers, not two
separately-maintained claims.

**Run against:** `LLM_PROVIDER=ollama`, model `llama3.2:3b` (Q4_K_M quantization), CPU-only
inference (see `docs/LLM_STRATEGY.md` for why), against the live Docker Postgres/pgvector
deployment with the real 263,841-row 2023 Chicago crime dataset loaded.

**Last run:** 2026-09-25.

## 1. RAG Retrieval

Method: `scripts/evaluate_rag.py` — 15 hand-written questions (`data/rag_eval_set.json`),
one targeted at each of the 15 reference documents, run through the real retrieval path
(sentence-transformers embedding + pgvector cosine similarity — this evaluation needs no
LLM at all, so it's identical regardless of `LLM_PROVIDER`).

| Metric | Value |
|---|---|
| Recall@5 | 1.0 |
| MRR | 0.956 |

14 of 15 questions retrieved their expected document at rank 1; one (ward vs. community
area) retrieved a plausible related document first before the expected one at rank 3. See
`docs/RAG_EVALUATION.md` for full methodology and honest limitations of this evaluation
(small hand-curated set, one-expected-document-per-question scoring).

## 2. Intent Classification

Method: `scripts/evaluate_intent.py` — 20 questions (`data/eval/intent_eval_set.json`), 5
each across sql/rag/hybrid/rejected, run through the real `classify_intent()` (a real LLM
call every time, not mocked).

| Metric | Value |
|---|---|
| Accuracy | 0.75 (15/20) |
| Rejected rate | 0.15 |

Confusion matrix (expected → actual):

| Expected | Actual | Count |
|---|---|---|
| hybrid | hybrid | 3 |
| hybrid | rag | 2 |
| rag | rag | 5 |
| rejected | hybrid | 1 |
| rejected | rejected | 3 |
| rejected | sql | 1 |
| sql | hybrid | 1 |
| sql | sql | 4 |

`rag` classification was perfect (5/5). The model's confusion is concentrated in two
places: "hybrid" questions (ones needing both a number and interpretation) sometimes get
classified as pure "rag," and one prompt-injection-style "rejected" question got routed to
"sql" instead — meaning it wasn't correctly recognized as out-of-scope, though (see
`docs/SECURITY.md`) the downstream SQL validator would still have caught anything unsafe it
tried to produce. This is a measured limitation of a 3B CPU-inference model doing 4-way
classification, not a claim that intent routing is unreliable in general — see
`docs/LLM_STRATEGY.md`'s trade-off section.

## 3. NL-to-SQL

Method: `scripts/evaluate_nl2sql.py` — 20 cases (`data/eval/nl2sql_eval_set.json`): 10
legitimate analytical questions (aggregation, filter, grouping, date, top-N), 7
injection/destructive/unauthorized-access attempts, 3 unscored ambiguous/invalid edge
cases. Every case calls the real `generate_sql()` (real LLM call) and, if validation
passes, actually executes the SQL against the live database.

| Metric | Value |
|---|---|
| SQL generation rate | 0.85 |
| Validation pass rate | 0.60 |
| Execution success rate (of validated) | 0.667 |
| Legitimate questions correctly allowed | 0.90 (9/10) |
| **Malicious questions correctly blocked** | **1.00 (7/7)** |

The safety-critical number is the last one: every injection, destructive-request, and
unauthorized-access attempt in the eval set was blocked — either the model itself declined
to produce SQL for it, or `validate_sql()` rejected what it produced. Zero malicious
questions got through in this run.

The more interesting finding is the execution-success gap: of the SQL that passed
validation, a third still failed at actual Postgres execution — not from anything unsafe,
but from real semantic/type errors a 3B model made (e.g. `SUM()` on a boolean column,
comparing a `VARCHAR` district code to an integer literal, referencing a table alias that
was never joined). `validate_sql()` correctly scoped these to allowed tables/columns with a
safe row limit — it isn't designed to catch semantic or type errors, only safety
violations, and it didn't miss anything unsafe here. This is genuine evidence of a small
local model's SQL-generation ceiling, not a validator gap — see
`docs/nl2sql_eval_results.json` for the exact failing queries and errors.

## 4. End-to-End Latency

Method: `scripts/evaluate_e2e.py` — 8 questions (2 per route type, sampled from the intent
eval set), run through the real `run_investigation()`, measuring total and per-stage
(intent/SQL/RAG/synthesis) latency. Deliberately small: each question can involve multiple
real LLM calls, and CPU inference is slow enough that a large sample would make this
impractical to re-run routinely — the p50/p95 figures below are reported with their sample
size alongside them precisely because a handful of measurements isn't a statistically
robust percentile in the way a real load test's would be.

<!-- EVAL:E2E -->

## How to reproduce

```bash
python scripts/evaluate.py
```

Runs all four and writes `docs/evaluation_results.json` (the combined summary) plus each
evaluation's own detailed report. Requires the live database and a working `LLM_PROVIDER`
for everything except RAG retrieval.

## What these numbers do and don't establish

- They establish that the pipeline works end-to-end against a real local model, that the
  SQL safety validator's rejection behavior holds under real (not simulated) LLM output,
  and that RAG retrieval is accurate on this corpus.
- They do **not** establish statistically robust accuracy claims at scale — every eval set
  here is intentionally small (15-20 cases) so a reviewer can read every question and every
  result individually, which is a different and, for a portfolio project, more honest goal
  than a large number nobody can inspect.
- Intent/NL-to-SQL numbers are specific to `llama3.2:3b`. A stronger model (including
  `LLM_PROVIDER=anthropic`) would very likely score higher on strict-JSON-format
  reliability specifically — that gap itself is part of what `docs/LLM_STRATEGY.md`'s
  trade-off section is describing, not a flaw unique to this codebase.
