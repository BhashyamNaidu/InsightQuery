"""Best-effort extraction of a JSON object from raw LLM output.

app/nlsql/generator.py already had to strip markdown code fences from SQL output;
app/services/intent.py and app/llm/synthesis.py did a bare json.loads(response.text)
with no such handling. That's a real, predictable gap for smaller/local models
(the default LLM_PROVIDER is Ollama running a ~3B model — see
docs/LLM_STRATEGY.md) which are noticeably more likely than a frontier hosted
model to wrap JSON in ```json ... ``` fences or add a sentence of preamble before
it even when explicitly instructed to respond with only JSON.

This does not make JSON parsing bulletproof — it's a pragmatic best effort, not a
guarantee. If it still fails, callers must (and already do) treat that as a normal,
expected LLM failure mode to degrade from, not something this function should hide.
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def extract_json_object(text: str) -> str:
    """Returns a string more likely to be parseable by json.loads() than the raw
    LLM output: strips markdown code fences, and if the result still isn't a
    clean JSON object, falls back to slicing between the first '{' and the last
    '}' (handles a model adding a sentence of preamble/postamble around the JSON).
    Does not itself parse or validate — callers still call json.loads() and must
    still handle JSONDecodeError.
    """
    cleaned = _FENCE_RE.sub("", text).strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return cleaned[first_brace : last_brace + 1]

    return cleaned
