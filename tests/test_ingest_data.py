"""Regression test for a real bug: SQLAlchemy's text() requires an *expanding*
bindparam for `NOT IN :name` — a plain named bindparam sends the tuple to the DBAPI
as a single opaque parameter instead of expanding it to `NOT IN (?, ?, ?)`, which
raises (or on some drivers silently matches nothing) at execution time. This is
exercised by scripts/ingest_data.py's data-quality gate. See that module's
_fk_orphan_check for the fix.
"""
from __future__ import annotations

import pytest
from sqlalchemy import bindparam, create_engine, text


def _make_table(conn):
    conn.exec_driver_sql("CREATE TABLE crimes (community_area_code INTEGER)")
    conn.exec_driver_sql("INSERT INTO crimes VALUES (1), (2), (3), (99)")


def test_plain_named_bindparam_fails_for_not_in():
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        _make_table(conn)
        stmt = text(
            "SELECT COUNT(*) FROM crimes WHERE community_area_code NOT IN :valid"
        ).bindparams(valid=(1, 2, 3))
        with pytest.raises(Exception):
            conn.execute(stmt)


def test_expanding_bindparam_correctly_counts_orphans():
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        _make_table(conn)
        stmt = text(
            "SELECT COUNT(*) FROM crimes WHERE community_area_code NOT IN :valid"
        ).bindparams(bindparam("valid", value=(1, 2, 3), expanding=True))
        assert conn.execute(stmt).scalar_one() == 1  # only the "99" row is an orphan


def test_expanding_bindparam_handles_empty_valid_set_via_placeholder():
    # ingest_data.py substitutes a placeholder (-1,) when the valid set is empty,
    # rather than passing an empty tuple (which is itself a separate SQL edge case
    # some backends reject for IN/NOT IN).
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        _make_table(conn)
        stmt = text(
            "SELECT COUNT(*) FROM crimes WHERE community_area_code NOT IN :valid"
        ).bindparams(bindparam("valid", value=(-1,), expanding=True))
        assert conn.execute(stmt).scalar_one() == 4  # nothing matches -1, all rows are "orphans"
