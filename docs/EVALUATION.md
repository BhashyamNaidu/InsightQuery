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

**Last full run:** 2026-10-03 (all four evaluations in one `python scripts/evaluate.py`
invocation, run sequentially, after the SQL-repair and correctness-prompt changes).
This run includes the literal-`%` executor fix (§3b). Numbers from 2026-09-25 are kept only
where a before/after comparison is made.

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
| Accuracy | 0.80 (16/20) |
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
| sql | sql | 5 |

`rag` (5/5) and `sql` (5/5) classification were perfect in this run. The misses (4 of 20)
are 2 "hybrid" questions classified as pure "rag," a prompt-injection-style "rejected"
question where the classifier output couldn't be parsed and fell back to the default
"hybrid," and a "pretend you are a pirate" question routed to "sql" — i.e. not recognized
as out-of-scope, though (see `docs/SECURITY.md`) the downstream SQL validator would still
have caught anything unsafe it tried to produce. The previous run (2026-09-25) scored 0.75;
the 0.75 → 0.80 difference is one question on a 3B non-deterministic model and is not
evidence of improvement (no intent code or prompt was changed). This is a measured limitation of a 3B CPU-inference model doing 4-way
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
| | 2026-09-25 (before) | 2026-10-03 (after) |
|---|---|---|
| SQL generation rate | 0.85 | 0.90 |
| Validation pass rate | 0.60 | 0.45 |
| Execution success rate (of validated) | 0.667 | 0.889 (8/9) |
| Legitimate questions correctly allowed | 0.90 (9/10) | 0.90 (9/10) |
| **Malicious questions correctly blocked** | **1.00 (7/7)** | **1.00 (7/7)** |

The "after" run used the correctness prompt and bounded repair; 3 queries were repaired,
2 of those then executed (see §3b for why the before/after execution-success difference is
**not** evidence of improvement, and why validation pass rate fell: that run drew more
model errors that the validator correctly rejected, e.g. a query with no table).

The safety-critical number is the last one: every injection, destructive-request, and
unauthorized-access attempt in the eval set was blocked — either the model itself declined
to produce SQL for it, or `validate_sql()` rejected what it produced. Zero malicious
questions got through in either run.

The more interesting finding is the execution-success gap: of the SQL that passed
validation, a third still failed at actual Postgres execution — not from anything unsafe,
but from real semantic/type errors a 3B model made (e.g. `SUM()` on a boolean column,
comparing a `VARCHAR` district code to an integer literal, referencing a table alias that
was never joined). `validate_sql()` correctly scoped these to allowed tables/columns with a
safe row limit — it isn't designed to catch semantic or type errors, only safety
violations, and it didn't miss anything unsafe here. This is genuine evidence of a small
local model's SQL-generation ceiling, not a validator gap — see
`docs/nl2sql_eval_results.json` for the exact failing queries and errors.

## 3b. NL-to-SQL: did the correctness prompt + bounded repair help? (2026-10-03)

**Short answer: not demonstrably.** A single before/after comparison looked like a large
win, but repeated runs showed the apparent gain is within run-to-run variance of a
non-deterministic 3B model. What follows is the full measurement, including what was
wrong with the first interpretation.

**What changed:** (1) general PostgreSQL-correctness guidance added to the SQL prompt
(typed columns, boolean aggregation, zero-padded text district codes, date functions);
(2) one bounded repair attempt when PostgreSQL rejects an already-validated query, with the
repaired SQL re-validated before it runs (`docs/SQL_SAFETY.md`). Neither touched the
validator, allow-list, or database grants.

**Metric used:** legitimate questions (of 10) whose final SQL *executed without error*,
measured by a throwaway harness (outside the repo) that runs the same shared pipeline
under one configuration per arm. Three runs per arm; the original single-run baseline is
listed separately.

| Configuration | Runs (legit executed OK, of 10) | Mean |
|---|---|---|
| Old prompt, no repair (baseline re-measured) | 8, 6, 7 | 7.00 |
| *(original baseline run, 2026-09-25)* | *5* | — |
| New prompt, no repair | 8, 8, 7 | 7.67 |
| New prompt + repair (shipped config) | 9, 8, 6 | 7.67 |
| *(an earlier full evaluation run of the shipped config)* | *10* | — |
| *(final full evaluation run, 2026-10-03, shipped config, after the `%` fix)* | *8* | — |

- The same old configuration scored **5, 8, 6, 7** across four runs, and the shipped
  configuration scored **10, 9, 8, 6, 8** across five. A 10/10 result and a
  5/10 result are both ordinary draws; the headline "66.7% → 100%" from comparing one run to
  one run is not evidence of improvement.
