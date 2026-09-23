from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.llm.client import complete
from app.llm.prompts import INTENT_SYSTEM_PROMPT
from app.schemas.investigation import Route

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    route: Route
    reasoning: str


def classify_intent(question: str) -> IntentResult:
    response = complete(INTENT_SYSTEM_PROMPT, question, max_tokens=200)
    try:
        data = json.loads(response.text)
        route = Route(data["route"])
        reasoning = data.get("reasoning", "")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Intent classification output unparseable (%s); defaulting to hybrid.", exc)
        route = Route.HYBRID
        reasoning = "Could not parse intent classifier output; defaulting to hybrid."
    return IntentResult(route=route, reasoning=reasoning)
