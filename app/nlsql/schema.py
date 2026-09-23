"""The single source of truth for what the NL-to-SQL pipeline is allowed to touch.

Used by both the validator (to enforce the allow-list) and the SQL-generation prompt
(so the LLM is only ever shown the tables/columns it's permitted to query).
"""

ALLOWED_TABLES: dict[str, set[str]] = {
    "crimes": {
        "id",
        "case_number",
        "occurred_at",
        "block",
        "iucr_code",
        "primary_type",
        "description",
        "location_description",
        "arrest",
        "domestic",
        "beat",
        "district_code",
        "ward",
        "community_area_code",
        "fbi_code",
        "latitude",
        "longitude",
        "year",
    },
    "iucr_codes": {"code", "primary_type", "secondary_desc", "index_crime"},
    "police_districts": {"code", "name"},
    "community_areas": {"code", "name"},
}

ALL_ALLOWED_COLUMNS: set[str] = {col for cols in ALLOWED_TABLES.values() for col in cols}

SCHEMA_DESCRIPTION = """\
Table crimes (one row per reported incident, Chicago, calendar year 2023):
  id INTEGER, case_number TEXT, occurred_at TIMESTAMP, block TEXT,
  iucr_code TEXT (FK -> iucr_codes.code), primary_type TEXT, description TEXT,
  location_description TEXT, arrest BOOLEAN, domestic BOOLEAN, beat TEXT,
  district_code TEXT (FK -> police_districts.code), ward INTEGER,
  community_area_code INTEGER (FK -> community_areas.code), fbi_code TEXT,
  latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, year INTEGER

Table iucr_codes (crime classification reference):
  code TEXT PK, primary_type TEXT, secondary_desc TEXT, index_crime BOOLEAN

Table police_districts (dimension):
  code TEXT PK, name TEXT

Table community_areas (dimension):
  code INTEGER PK, name TEXT

Only SELECT queries against these four tables/columns are permitted. No other tables
exist as far as you are concerned.
"""
