# Resume-Ready Project Description

## Short version (one line)

**InsightQuery** — an auditable AI investigation platform over real Chicago crime data
(260K+ records): validated NL-to-SQL, pgvector RAG, and evidence-grounded LLM synthesis
where every claim traces back to a SQL result or a cited document, never an LLM guess.

## Resume bullet points (pick 2-4 depending on role)

**Backend / Software Engineering:**
> Designed and built a FastAPI investigation platform translating natural-language
> questions into validated, read-only SQL over PostgreSQL, using an AST-level validator
> (sqlglot) and a least-privilege database role as independent, defense-in-depth safety
> layers against LLM-generated queries; covered with 35+ adversarial security tests.

**Data Engineering:**
> Built a reproducible ingestion pipeline pulling 260K+ real records from a public API,
> with automated data-quality gates (fails the run if >5% of rows fail cleaning or
> reference invalid foreign keys) rather than silently loading dirty data into a
> normalized, indexed relational schema.

**AI/ML / RAG:**
> Implemented a retrieval-augmented generation pipeline (pgvector cosine similarity over
> locally embedded document chunks) with a hand-evaluated retrieval-quality report
> (recall@k, MRR) and an evidence-only LLM synthesis prompt that requires per-claim
> citations and explicitly refuses to answer beyond its supplied evidence.

**Technology Consulting / Data Analytics:**
> Delivered a decision-support tool distinguishing deterministic fact (SQL/retrieval
> results) from LLM-generated interpretation at every step of its output, with documented
> data-quality caveats and methodological pitfalls (e.g. year-over-year comparison
> traps) surfaced directly to the end user rather than hidden behind a confident-sounding
> answer.

**Cloud / Infrastructure:**
> Containerized a multi-service application (FastAPI + Postgres/pgvector) with Docker
> Compose, environment-based configuration, and a documented least-privilege database
> role model separating the application's own writes from LLM-generated query execution.

## What makes this different from a typical "chat with your data" portfolio project

Most similar projects let an LLM write and execute SQL directly, or answer from general
knowledge dressed up with a document search. InsightQuery is built around the opposite
premise: the LLM is never the source of truth. Every number in a final answer traces to a
SQL query a deterministic validator approved and a least-privilege database role executed;
every non-numeric factual claim traces to a retrieved, cited document chunk. This is the
one sentence worth saying in an interview if only one is allowed.

## What to say if asked "what would you improve with more time"

Answer directly from [docs/LIMITATIONS.md](LIMITATIONS.md) — it's a real, prioritized list
written during development, not reverse-engineered for the interview.
