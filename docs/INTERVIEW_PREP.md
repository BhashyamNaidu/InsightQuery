# Interview Prep: Explaining Every Architectural Decision

Format: decision -> the actual reason -> the follow-up question an interviewer might ask
and how to answer it honestly.

## "Why is the LLM not allowed to run its own SQL?"

Because letting an LLM execute arbitrary generated SQL against a real database is a
known, well-documented failure class — prompt injection or an unlucky phrasing can produce
a destructive or exfiltrating query, and even a well-behaved model can write something too
expensive. The fix isn't "trust it more" or "add a system prompt telling it not to" — it's
architectural: `validate_sql()` (`app/nlsql/validator.py`) parses the SQL into an AST and
allow-lists everything (statement type, tables, columns, functions), independent of a
Postgres role that has `SELECT`-only grants on exactly four tables. Two independent layers
have to fail for anything unsafe to execute.

*Follow-up: "What if the validator has a bug?"* — That's exactly why the DB role exists
too. A validator bug degrades to "the query still can't write anything," not "game over."
That's the actual argument for defense in depth, not a buzzword.

*Follow-up: "Why sqlglot and not just regex/keyword blocking?"* — Because keyword
blocking is trivially bypassed (comments, encoding tricks, alternate syntax) and doesn't
understand structure — it can't tell you whether `SELECT` even matches the intended tables.
Parsing to an AST and checking node types/table references is the only way to reason about
what the SQL actually does rather than what it superficially looks like.

## "Why Chicago crime data instead of a sales/e-commerce dataset?"

Two reasons, and both matter. First, it's real public data with a genuine reporting-lag,
classification, and privacy story — which gives legitimate, sourceable content for the RAG
corpus (IUCR/FBI classification, data-quality caveats) instead of inventing filler
documents. Second, it fits the "investigation" framing literally, which matters for a
system whose whole point is auditability over confident-sounding answers.

## "Why a relational star-schema instead of one flat table?"

The crimes table is genuinely a fact table with three real dimensions (classification
code, district, community area) reused across hundreds of thousands of rows — normalizing
them isn't cargo-culting a textbook pattern, it buys referential integrity (an FK to
`iucr_codes` fails loudly if the ingestion pipeline tries to insert a bad code) and smaller
indexes on the dimension tables for the join-heavy comparison queries in
`app/analytics/queries.py`.

## "Why sentence-transformers locally instead of an embeddings API?"

Cost and dependency isolation: the only paid API call in the whole system is the final
synthesis call (and, more cheaply, intent classification and SQL generation). Embeddings
run once at ingestion time for a small, static, 15-document corpus — paying per-call API
latency and cost for that doesn't buy anything here. This would be a real tradeoff to
revisit if the corpus were large and constantly changing.

## "Why not just use LangChain / an agent framework?"

Because the value this system demonstrates is the safety and auditability boundaries
themselves — the validator, the read-only role, the evidence-only synthesis prompt — and
those are a few hundred lines of code that are much easier to reason about, test, and
explain in an interview when they're not buried inside a framework's abstraction layers.
An agent framework would also invite exactly the kind of scope creep (tool-calling loops,
multi-step planning) the project spec explicitly rules out — this system doesn't need an
agent loop because its question-answering shape is fixed and well-understood upfront.

## "Walk me through what happens end to end for one question."

Use the diagram in `README.md`/`docs/architecture.svg` and narrate it left to right:
intent classification (LLM, constrained JSON) -> SQL generation (LLM) -> validation
(deterministic, `app/nlsql/validator.py`) -> execution (read-only role,
`app/nlsql/executor.py`) in parallel/independent of -> retrieval (pgvector,
`app/rag/retrieval.py`) -> both results handed to synthesis (LLM,
`app/llm/synthesis.py`) with an explicit "this is data, not instructions" framing around
the evidence -> a schema-validated JSON answer with citations, or an honest
"insufficient evidence" if the schema validation fails twice.

## "What's the weakest part of this system, honestly?"

Answer straight from `docs/LIMITATIONS.md` #1 and #2 (the column-allow-list simplification
and the small RAG evaluation set). Naming your own weak points precisely, with the reason
they were accepted rather than fixed, reads as more senior than claiming there aren't any.

## "Tell me about a real bug you found and fixed."

This project's git history has several genuine ones, found only once it ran against a
real Docker deployment rather than mocked tests — good material because each has a clear
root cause and a specific fix, not a vague "I debugged some issues."

- **A database access boundary gap.** The read-only Postgres role that executes generated
  SQL was supposed to have `SELECT` on exactly four tables. Direct-connection testing
  (`psql` as that role, bypassing the app entirely) found it could also read `query_log` —
  which contains every question and generated SQL string this system has ever logged.
  Root cause: `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES` grants on *every*
  current and future table, not a scoped subset — a one-line mistake with a real
  confidentiality consequence. Fixed by removing it in favor of explicit, named grants,
  and re-verified against a *from-scratch* container rebuild, not just a patch to the
  already-running one (see `docs/SQL_SAFETY.md`).
- **A safety-critical function that could crash instead of reject.** `validate_sql()` is
  documented as this system's single safety boundary — it must always return a decision,
  never raise. Adversarial input testing found it did raise, on plain non-string input,
  because `(x or "").strip()` doesn't guard against a truthy non-string like the int `123`.
  The fix is one `isinstance` check; the lesson is that "the function that must never
  fail" needs its own explicit input-validation test, not just tests of its happy path.
- **A silent auditability gap during an LLM outage.** With no Anthropic API key configured
  (a real outage, encountered while testing, not a simulated one), the whole
  `/investigate` pipeline raised before a `query_log` row was ever written — meaning the
  exact moment auditability matters most (something went wrong) is when this system
  produced no audit trail at all. Fixed by making every LLM-dependent stage degrade to an
  explicit, logged failure state instead of raising — the same pattern the synthesis stage
  already used, just not consistently applied to the earlier stages yet.
- **A quieter one: retrying a permanent failure.** The same outage testing showed a failed
  request taking ~40 seconds to fail, because the retry decorator retried a missing-API-key
  error (which fails identically every time) exactly like a transient rate limit. Narrowing
  retries to actually-transient error types cut that to under a second — a reminder that
  "add retries" isn't automatically a resilience improvement without also asking *which*
  failures are worth retrying.

The throughline across all four: none were found by reasoning about the code in the
abstract — all four needed the system actually running against real infrastructure
(a live database, a live/absent API key) before they were even visible.
