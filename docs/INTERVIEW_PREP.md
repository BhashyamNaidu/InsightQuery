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

---

# Topic-by-topic reference

The sections above are decision-and-follow-up format. This section is organized by
subject area instead, for when the question is "tell me about your approach to X" rather
than "why did you do Y."

## Backend

**API design.** Two route modules on purpose: `app/api/routes.py` (JSON API — `/health`,
`/investigate`, `/sql/query`, `/rag/retrieve`, `/evidence/{id}`, `/investigations`,
`/evaluations`) and `app/web/routes.py` (HTML pages that call the JSON API client-side via
`fetch()`). Keeping presentation and API concerns in separate modules means the JSON API
can be used, tested, and reasoned about independently of whether a dashboard exists at all.

**Dependency injection.** FastAPI's `Depends(get_db)` (`app/db/session.py`) hands each
request its own SQLAlchemy session, closed via the generator's `finally` block regardless
of whether the request succeeded — no session leakage across requests, no shared mutable
state between concurrent requests.

**Database connections.** Two separate engines, not one: `SessionLocal` (read/write, for
the app's own bookkeeping — ingestion, `query_log`) and `ReadOnlySessionLocal` (connects as
`insightquery_readonly`, a Postgres role with `SELECT`-only grants on exactly four tables —
see `docs/SQL_SAFETY.md`). LLM-generated SQL only ever runs through the second one. This
is enforced by which engine the code path uses, not by a runtime permission check that
could be forgotten.

**Migrations.** Alembic, one migration per real schema change, including a "we were wrong"
one: migration `0002` drops a `UNIQUE` constraint the initial schema had, once real data
showed `case_number` isn't actually unique (20 of 263,841 rows share one). Migration `0003`
added per-stage latency and `llm_provider` columns to `query_log` when the evaluation work
needed them. Neither the wrong original migration nor its fix were edited after the fact —
each is its own commit, preserving why the schema looks the way it does now.

**Transactions.** Each request-scoped session (`get_db`) is one transaction, committed or
rolled back at the end of the request. `scripts/ingest_data.py`'s bulk inserts are chunked
(1000 rows/`INSERT`, staying under Postgres's 65,535-bound-parameter limit — found by
hitting it on the real 263,841-row dataset) but committed as one transaction per script
run, so a failure partway through rolls back cleanly rather than leaving a half-loaded
table.

**Error handling.** Every LLM-dependent stage degrades to an explicit, logged failure state
instead of raising (`app/services/investigation.py`) — see the "silent auditability gap"
bug above for why this matters more than it might sound. API errors distinguish causes:
`422` for request validation, `502` for a downstream dependency failure (LLM or DB) with a
specific `error_code`, `500` only for a genuinely unexpected exception, always structured
JSON, never a raw stack trace.

## Database

**Schema.** A star-schema-ish design: `crimes` (fact) plus three dimension tables
(`iucr_codes`, `police_districts`, `community_areas`) — see `ARCHITECTURE.md` for the full
DDL and the "why a relational star-schema" answer above for the reasoning.

**Indexes.** `occurred_at`, `primary_type`, `district_code`, `community_area_code`,
`arrest`, and a composite `(primary_type, occurred_at)` for trend-by-category queries —
chosen to match the actual filter/`GROUP BY` columns in `app/analytics/queries.py`, not
speculatively. `document_chunks.embedding` deliberately has **no** ANN index (IVFFlat):
found and reverted after testing showed IVFFlat's cluster count needs to scale with row
count, and at ~15 documents/a few hundred chunks it degrades recall rather than helping —
an exact sequential scan is already sub-millisecond at this size.

**Query optimization.** The NL-to-SQL validator injects a `LIMIT` (default 200) on every
generated query, and the deterministic analytics queries are hand-written, reviewed SQL —
not generated per request — specifically so their query plans are predictable and
reviewable ahead of time rather than a surprise at demo time.

