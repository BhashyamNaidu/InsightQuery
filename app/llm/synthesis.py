from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.llm.client import complete
from app.llm.json_utils import extract_json_object
from app.llm.prompts import SYNTHESIS_SYSTEM_PROMPT, build_synthesis_user_prompt
from app.schemas.investigation import Confidence, SynthesisOutput

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2


def synthesize(
    question: str,
    sql: str | None = None,
    sql_rows: list[dict] | None = None,
    evidence_chunks: list[dict] | None = None,
) -> SynthesisOutput:
    evidence_chunks = evidence_chunks or []
    user_prompt = build_synthesis_user_prompt(question, sql, sql_rows, evidence_chunks)

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        response = complete(SYNTHESIS_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
        try:
            data = json.loads(extract_json_object(response.text))
            return SynthesisOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning("Synthesis output failed validation (attempt %d/%d): %s", attempt, _MAX_ATTEMPTS, exc)

    return SynthesisOutput(
        answer="The system could not produce a validated, evidence-grounded answer for this question.",
        citations=[],
        confidence=Confidence.LOW,
        limitations=[f"LLM synthesis output failed schema validation after retry: {last_error}"],
    )
