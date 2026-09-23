# RAG Evaluation

## Corpus

15 original reference documents (`data/documents/`), ~300-500 words each, covering crime
classification methodology, data-quality caveats, geography/policy context, and
interpretation pitfalls. Written for this project from public factual information about
Chicago's open-data practices and general criminal-justice terminology — not scraped from
any copyrighted source — specifically so the corpus is small enough to be read end-to-end
by a reviewer in a few minutes and its evaluation is fully inspectable.

## Method

`scripts/evaluate_rag.py` runs a hand-written evaluation set of 15 question/expected-
document pairs (`data/rag_eval_set.json` — one targeted question per document) through
the real retrieval path (`app/rag/retrieval.py`: sentence-transformers embedding +
pgvector cosine similarity) and reports:

- **Recall@k** — the fraction of questions for which the expected document appears
  anywhere in the top-k retrieved chunks' source documents.
- **MRR (Mean Reciprocal Rank)** — the average of `1/rank` of the expected document across
  all questions (0 if not retrieved in the top-k at all), which penalizes a correct
  document showing up at rank 5 more than one showing up at rank 1, unlike recall@k alone.

This is deliberately a small, hand-curated set rather than a large synthetic one: with 15
source documents, 15 targeted questions give a legible, per-question-inspectable result —
every miss can be read and understood individually (see the per-question output the
script prints), rather than summarized away into a single aggregate number that could
hide a systematic weak spot.

## Running it

```bash
python scripts/ingest_documents.py   # one-time: chunk, embed, load the corpus
python scripts/evaluate_rag.py --top-k 5
```

The full report (including every question's retrieved titles and rank) is written to
`docs/rag_eval_results.json` for inspection.

## Honest limitations of this evaluation

- **15 questions is small.** It is enough to catch a broken pipeline or a badly chunked
  document, not enough to make a statistically confident claim about recall in general.
  A production system would need a substantially larger, likely LLM-assisted-then-
  human-reviewed evaluation set.
- **One expected document per question.** Several documents overlap in subject matter
  (e.g. the arrest/domestic-flag definitions document and the domestic-violence-resources
  document both touch the `domestic` flag) — a retrieval that surfaces a *reasonable*
  related document instead of the single labeled "expected" one is scored as a miss even
  though it might be a genuinely useful result. This is a known scoring simplification,
  not a claim that anything outside the exact expected title is wrong.
- **No adversarial/out-of-scope questions in this set.** The evaluation set only tests
  "can it find the right document for an on-topic question," not "does it correctly
  retrieve nothing (or say so) for a question the corpus can't answer." That behavior is
  covered separately by the synthesis prompt's "insufficient evidence" instruction and by
  the corresponding tests on the synthesis schema, not by the retrieval-quality
  measurement here.
- **Chunking approximation.** Chunks are word-count-based (not exact token counts, see
  `app/rag/chunking.py`), which can occasionally split a sentence across a chunk boundary
  and slightly change which chunk a passage's embedding best matches.

Results from the last run are checked into `docs/rag_eval_results.json` — read that file
for actual numbers rather than assuming a specific score here, since evaluation is
re-run whenever the corpus or embedding model changes.
