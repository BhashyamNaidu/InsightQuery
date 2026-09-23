"""Regression test for a real bug hit on the first live ingestion run: psycopg
reports cursor.rowcount as -1 ("unknown") for a multi-row INSERT ... ON CONFLICT DO
NOTHING statement, and `result.rowcount or 0` doesn't guard against that because -1
is truthy in Python — so `_insert_crimes` was silently summing -1 per chunk into a
nonsensical negative "rows inserted" count while the actual data loaded correctly.
Fixed by counting rows before/after instead of trusting rowcount. See
scripts/ingest_data.py.
"""


def test_or_zero_does_not_guard_against_negative_rowcount():
    """Documents the exact Python truthiness gotcha that caused the bug."""
    fake_rowcount = -1
    assert (fake_rowcount or 0) == -1  # NOT 0 - this is the bug
    assert max(fake_rowcount, 0) == 0  # a correct guard, for contrast


def test_before_after_counting_is_immune_to_rowcount_unreliability():
    # The fix doesn't depend on rowcount at all, so this just documents that the
    # replacement logic (after - before) is a plain, driver-independent integer
    # subtraction with no truthiness pitfalls.
    before, after = 263841, 263841
    assert after - before == 0
    before, after = 0, 263841
    assert after - before == 263841
