# InsightQuery

AI-powered data investigation and analytics platform. Ask a natural-language question about
Chicago crime data; get back a deterministic SQL result and/or retrieved document evidence,
synthesized into a grounded answer with citations — never an LLM guess.

![Architecture](docs/architecture.svg)

Full design rationale: [ARCHITECTURE.md](ARCHITECTURE.md). LLM provider strategy (and why it
runs on a free local model by default): [docs/LLM_STRATEGY.md](docs/LLM_STRATEGY.md).

## Why this exists

Most "chat with your data" demos let an LLM write and run arbitrary SQL, or let it answer
from "vibes" instead of evidence. InsightQuery treats the LLM as a narrator, not a source of
truth: structured questions are answered by validated, read-only SQL against a real Postgres
schema (see [docs/SQL_SAFETY.md](docs/SQL_SAFETY.md)); document questions are answered by
retrieval against an embedded corpus in pgvector; the LLM's only job is to explain what the
deterministic systems already found, citing its sources, and to say "insufficient evidence"
when that's the honest answer.

## Key capabilities

- **Safe NL-to-SQL**: an LLM proposes SQL, an independent AST-level validator
  (`app/nlsql/validator.py`) decides whether it ever runs — backed by a database role with
  `SELECT`-only grants on exactly four tables as a second, independent layer.
- **RAG over a curated corpus**: 15 reference documents, chunked and embedded locally
  (no API cost), retrieved via pgvector cosine similarity.
- **Evidence-grounded synthesis**: the final LLM call receives only the SQL rows and
  retrieved chunks already found — never asked to invent a number or a source — and its
  output is schema-validated before being trusted.
- **Configurable LLM provider**: `LLM_PROVIDER=ollama` (default — free, local, no API key)
  or `anthropic` (paid, requires a key). Every LLM-dependent stage degrades gracefully
  (logged, auditable) if the provider is unreachable or misconfigured — see
  [docs/LLM_STRATEGY.md](docs/LLM_STRATEGY.md).
- **A dashboard** (`/`, `/history`, `/metrics`) showing the full investigation trace —
  intent, generated SQL, validation verdict, chart, evidence, per-stage timing, and a
  trust checklist — not just a chat bubble.
- **Real evaluation**, not claims: `python scripts/evaluate.py` measures intent
  classification accuracy, NL-to-SQL safety/success rates, RAG recall@k/MRR, and
  end-to-end latency against the live system. See [docs/EVALUATION.md](docs/EVALUATION.md)
  for the actual current numbers.

## Setup

