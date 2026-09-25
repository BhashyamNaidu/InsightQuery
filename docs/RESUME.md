# Resume-Ready Project Description

## Short version (one line)

**InsightQuery** — an auditable AI investigation platform over real Chicago crime data
(263,841 records): validated NL-to-SQL, pgvector RAG, and evidence-grounded LLM synthesis
where every claim traces back to a SQL result or a cited document, never an LLM guess.
Runs on a free local LLM by default (Ollama) — no API key required to use it.

## Resume bullet points (pick 2-4 depending on role — every number here is measured, not
estimated; see `docs/EVALUATION.md` for the underlying reports)

**Backend / Software Engineering:**
> Designed and built a FastAPI investigation platform translating natural-language
> questions into validated, read-only SQL over PostgreSQL, using an AST-level validator
> (sqlglot) and a least-privilege database role as independent, defense-in-depth safety
> layers; 100% of malicious/injection SQL attempts blocked in a 20-case evaluation
> (`docs/nl2sql_eval_results.json`), covered by 141 automated tests including live
> adversarial tests against a real LLM.

**Data Engineering:**
> Built a reproducible ingestion pipeline pulling 263,841 real records from a public API,
> with automated data-quality gates (fails the run if >5% of rows fail cleaning or
> reference invalid foreign keys) rather than silently loading dirty data into a
> normalized, indexed relational schema.

**AI/ML / RAG:**
> Implemented a retrieval-augmented generation pipeline (pgvector cosine similarity over
> locally embedded document chunks) measuring recall@5 = 1.0 and MRR = 0.956 against a
> hand-evaluated question set, with a configurable LLM provider abstraction (local Ollama
> or hosted Anthropic) and an evidence-only synthesis prompt that requires per-claim
> citations — found and fixed a real prompt-injection vulnerability where a planted
> instruction in retrieved document content got the LLM to fabricate a citation, closing it
> deterministically (cross-checking every citation against actually-retrieved documents)
> rather than by re-wording the prompt.

**Technology Consulting / Data Analytics:**
> Delivered a decision-support tool distinguishing deterministic fact (SQL/retrieval
> results) from LLM-generated interpretation at every step of its output, with a dashboard
> showing the full investigation trace (intent, generated SQL, per-stage latency, evidence,
> trust checklist) and documented data-quality caveats surfaced directly to the end user
> rather than hidden behind a confident-sounding answer.

**Cloud / Infrastructure:**
> Containerized a multi-service application (FastAPI + Postgres/pgvector) with Docker
> Compose, a documented least-privilege database role model, and a CPU-only-inference
> configuration avoiding unnecessary multi-gigabyte GPU dependencies in the container image.

**Security:**
> Ran adversarial testing against a live deployment and a real LLM (not simulated),
> finding and fixing four distinct real vulnerabilities/bugs — including a database
> access-boundary gap granting broader read access than intended, and a non-deterministic
> LLM prompt-injection exploit that fabricated a source citation — each closed with a
> deterministic code fix and a regression test, not a documentation note.

## What makes this different from a typical "chat with your data" portfolio project

Most similar projects let an LLM write and execute SQL directly, or answer from general
knowledge dressed up with a document search. InsightQuery is built around the opposite
premise: the LLM is never the source of truth. Every number in a final answer traces to a
SQL query a deterministic validator approved and a least-privilege database role executed;
every non-numeric factual claim traces to a retrieved, cited document chunk — and that
citation is itself cross-checked against what was actually retrieved, not just trusted.
This is the one sentence worth saying in an interview if only one is allowed.

## What to say if asked "what would you improve with more time"

Answer directly from [docs/LIMITATIONS.md](LIMITATIONS.md) — it's a real, prioritized list
written during development, not reverse-engineered for the interview.
