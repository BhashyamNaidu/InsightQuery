"""A hybrid answer written without its database half must not pass for a full answer.

Observed live (llama3.2:3b): the SQL branch failed, synthesis was given only documents, and the
model still answered the database part from general knowledge ("robbery has the highest arrest
rate"), with confidence "high", though nothing retrieved supported it. Prompt wording asking
the model not to is a request, not a boundary, so the guarantees tested here are enforced in
code and hold even when the (mocked) model misbehaves.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import pytest

from app.llm import synthesis
from app.llm.prompts import build_synthesis_user_prompt
from app.schemas.investigation import Confidence, EvidenceChunk, Route, SynthesisOutput
from app.services import investigation
from tests.test_sql_branch_outcomes import CHUNK, _Harness

FABRICATED = "Robbery has the highest arrest rate in Chicago."


def _misbehaving_synthesize(harness):
    """The model ignores the notice: asserts an unsupported claim with high confidence."""
    def fake(**kwargs):
        harness.synth_calls.append(kwargs)
        return SynthesisOutput(answer=FABRICATED, citations=[], confidence=Confidence.HIGH, limitations=["model caveat"])
    return fake


def _hybrid(monkeypatch, generated_sql, executed_rows=None):
    h = _Harness(monkeypatch, Route.HYBRID, generated_sql=generated_sql, executed_rows=executed_rows)

    def no_repair(*args, **kwargs):  # keep the test hermetic: a repair attempt must never reach a real LLM
        raise RuntimeError("repair unavailable")

    monkeypatch.setattr("app.nlsql.pipeline.repair_sql", no_repair)
    monkeypatch.setattr(investigation, "_run_rag_stage", lambda q: [CHUNK])
    monkeypatch.setattr(investigation, "synthesize", _misbehaving_synthesize(h))
    return h


@pytest.mark.parametrize("bad_sql,fragment", [
    ("DELETE FROM crimes", "blocked by the SQL safety validator"),
    ("SELECT COUNT(*) FROM crimes", "failed when run against the database"),  # made to fail below
    (None, "no SQL query could be generated"),
])
def test_missing_sql_half_is_disclosed_in_the_answer_itself_and_confidence_is_capped(monkeypatch, bad_sql, fragment):
    rows = RuntimeError("boom") if bad_sql and bad_sql.startswith("SELECT") else None
    if rows:
        from sqlalchemy.exc import ProgrammingError
        rows = ProgrammingError("stmt", {}, Exception("missing FROM-clause entry"))
    _hybrid(monkeypatch, bad_sql, executed_rows=rows)

    response = investigation.run_investigation("Which crime type has the highest arrest rate, and how should I read it?")

    answer = response.synthesis.answer
    # the disclosure comes FIRST, before whatever the model wrote
    assert answer.startswith("The database part of this question could not be answered")
    assert fragment in answer.split(". What follows")[0]
    assert "contains no database figures" in answer
    assert answer.index("database part") < answer.index(FABRICATED)
    # the model said HIGH; the system does not trust that for a half-answered question
    assert response.synthesis.confidence == Confidence.LOW
    assert any("no result" in lim for lim in response.synthesis.limitations)
    assert "model caveat" in response.synthesis.limitations


def test_model_is_told_the_database_part_is_unavailable_and_given_no_sql_evidence(monkeypatch):
    h = _hybrid(monkeypatch, "DELETE FROM crimes")
    investigation.run_investigation("Count thefts and explain them")
    call = h.synth_calls[0]
    assert call["sql"] is None and call["sql_rows"] is None
    assert "blocked by the SQL safety validator" in call["sql_unavailable"]


def test_successful_hybrid_is_not_qualified_or_capped(monkeypatch):
    h = _Harness(monkeypatch, Route.HYBRID, generated_sql="SELECT COUNT(*) AS n FROM crimes", executed_rows=[{"n": 5}])
    monkeypatch.setattr(investigation, "_run_rag_stage", lambda q: [CHUNK])

    response = investigation.run_investigation("Count crimes and explain")

    assert h.synth_calls[0]["sql_unavailable"] is None
    assert response.synthesis.answer == "narrated"  # no lead-in
    assert response.synthesis.confidence == Confidence.MEDIUM  # whatever the model said, untouched
    assert not any("no result" in lim for lim in response.synthesis.limitations)


# --- the prompt the model actually receives -------------------------------------------

def _chunk_dicts():
    return [CHUNK.model_dump()]


def test_prompt_contains_a_system_notice_and_no_sql_evidence_when_the_sql_half_is_missing():
    p = build_synthesis_user_prompt("q", None, None, _chunk_dicts(), "the query failed when run against the database")
    assert "[SYSTEM NOTICE]" in p and "could not be answered" in p
    assert "the query failed when run against the database" in p
    assert "Do NOT state or imply any figure" in p
    assert "SQL result rows" not in p and "SQL executed" not in p
    # an instruction, not data: it must sit outside every [EVIDENCE] block
    notice_at = p.index("[SYSTEM NOTICE]")
    assert all(not (m <= notice_at <= p.index("[/EVIDENCE]", m)) for m in _evidence_starts(p))


def _evidence_starts(p):
    i, out = 0, []
    while (i := p.find("[EVIDENCE]", i)) != -1:
        out.append(i)
        i += 1
    return out


def test_prompt_has_no_notice_normally():
    p = build_synthesis_user_prompt("q", "SELECT 1", [{"n": 1}], _chunk_dicts())
    assert "[SYSTEM NOTICE]" not in p
    assert "SQL result rows" in p


def test_synthesize_forwards_the_notice_to_the_model(monkeypatch):
    seen = {}

    class R:
        text = '{"answer": "a", "citations": [], "confidence": "low", "limitations": []}'
        model, provider, input_tokens, output_tokens = "m", "p", 1, 1

    def fake_complete(system, user, **kw):
        seen["system"], seen["user"] = system, user
        return R()

    monkeypatch.setattr(synthesis, "complete", fake_complete)
    synthesis.synthesize("q", evidence_chunks=_chunk_dicts(), sql_unavailable="no SQL query could be generated")
    assert "[SYSTEM NOTICE]" in seen["user"] and "no SQL query could be generated" in seen["user"]
    assert "[SYSTEM NOTICE]" in seen["system"]  # rule 6 tells the model how to treat it
