# InsightQuery

AI-powered data investigation and analytics platform. Ask a natural-language question about
Chicago crime data; get back a deterministic SQL result and/or retrieved document evidence,
synthesized into a grounded answer with citations — never an LLM guess.

Full design rationale: [ARCHITECTURE.md](ARCHITECTURE.md).

> Status: under active development. This README is filled in progressively as each phase
> lands — see commit history for what's actually implemented right now.

## Why this exists

Most "chat with your data" demos let an LLM write and run arbitrary SQL, or let it answer
from "vibes" instead of evidence. InsightQuery treats the LLM as a narrator, not a source of
truth: structured questions are answered by validated, read-only SQL against a real Postgres
schema; document questions are answered by retrieval against an embedded corpus in pgvector;
the LLM's only job is to explain what the deterministic systems already found, citing its
sources, and to say "insufficient evidence" when that's the honest answer.

## Quickstart

```bash
docker compose up -d
```

(Setup details, API docs, and a full demo walkthrough are added as each phase completes —
see `docs/` for the growing documentation set.)

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full schema/API/security design, and the
`docs/` directory for SQL safety, RAG evaluation, and security writeups as they land.
