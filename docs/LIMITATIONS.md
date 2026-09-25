# Known Limitations & Future Improvements

Written deliberately as a real list, not a token gesture — an interviewer will ask "what
would you change with more time," and every item here is something actually considered
and consciously deferred, not discovered after the fact.

## Known limitations (present in the current implementation)

1. **NL-to-SQL column allow-list is table-agnostic**, not fully schema-qualified (see
   `docs/SQL_SAFETY.md`). Low risk today because none of the four allowed tables has a
   sensitive column, but it's a real simplification, not an oversight to gloss over.
2. **RAG evaluation set is small (15 questions, one per document).** Measured
   recall@5 = 1.0, MRR = 0.956 against the live system (see `docs/RAG_EVALUATION.md`) —
   a genuinely good result, but on a set small enough that it's evidence the pipeline
   works correctly, not a statistically confident general recall estimate.
3. **Single calendar year of data (2023).** Chosen deliberately for a fast, reviewable
   ingestion within scope — but it means true multi-year trend analysis isn't possible,
   and "this year vs. last year" questions can't be answered from this dataset as loaded.
4. **No authentication/authorization.** Fine for a portfolio/demo deployment with no real
   user data; would be a hard requirement before any production use with real accounts.
5. **Chunking is word-count-based, not exact-token-based** (see `app/rag/chunking.py`) —
   a reasonable approximation for English prose, not a precise tokenizer-driven split.
6. **Intent classification is a single LLM call with no human-reviewable middle ground**
   between "sql," "rag," and "hybrid" — a genuinely ambiguous question gets one classifier
   guess (defaulting to "hybrid" on any parse failure) rather than, say, asking the user
   to disambiguate.
7. **No caching layer.** Every question re-embeds (for RAG) and re-calls the LLM (for
   intent, possibly SQL generation, and synthesis) even if asked before. Fine at demo
   scale; would matter under real load or cost pressure.
8. **Synthesis retries once on malformed JSON, then gives up explicitly** rather than
   attempting more sophisticated repair (e.g. asking the model to fix its own JSON). This
   is a deliberate simplicity choice — a rare failure mode surfaced honestly beats an
   overengineered self-repair loop for a system this size.
9. **First RAG retrieval in a fresh process pays a one-time embedding-model load cost**
   (~30-45 seconds observed, loading `sentence-transformers/all-MiniLM-L6-v2` into
   memory) — noticeable on the very first `/investigate` or `/rag/retrieve` call after
   the API process starts, negligible on every call after. Not addressed with a
   startup-time warmup call, which would be the straightforward fix.
10. **This machine's local dev setup needed a non-default Postgres port (5433, not 5432)**
    because a native PostgreSQL install already occupied 5432 — documented in
    `docker-compose.yml` and `.env.example`, not a system limitation, but worth knowing
    if `docker compose up` is ever run on a fresh machine that also has a local Postgres.
11. **The default local LLM (`llama3.2:3b`) has real, measured accuracy limits** — see
    `docs/EVALUATION.md` for the actual numbers: 75% intent-classification accuracy, and
    only 66.7% of validated SQL actually executed successfully (the rest had genuine
    semantic/type errors — `SUM()` on a boolean column, a `VARCHAR`/integer comparison —
    that the safety validator correctly let through because they aren't safety violations,
    just wrong SQL). `LLM_PROVIDER=anthropic` would very likely score higher on both; this
    is the explicit cost/quality trade-off `docs/LLM_STRATEGY.md` describes, not hidden.
12. **CPU-only local inference is slow**: ~50s average end-to-end investigation latency
    (measured, `docs/EVALUATION.md`), dominated by the synthesis call. Acceptable for a
    demo, not for anything latency-sensitive — `LLM_PROVIDER=anthropic` would be
    meaningfully faster at the cost of a paid API key.
13. **LLM output is non-deterministic, including its susceptibility to prompt injection.**
    A planted-instruction attack against synthesis (fabricating a citation) failed in one
    test run and succeeded in another, same code, same model — the fix
    (`app/llm/synthesis.py`'s citation cross-check) closes the *specific* vector this found,
    but doesn't imply every possible injection vector has been found or is closed by
    construction the way SQL safety is. This is the honest state of the art for
    LLM-output security today: verify and constrain what you can deterministically, and
    keep testing adversarially rather than trusting a prompt instruction.

## Explicitly out of scope (see `ARCHITECTURE.md` §12 for the full list and rationale)

Multi-agent orchestration, RBAC, Kubernetes, hybrid (BM25+vector) search, and any cloud
infrastructure beyond what's needed to run the demo. These aren't "future work" — they're
deliberately not the right complexity for what this system needs to prove.

## Future improvements, roughly in order of value if this continued past one week

1. **Schema-qualified column validation** using sqlglot's optimizer with a live catalog,
   closing the one documented gap in the SQL safety model — the highest-value fix if the
   schema ever grew to include a table with sensitive columns.
2. **A larger, partially LLM-assisted RAG evaluation set** (50-100 questions), still
   human-reviewed before being trusted, to get a recall/MRR number worth citing with
   confidence rather than treating as illustrative.
3. **Multi-year ingestion** with the reporting-lag-aware trimming described in
   `data/documents/13_data_refresh_cadence.md` actually implemented in the analytics
   layer (e.g. flag or exclude the most recent N days of any query result), not just
   documented as a caveat for a human reader.
4. **Basic API-key auth and per-key rate limiting** — the minimum needed before this could
   sit behind a real public URL rather than a local/demo deployment.
5. **A small result cache** (e.g. hash of validated SQL, or of the retrieval query) to cut
   both latency and LLM cost on repeated questions.
6. **Extend the citation-verification pattern to numeric claims.** Citations are now
   cross-checked against actually-retrieved documents (`app/llm/synthesis.py`, added after
   a real exploit was found — see `docs/SECURITY.md`); a numeric claim in the answer text
   (e.g. "theft rose 12%") isn't currently cross-checked against the actual SQL result rows
   the same way, because verifying a number embedded in free text is a harder parsing
   problem than checking a citation string against a known set of titles. Worth doing if
   this continued — it's the same principle, just harder to implement well.
