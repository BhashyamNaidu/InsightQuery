"""Pull raw data from the City of Chicago open data portal (Socrata API, no auth
required for this volume) into data/raw/ as-is, with no cleaning. Cleaning and
loading happens in ingest_data.py — kept separate so a flaky network doesn't force
re-cleaning, and so data/raw/ is a reproducible, inspectable snapshot of what the
source actually returned.

Usage:
    python scripts/fetch_data.py
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fetch_data")

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
BASE = "https://data.cityofchicago.org/resource"
PAGE_SIZE = 50_000
CRIME_YEAR = 2023


def _get(url: str, params: dict) -> list[dict]:
    with httpx.Client(timeout=60) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_crimes(year: int = CRIME_YEAR) -> list[dict]:
    """Paginate through a full calendar year of crime records."""
    url = f"{BASE}/ijzp-q8t2.json"
    all_rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "$where": f"year = {year}",
            "$order": "id",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        batch = _get(url, params)
        if not batch:
            break
        all_rows.extend(batch)
        logger.info("Fetched %d crime rows (running total %d)", len(batch), len(all_rows))
        offset += PAGE_SIZE
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(0.2)  # be a polite anonymous (unauthenticated) API consumer
    return all_rows


def fetch_iucr_codes() -> list[dict]:
    return _get(f"{BASE}/c7ck-438e.json", {"$limit": 5000})


def fetch_community_areas() -> list[dict]:
    return _get(
        f"{BASE}/igwz-8jzy.json",
        {"$select": "area_num_1,community", "$limit": 500},
    )


def fetch_police_districts() -> list[dict]:
    return _get(
        f"{BASE}/z8bn-74gv.json",
        {"$select": "district,district_name", "$limit": 500},
    )


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    datasets = {
        "crimes_2023.json": fetch_crimes,
        "iucr_codes.json": fetch_iucr_codes,
        "community_areas.json": fetch_community_areas,
        "police_districts.json": fetch_police_districts,
    }
    for filename, fetch_fn in datasets.items():
        logger.info("Fetching %s ...", filename)
        rows = fetch_fn()
        out_path = RAW_DIR / filename
        out_path.write_text(json.dumps(rows), encoding="utf-8")
        logger.info("Wrote %d rows to %s", len(rows), out_path)


if __name__ == "__main__":
    main()