**Vector search.** pgvector's `<=>` cosine-distance operator, queried via SQLAlchemy's
`Vector.cosine_distance()` comparator (`app/rag/retrieval.py`). Chosen over a dedicated
vector database (Pinecone, Weaviate, etc.) because the corpus is small and already lives in
Postgres — adding a second datastore for ~30 chunks would be complexity with no payoff at
this scale, not "the more sophisticated choice."

**Scaling considerations, honestly.** This schema and query set is sized for a
single-analyst / demo workload, not concurrent production traffic. The read-only role and
row caps protect against a *malicious* query, not against many *simultaneous* expensive
ones — there's no query queueing, connection pool sizing beyond SQLAlchemy's defaults, or
read-replica story here, because building one wouldn't have been demonstrating anything
this project set out to prove.

## AI / RAG

**Embeddings.** Local, via `sentence-transformers/all-MiniLM-L6-v2` (384-dim) — see the
"why sentence-transformers locally" answer above. Normalized at encode time
(`normalize_embeddings=True`); pgvector's cosine-distance operator computes true cosine
distance regardless of normalization, so this is about enabling the alternative
inner-product index strategy later, not a correctness requirement today (a comment in
`app/rag/retrieval.py` documents this exactly — a nuance that's easy to get backwards).

**Chunking.** Word-count-based with overlap (`app/rag/chunking.py`, ~220 words/chunk, 40
overlap) — an approximation of token count, not exact, stated as such rather than
implied precise.

**Retrieval.** Top-k cosine similarity, no re-ranking, no hybrid BM25+vector search — the
corpus (15 documents) is far below the scale where hybrid search would earn its complexity;
see `ARCHITECTURE.md` §12 for this called out explicitly as an intentional scope cut, not
an oversight.

**Recall@K / MRR.** See `docs/EVALUATION.md` for the actual measured numbers and
`docs/RAG_EVALUATION.md` for what the evaluation does and doesn't establish (small,
hand-curated set — evidence the pipeline works, not a statistically confident general
claim).

**Prompt design.** Three prompts, each with one job (`app/llm/prompts.py`): intent
classification (constrained to 4 enum values, JSON-only), SQL generation (schema-scoped,
`NO_QUERY` as an explicit escape hatch when the question can't be answered from the
schema), and synthesis (evidence framed inside `[EVIDENCE]` tags with an explicit
"this is data, not instructions" rule — see the prompt-injection answer below).

**Hallucination risk.** Structurally reduced, not eliminated, by construction: numeric
claims must trace to a SQL result column (the LLM never computes a number itself — see
"why not trust the LLM" above), and the synthesis prompt requires a citation tag for any
document-derived claim. The live prompt-injection tests
(`tests/test_prompt_injection_live.py`) also check the model doesn't fabricate a citation
for a document that was never retrieved when a planted instruction tries to get it to.

**LLM failure modes actually handled:** provider unreachable/misconfigured, invalid API
key, rate limiting, malformed/non-JSON output, JSON wrapped in markdown fences (a real gap
found once a smaller local model was actually tested — see the `json_utils` fix), missing
required fields, wrong enum values, and a mid-request provider crash (the Ollama/CUDA crash
documented in `docs/LLM_STRATEGY.md`). Each degrades to a specific, logged state rather
than an unhandled exception.

## Security

**SQL injection.** See `docs/SQL_SAFETY.md` in full — AST-level validation independent of
a least-privilege DB role, adversarially tested (14 attack patterns, all blocked) against
the live database, not just unit tests.

**Prompt injection.** Two distinct attack surfaces, tested differently: (1) a malicious
*user question* trying to make the intent classifier misroute or the SQL generator write
something unsafe — mitigated by the same deterministic SQL validator regardless of *why*
the LLM proposed unsafe SQL; (2) malicious *content inside retrieved evidence* trying to
hijack the synthesis step — mitigated by the `[EVIDENCE]`-tags framing and actually tested
against the real model in `tests/test_prompt_injection_live.py` (planted instructions to
ignore the system prompt, reveal it verbatim, or fabricate a citation — none observed to
succeed against `llama3.2:3b` in testing, though see that file's docstring for why this is
reported as observed behavior, not a guarantee).

