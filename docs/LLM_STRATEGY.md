# LLM Provider Strategy

## The problem this solves

Earlier versions of this project hard-coded Anthropic as the only LLM backend, which meant
demonstrating the system — running it, evaluating it, letting someone else clone and try
it — required a paid API key. That's a real barrier for a portfolio project: a reviewer
shouldn't need to spend money to see whether the SQL safety validator actually blocks
`DROP TABLE`.

## What changed

LLM access is now behind a provider interface (`app/llm/providers/base.py`): a single
`LlmProvider.complete(system, user, max_tokens) -> LlmResponse` method. Every call site in
the app (`app/services/intent.py`, `app/nlsql/generator.py`, `app/llm/synthesis.py`) calls
`app.llm.client.complete()`, which is a thin dispatcher that reads `LLM_PROVIDER` from
config and delegates to the matching provider. No call site knows or cares which provider
is actually running.

```
LLM_PROVIDER=ollama       # default — free, local, no API key
LLM_PROVIDER=anthropic    # requires ANTHROPIC_API_KEY, paid, higher quality
LLM_PROVIDER=none         # LLM features disabled; SQL/RAG/analytics still work
```

## Why Ollama, specifically, as the default

The brief was "genuinely free," not "free under some vendor's current promotional terms."
Hosted-API free tiers exist and some are generous, but their limits and pricing are a
business decision by a third party that can change at any time — a project's default
configuration shouldn't rest on that. Local inference via [Ollama](https://ollama.com) has
no such dependency: it's free because it's your own CPU, not because of anyone's rate-limit
policy. That's what "the application must still work gracefully if no LLM is configured or
reachable" is protecting against too — see the graceful-degradation section below.

## Hardware fit (measured on the actual development machine)

| | |
|---|---|
| RAM | 15.84 GB |
| GPU | NVIDIA MX250 (2 GB VRAM — not viable for LLM inference), Intel UHD integrated |
| Inference mode | CPU-only |

A 2GB laptop GPU can't meaningfully accelerate even a small quantized LLM (context +
KV-cache overhead alone often exceeds that), so this runs on CPU. That rules out anything
requiring a real GPU (7B+ models at usable speed, most "local LLM" demos you see online)
and points toward small (~3B parameter), quantized models specifically chosen for
instruction-following rather than raw capability. Default: `llama3.2:3b`
(`ollama pull llama3.2:3b`, ~2GB on disk).

**Confirmed the hard way, not just estimated:** Ollama's automatic GPU detection tried to
use the MX250 anyway on its first real request and crashed the inference subprocess
outright (`CUDA error: shared object initialization failed`, exit code
`0xc0000409`). The app's existing graceful-degradation path handled it correctly — that
request's intent classification fell back to `hybrid` with the failure reason logged,
exactly as designed — but a crash-and-restart on every first request isn't something to
route around instead of fixing. Set `CUDA_VISIBLE_DEVICES=-1` before starting Ollama to
force CPU-only mode explicitly, which avoids the crash entirely (verified: two consecutive
successful requests afterward, no crash, ~1s warm inference for a short prompt). If
running Ollama as a persistent Windows service, set this at the User or System
environment-variable level so it's in effect before Ollama starts, not just in the shell
that happens to launch it once.

## Trade-off, stated plainly

CPU inference on a 3B model is slower and less reliable at strict-format output (JSON,
SQL) than a frontier hosted model. This is measured, not asserted — see
`docs/EVALUATION.md` for the actual intent-classification accuracy, NL-to-SQL success
rate, and per-stage latency numbers under `LLM_PROVIDER=ollama`, and how they compare to
`LLM_PROVIDER=anthropic` where both were run.

## Graceful degradation (see `app/services/investigation.py`)

Every LLM-dependent stage already degrades to an explicit, logged failure state instead of
crashing the request, regardless of *why* the LLM call failed (no provider configured,
Ollama not running, Anthropic key missing, network timeout — `app/llm/client.py` wraps all
of these as `LlmError`):

- `classify_intent()` → defaults to `hybrid` with the failure reason as its stated
  reasoning.
- SQL generation → the SQL stage returns a rejected `SqlExecutionResult` with a clear
  reason, never raises.
- Synthesis → `run_investigation()` returns `synthesis: null` rather than failing the
  whole request; the deterministic SQL/RAG results the request already produced are still
  returned.
- Deterministic analytics (`app/analytics/queries.py`) and RAG retrieval
  (`app/rag/retrieval.py`, local embeddings) don't call an LLM at all and are entirely
  unaffected by `LLM_PROVIDER=none` or an LLM outage.

## Configuration

See `.env.example` for the full variable list (`LLM_PROVIDER`, `ANTHROPIC_API_KEY`,
`ANTHROPIC_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`). Running
the containerized API against a host-installed Ollama requires
`OLLAMA_BASE_URL=http://host.docker.internal:11434` (Docker Desktop's DNS name for the
host machine) rather than `localhost`, since `localhost` inside a container refers to the
container itself.