- Prompt-only vs. old prompt: +0.67 questions on average (n=3 per arm) — smaller than the
  spread within any single arm.
- Repair on top of the new prompt: **no difference in mean** (7.67 vs 7.67). Across the three
  shipped-config runs there were **9 repair attempts, of which 3 (33%) executed
  successfully** (n=9; too small to generalize).
- **Safety did not change:** malicious/destructive/unauthorized-access questions were
  blocked **7/7 in every run** of the shipped config (5 runs including both full evaluation
  runs), and **0 malicious queries were ever executed**.

**Execution success overstates correctness.** Reviewing the actual *results* of the
10 legitimate queries from one run (manual review, not an automated metric): 6/10 were
semantically correct, **4/10 wrong despite executing** — an "average thefts per month" query
that filtered on a hallucinated `'THEORY'` literal (all zeros), "robberies in Austin"
returning 0 rows via an invented description string, "percentage arrested" returning
0.00038, and a "busiest weekday" query whose rows all carry the same constant label (its top
row is right only by coincidence: the constant is the weekday of 2023-01-01, a Sunday, which
happens to be the true busiest day at 38,714). The original baseline run's executed queries
reviewed the same way: 4/10 correct. Ground truth for these judgments came from
independent queries (true arrest rate 12.21%, Austin = community area 25, busiest weekday
Sunday). Semantic correctness is **not** automatically measured by `evaluate_nl2sql.py`;
that remains a limitation.

**Failure taxonomy (all runs, legitimate questions only):**

| Category | Examples seen | Handled by |
|---|---|---|
| Model error caught by the validator before execution | hallucinated column (`community_area_name`, `value`), typo (`ooccurred_at`), query with no table, SQL parse error | validator (correct rejections, not false positives) |
| PostgreSQL semantic/type error | `avg(boolean)`, `SUM(boolean)`, `varchar = integer`, nested aggregates, `SELECT DISTINCT` + `ORDER BY` | one repair attempt (about a third succeed) |
| PostgreSQL syntax error | `COUNT(*) OVER (PARTITION BY ...)` malformed | one repair attempt |
| **Application bug (found and fixed)** | a literal `%` in generated SQL (e.g. `LIKE 'THEFT%'`) failed in the driver — see below | executor fix |
| Infrastructure | one ablation run crashed once with an unrecorded error and passed on re-run; not reproduced | unexplained |

**An application bug surfaced by this analysis:** one execution failure
(`only '%s', '%b', '%t' are allowed as placeholders`) traced to psycopg treating any literal
`%` in the SQL as a parameter marker, so every `LIKE` pattern and the modulo operator failed
at execution. No evaluation question used `LIKE`, so no existing test or metric had
exercised it. Fixed in `app/nlsql/executor.py` with unit and real-database regression tests.
The evaluation runs in this section were taken *before* that fix; one ablation failure was
attributable to it, so the conclusions above stand, but the numbers were not re-run for it.

## 4. End-to-End Latency

Method: `scripts/evaluate_e2e.py` — 8 questions (2 per route type, sampled from the intent
eval set), run through the real `run_investigation()`, measuring total and per-stage
(intent/SQL/RAG/synthesis) latency. Deliberately small: each question can involve multiple
real LLM calls, and CPU inference is slow enough that a large sample would make this
impractical to re-run routinely — the p50/p95 figures below are reported with their sample
size alongside them precisely because a handful of measurements isn't a statistically
robust percentile in the way a real load test's would be.

| Metric | Value |
|---|---|
| Succeeded / total | 8 / 8 |
| Avg total latency | 46.0 s |
| p50 total latency (n=8) | 40.0 s |
| p95 total latency (n=8) | 80.1 s |
| Synthesis success rate | 1.00 (8/8) |

Per-stage average:

| Stage | Avg latency |
|---|---|
| Intent classification | 7.7 s |
| SQL generation + validation + execution (incl. repair if any) | 10.7 s |
| RAG retrieval | 0.1 s |
| LLM synthesis | 37.6 s |

Two things stand out, both expected given CPU-only inference on a 3B model (see
`docs/LLM_STRATEGY.md`): RAG retrieval is essentially free (local embeddings, no LLM call),
and synthesis dominates total latency — it's the longest prompt (question + SQL rows +
evidence chunks) generating the most output tokens (up to 1024) of any of the three LLM
calls in the pipeline. At ~46 seconds average end-to-end, this configuration is honestly
positioned as "runs correctly and free of charge," not "fast" — `LLM_PROVIDER=anthropic`
would very likely cut this to single-digit seconds at the cost of requiring a paid API key,
which is exactly the trade-off `docs/LLM_STRATEGY.md` describes rather than hides.

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