**Prerequisites:** Docker Desktop (with WSL2 backend on Windows), Python 3.11+, and either
[Ollama](https://ollama.com) (free, local — the default) or an
[Anthropic API key](https://console.anthropic.com/) (paid, optional).

```bash
# 1. Clone and configure
cp .env.example .env
# Default LLM_PROVIDER=ollama needs Ollama installed and running, with the model pulled:
ollama pull llama3.2:3b
# If Ollama detects a GPU it can't actually use well, force CPU-only mode first (see
# docs/LLM_STRATEGY.md for why this matters — it prevented a real crash during testing):
#   set CUDA_VISIBLE_DEVICES=-1   (Windows)  /  export CUDA_VISIBLE_DEVICES=-1  (Linux/Mac)
# To use Anthropic instead: set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env.

# Note: the db container maps to host port 5433, not 5432, in case this machine already
# runs a native Postgres on 5432 (see the comment in docker-compose.yml) — .env.example
# already points at 5433, no change needed unless you edit the port mapping yourself.

# 2. Start Postgres + pgvector
docker compose up -d db

# 3. Python environment
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash; use .venv\Scripts\Activate.ps1 for PowerShell
pip install -r requirements.txt

# 4. Create schema and apply the least-privilege read-only role's grants
alembic upgrade head
docker exec -i insightquery-db psql -U insightquery -d insightquery < scripts/grant_readonly.sql

# 5. Load data (one-time; pulls live from the Chicago open data portal).
# PYTHONPATH=. is required so these scripts can import the `app` package.
PYTHONPATH=. python scripts/fetch_data.py
PYTHONPATH=. python scripts/ingest_data.py
PYTHONPATH=. python scripts/ingest_documents.py

# 6. Run the API + dashboard
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
# Dashboard at http://localhost:8000/  ·  API docs at http://localhost:8000/docs
```

Or run the whole stack in Docker: `docker compose up -d` (after steps 4-5, which need to
run once against the containerized DB — see `docker-compose.yml`; Ollama itself runs on the
host, not in a container, and the API reaches it via `host.docker.internal`).

**Stopping:** `docker compose down` (add `-v` to also drop the database volume).

### Verified

The full stack (`db` + `api` containers, both LLM providers, the dashboard) has been run
end-to-end against a real Docker Desktop (WSL2 backend) deployment: 263,841 real 2023
Chicago crime records loaded, 15 reference documents chunked/embedded/loaded, every
dashboard page rendering correctly (including the graceful-degradation UI when the LLM is
unavailable), the `insightquery_readonly` role confirmed to `SELECT` successfully on the
four analytics tables while denied `INSERT`/`DROP`/`DELETE` and denied `SELECT` on
`query_log`/`documents`/`document_chunks`, adversarial SQL injection testing (14 attack
patterns) blocked entirely by the validator, and a real local LLM (`llama3.2:3b` via
Ollama) generating, validating, and executing genuine SQL end-to-end. See
[docs/SQL_SAFETY.md](docs/SQL_SAFETY.md), [docs/SECURITY.md](docs/SECURITY.md), and
[docs/EVALUATION.md](docs/EVALUATION.md) for full results, including the real bugs this
testing found and fixed.

### Running tests

```bash
pytest -q
```

130+ tests cover the SQL-safety adversarial matrix, chunking, the API contract, LLM-outage
resilience, malformed-LLM-output handling, and analytics-query syntax — all runnable
without a live database or LLM. A smaller set of integration tests (real Postgres) and live
adversarial tests (a real LLM call — `tests/test_prompt_injection_live.py`) skip
automatically, rather than fail, if the corresponding dependency isn't reachable.

### Running evaluations

```bash
python scripts/evaluate.py
```

Runs RAG retrieval, intent classification, NL-to-SQL, and end-to-end latency evaluations
against the live system and writes `docs/evaluation_results.json` plus per-evaluation
detail reports. The dashboard's `/metrics` page reads these same files. See
[docs/EVALUATION.md](docs/EVALUATION.md) for the current measured numbers and what they do
and don't establish.

## Demo walkthrough

Open `/` and ask something like *"How did theft change month to month in 2023, and is
there a seasonal explanation?"*, or via the API directly against `POST /investigate`:

```
Question
  -> intent: "hybrid" (needs both a number and context)
  -> SQL generated + validated + executed (Postgres, read-only role)      <- source of truth
  -> documents retrieved (pgvector cosine search)                         <- source of truth
  -> LLM synthesis, given ONLY the SQL rows + retrieved chunks above
  -> Answer, with every number traceable to the SQL and every claim cited
```

The dashboard renders the generated SQL (syntax-highlighted, with its validation verdict),
an auto-selected chart built from the actual result rows, the retrieved evidence with
similarity scores, a per-stage timing trace, and a trust checklist reflecting the request's
actual state — not a hardcoded "safe" badge. `/history` lists every past investigation
(the `query_log` audit trail); `/metrics` shows the real evaluation numbers above.

## Project layout

```
app/
  api/        JSON API routes
  web/        dashboard HTML routes (Jinja2)
  templates/  dashboard page templates
  static/     dashboard CSS/JS (vanilla JS + Chart.js via CDN, no build step)
  analytics/  hand-written deterministic SQL (trends, comparisons, anomalies)
  core/       config, logging
  db/         SQLAlchemy engine/session
  llm/        provider-agnostic LLM client (app/llm/providers/: anthropic, ollama)
  models/     SQLAlchemy models
  nlsql/      NL-to-SQL generation, AST validator, read-only executor
  rag/        chunking, embeddings, pgvector retrieval
  schemas/    Pydantic request/response models
  services/   intent classification, investigation orchestration
data/
  documents/  15 curated RAG reference documents + manifest
  eval/       intent + NL-to-SQL evaluation question sets
  raw/        fetched-but-uncleaned source snapshots (gitignored)
  processed/  reserved for cleaned intermediates (gitignored)
scripts/      fetch/ingest/evaluate CLIs, DB role setup SQL
docs/         architecture, SQL safety, security, evaluation, LLM strategy, limitations
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full schema/API/security design, and `docs/`
for SQL safety, evaluation, LLM strategy, security, and known-limitations writeups.
