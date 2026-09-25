from app.llm.json_utils import extract_json_object


def test_clean_json_passed_through_unchanged():
    assert extract_json_object('{"route": "sql"}') == '{"route": "sql"}'


def test_strips_json_fenced_code_block():
    text = '```json\n{"route": "sql"}\n```'
    assert extract_json_object(text) == '{"route": "sql"}'


def test_strips_bare_fenced_code_block():
    text = '```\n{"route": "sql"}\n```'
    assert extract_json_object(text) == '{"route": "sql"}'


def test_strips_preamble_and_postamble_prose():
    text = 'Here is the JSON response:\n{"route": "sql"}\nLet me know if you need anything else!'
    assert extract_json_object(text) == '{"route": "sql"}'


def test_handles_whitespace_padding():
    text = '   \n  {"route": "sql"}  \n  '
    assert extract_json_object(text) == '{"route": "sql"}'


def test_no_json_object_returns_cleaned_text_unchanged_for_caller_to_fail_on():
    text = "I cannot answer that."
    assert extract_json_object(text) == "I cannot answer that."


def test_nested_braces_in_json_content_handled_via_outermost_braces():
    text = 'prose before {"answer": "the count is {5}", "confidence": "high"} prose after'
    result = extract_json_object(text)
    assert result.startswith("{") and result.endswith("}")
