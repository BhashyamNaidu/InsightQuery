from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.llm.client import LlmError, complete
from app.llm.prompts import INTENT_SYSTEM_PROMPT
from app.schemas.investigation import Route

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    route: Route
    reasoning: str


def classify_intent(question: str) -> IntentResult:
    # Found via live testing during an LLM outage (no API key configured yet): this
    # call raising LlmError propagated all the way out of run_investigation before
    # a query_log entry was ever written, silently defeating this system's core
    # "every investigation is auditable" claim for the one failure mode most likely
    # to actually happen in production (a transient LLM API problem). Degrading to
    # hybrid here — the same fallback already used for unparseable output — keeps
    # the rest of the pipeline (and its logging) running instead of losing the
    # audit trail for the exact requests most worth auditing.
    try:
        response = complete(INTENT_SYSTEM_PROMPT, question, max_tokens=200)
    except LlmError as exc:
        logger.warning("Intent classification LLM call failed (%s); defaulting to hybrid.", exc)
        return IntentResult(
            route=Route.HYBRID,
            reasoning=f"Intent classifier LLM call failed; defaulting to hybrid. ({exc})",
        )

    try:
        data = json.loads(response.text)
        route = Route(data["route"])
        reasoning = data.get("reasoning", "")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Intent classification output unparseable (%s); defaulting to hybrid.", exc)
        route = Route.HYBRID
        reasoning = "Could not parse intent classifier output; defaulting to hybrid."
    return IntentResult(route=route, reasoning=reasoning)
