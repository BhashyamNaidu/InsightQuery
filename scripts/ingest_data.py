"""Clean, validate, and load the raw JSON pulled by fetch_data.py into Postgres.

Idempotent: safe to re-run (upserts dimension rows, and crime rows are inserted
with `ON CONFLICT (id) DO NOTHING` keyed on the source dataset's stable id, so a
re-run after a partial failure doesn't duplicate rows).

Usage:
    python scripts/ingest_data.py
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import SessionLocal
from app.models import CommunityArea, Crime, IucrCode, PoliceDistrict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_data")

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def _load_raw(filename: str) -> list[dict[str, Any]]:
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run scripts/fetch_data.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_iucr_codes(raw: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    dropped = 0
    for row in raw:
        code = (row.get("iucr") or "").strip()
        if not code:
            dropped += 1
            continue
        seen[code] = {
            "code": code,
            "primary_type": (row.get("primary_description") or "UNKNOWN").strip().upper(),
            "secondary_desc": (row.get("secondary_description") or "UNKNOWN").strip().upper(),
            "index_crime": (row.get("index_code") or "").strip().upper() == "I",
        }
    logger.info("iucr_codes: %d clean, %d dropped (missing code)", len(seen), dropped)
    return list(seen.values())


def clean_community_areas(raw: list[dict]) -> list[dict]:
    seen: dict[int, dict] = {}
    dropped = 0
    for row in raw:
        code = _to_int(row.get("area_num_1"))
        name = (row.get("community") or "").strip()
        if code is None or code == 0 or not name:
            dropped += 1
            continue
        seen[code] = {"code": code, "name": name}
    logger.info("community_areas: %d clean, %d dropped", len(seen), dropped)
    return list(seen.values())


def clean_police_districts(raw: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    dropped = 0
    for row in raw:
        code = (row.get("district") or "").strip()
        name = (row.get("district_name") or "").strip()
        # Normalize to the same zero-padded 3-digit code used in the crimes fact table
        # (e.g. "6" -> "006"); "Headquarters" isn't a patrol district, so it's excluded.
        if not code.isdigit() or not name:
            dropped += 1
            continue
        seen[code.zfill(3)] = {"code": code.zfill(3), "name": name}
    logger.info("police_districts: %d clean, %d dropped", len(seen), dropped)
    return list(seen.values())


def clean_crimes(
    raw: list[dict],
    valid_iucr: set[str],
    valid_district: set[str],
    valid_community: set[int],
) -> tuple[list[dict], dict[str, int]]:
    stats = {
        "total": len(raw),
        "dropped_no_id": 0,
        "dropped_no_date": 0,
        "dropped_dup": 0,
        "nulled_bad_district": 0,
        "nulled_bad_community_area": 0,
        "clean": 0,
    }
    seen_ids: set[int] = set()
    clean_rows: list[dict] = []

    for row in raw:
        record_id = _to_int(row.get("id"))
        if record_id is None:
            stats["dropped_no_id"] += 1
            continue
        if record_id in seen_ids:
            stats["dropped_dup"] += 1
            continue

        date_str = row.get("date")
        try:
            occurred_at = datetime.fromisoformat(date_str.replace(".000", "")) if date_str else None
        except (ValueError, AttributeError):
            occurred_at = None
        if occurred_at is None:
            stats["dropped_no_date"] += 1
            continue

        iucr_code = (row.get("iucr") or "").strip() or None
        if iucr_code not in valid_iucr:
            iucr_code = None  # keep the crime row; just don't dangle an FK to a bad code

        # Discovered on real data: a small fraction of rows (~0.15%) reference a
        # district code (e.g. "031", "061") that isn't a real CPD patrol district in
        # the reference lookup, or a community_area code with no matching row. Same
        # treatment as iucr_code above — null the FK rather than dropping the row or
        # crashing the whole ingestion on a foreign key violation.
        district_code = (row.get("district") or "").strip().zfill(3) or None
        if district_code not in valid_district:
            stats["nulled_bad_district"] += 1
            district_code = None

        community_area_code = _to_int(row.get("community_area")) or None
        if community_area_code not in valid_community:
            stats["nulled_bad_community_area"] += 1
            community_area_code = None

        seen_ids.add(record_id)
        clean_rows.append(
            {
                "id": record_id,
                "case_number": row.get("case_number") or f"UNKNOWN-{record_id}",
                "occurred_at": occurred_at,
                "block": row.get("block"),
                "iucr_code": iucr_code,
                "primary_type": (row.get("primary_type") or "UNKNOWN").strip().upper(),
                "description": row.get("description"),
                "location_description": row.get("location_description"),
                "arrest": _to_bool(row.get("arrest")),
                "domestic": _to_bool(row.get("domestic")),
                "beat": row.get("beat"),
                "district_code": district_code,
                "ward": _to_int(row.get("ward")),
                "community_area_code": community_area_code,
                "fbi_code": row.get("fbi_code"),
                "latitude": _to_float(row.get("latitude")),
                "longitude": _to_float(row.get("longitude")),
                "year": _to_int(row.get("year")) or occurred_at.year,
            }
        )
    stats["clean"] = len(clean_rows)
    return clean_rows, stats


def _upsert_dimension(session, model, rows: list[dict], pk_col: str) -> None:
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update_cols = {c: getattr(stmt.excluded, c) for c in rows[0] if c != pk_col}
    stmt = stmt.on_conflict_do_update(index_elements=[pk_col], set_=update_cols)
    session.execute(stmt)


def _insert_crimes(session, rows: list[dict]) -> int:
    if not rows:
        return 0
    # cursor.rowcount is unreliable for a multi-row INSERT ... ON CONFLICT DO NOTHING
    # via psycopg (it reports -1, meaning "unknown," for this statement shape) — and
    # `result.rowcount or 0` doesn't catch that, because -1 is truthy in Python, so it
    # was silently summing -1 per chunk into a nonsensical negative total. Counting
    # actual rows before/after is the only accurate way to report how many were added.
    before = session.execute(text("SELECT COUNT(*) FROM crimes")).scalar_one()

    # Postgres (via psycopg) caps a single query at 65535 bound parameters. Each
    # crime row binds 18 columns, so 5000 rows/chunk (90000 params) overflowed that
    # limit and failed at execution time on the very first real ingestion run.
    # 1000 rows * 18 cols = 18000 params, comfortably under the limit.
    chunk_size = 1000
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        stmt = pg_insert(Crime).values(chunk).on_conflict_do_nothing(index_elements=["id"])
        session.execute(stmt)

    session.flush()
    after = session.execute(text("SELECT COUNT(*) FROM crimes")).scalar_one()
    return after - before


def _fk_orphan_check(session, community_valid: set[int], district_valid: set[str]) -> None:
    """Data-quality gate: fail loudly if a meaningful fraction of rows reference a
    community area / district code that isn't in our (cleaned) dimension tables,
    rather than silently shipping a schema where joins quietly drop rows."""
    # NOT IN :valid needs an *expanding* bindparam — a plain named bindparam sends
    # the tuple to the DBAPI as a single opaque parameter (`NOT IN ?`), which either
    # errors or silently matches nothing, rather than expanding to `NOT IN (?, ?, ?)`.
    total = session.execute(text("SELECT COUNT(*) FROM crimes")).scalar_one()
    orphan_community = session.execute(
        text(
            "SELECT COUNT(*) FROM crimes WHERE community_area_code IS NOT NULL "
            "AND community_area_code NOT IN :valid"
        ).bindparams(bindparam("valid", value=tuple(community_valid) or (-1,), expanding=True))
    ).scalar_one()
    orphan_district = session.execute(
        text(
            "SELECT COUNT(*) FROM crimes WHERE district_code IS NOT NULL "
            "AND district_code NOT IN :valid"
        ).bindparams(bindparam("valid", value=tuple(district_valid) or ("__none__",), expanding=True))
    ).scalar_one()
    logger.info(
        "Data-quality check: %d/%d rows with orphan community_area_code, "
        "%d/%d rows with orphan district_code",
        orphan_community,
        total,
        orphan_district,
        total,
    )
    orphan_ratio = (orphan_community + orphan_district) / max(total, 1)
    if orphan_ratio > 0.05:
        raise RuntimeError(
            f"Data quality gate failed: {orphan_ratio:.1%} of rows have an FK code "
            "not present in dimension tables (>5% threshold). Investigate before proceeding."
        )


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    iucr_rows = clean_iucr_codes(_load_raw("iucr_codes.json"))
    community_rows = clean_community_areas(_load_raw("community_areas.json"))
    district_rows = clean_police_districts(_load_raw("police_districts.json"))

    valid_iucr = {r["code"] for r in iucr_rows}
    valid_district = {r["code"] for r in district_rows}
    valid_community = {r["code"] for r in community_rows}
    crime_rows, crime_stats = clean_crimes(
        _load_raw("crimes_2023.json"), valid_iucr, valid_district, valid_community
    )
    logger.info("crimes cleaning stats: %s", crime_stats)

    if crime_stats["clean"] / max(crime_stats["total"], 1) < 0.95:
        raise RuntimeError(
            f"Data quality gate failed: only {crime_stats['clean']}/{crime_stats['total']} "
            "crime rows survived cleaning (<95% threshold). Investigate before loading."
        )

    with SessionLocal() as session:
        _upsert_dimension(session, IucrCode, iucr_rows, "code")
        _upsert_dimension(session, CommunityArea, community_rows, "code")
        _upsert_dimension(session, PoliceDistrict, district_rows, "code")
        session.commit()
        logger.info("Loaded dimension tables.")

        inserted = _insert_crimes(session, crime_rows)
        session.commit()
        logger.info("Inserted %d new crime rows (of %d cleaned).", inserted, len(crime_rows))

        _fk_orphan_check(
            session,
            {r["code"] for r in community_rows},
            {r["code"] for r in district_rows},
        )

    logger.info("Ingestion complete.")


if __name__ == "__main__":
    main()