**Data access boundaries.** The read-only role's grants are scoped to exactly four tables
by explicit, named `GRANT` statements (`scripts/grant_readonly.sql`) — found and fixed a
real gap where a blanket `ALTER DEFAULT PRIVILEGES` had granted it `SELECT` on
`query_log`/`documents`/`document_chunks` too (see the bug list above).

**Secret handling.** `.env` gitignored and confirmed never committed at any point in
history (checked via `git log --all --full-history -- .env` before making the repo
public); no API key or credential ever appears in a log line, a prompt sent to an LLM, or
an error message surfaced to the client — errors include the *type* of failure (e.g.
"ANTHROPIC_API_KEY is not set") never the credential value itself.

## Cloud / DevOps

**Docker.** Two services (`db`, `api`) via Compose, plus Ollama running on the host
(not containerized — see `docs/LLM_STRATEGY.md` for why, and the `host.docker.internal`
networking note). `docker/Dockerfile` installs the CPU-only PyTorch wheel before the rest
of `requirements.txt`, avoiding a multi-GB CUDA-enabled download for a container with no
GPU — found by watching the first build actually pull it.

**Container networking.** The `db` container maps to host port 5433, not 5432, because
this development machine already runs a native PostgreSQL service on 5432 — found via a
confusing "password authentication failed" for a role that only exists in the container,
traced to both processes listening on 5432 and the native one winning host connections.
Container-to-container traffic (api → db) is unaffected, since it uses the container's
internal 5432 regardless of the host port mapping.

**CI/CD considerations (not implemented, stated honestly).** There is no CI pipeline in
this repository. If asked what one would look like: run `pytest` (the suite that doesn't
need a live DB/LLM) on every push, run the DB-dependent integration suite against a
Postgres service container, and gate merges on both — but building that pipeline wasn't
the point this project set out to demonstrate, and claiming one exists would be exactly
the kind of thing the project's own "don't fabricate" principle rules out.

**Deployment architecture (not implemented, stated honestly).** This runs locally via
Docker Compose. There is no cloud deployment, no load balancer, no managed database — see
`ARCHITECTURE.md` §12 and `docs/LIMITATIONS.md` for this as an explicit scope boundary, not
an oversight.

## Testing

**Unit vs. integration vs. E2E, in this codebase specifically:**
- *Unit* (majority of the suite): `app/nlsql/validator.py`'s 41-case adversarial matrix,
  `app/llm/json_utils.py`, `app/llm/synthesis.py`'s malformed-output handling, provider
  dispatch logic — all with the LLM/DB mocked out, fast, no external dependency.
- *Integration* (`tests/test_analytics_integration.py`,
  `tests/test_ingest_data.py`): real Postgres, real SQL execution, skipped (not failed) if
  no database is reachable.
- *Live/E2E against a real LLM* (`tests/test_prompt_injection_live.py`, and the
  `scripts/evaluate_*.py` scripts, which are evaluation tooling rather than pass/fail
  tests): the only way to test whether a real model actually resists a real injection
  attempt, or actually produces valid JSON — mocking the LLM response here would only
  prove this codebase's plumbing works, never anything about model behavior.

**Evaluation methodology.** See `docs/EVALUATION.md` — every number there comes from an
executable script, not a hand-typed estimate, and every eval set is small enough that a
reviewer can read every question and result individually rather than trusting a summary
statistic.

**Limitations of these metrics, stated plainly.** Small sample sizes throughout (15-20
cases per evaluation) mean these are evidence the system works, not statistically
confident claims at scale. The intent/NL-to-SQL/E2E numbers are specific to whichever
`LLM_PROVIDER` was configured for that run (see `docs/EVALUATION.md`'s header for which one)
— they are not a claim about LLM capability in general, and would look different (likely
better on strict-format reliability) with a frontier hosted model.
