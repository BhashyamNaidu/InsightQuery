-- Runs automatically on first container startup (docker-entrypoint-initdb.d).
-- Creates a dedicated, least-privilege role used ONLY to execute validated,
-- LLM-generated SQL. This role must never receive DML/DDL grants: the SQL
-- validator is defense-in-depth, this role is the backstop if it were ever bypassed.

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'insightquery_readonly') THEN
        CREATE ROLE insightquery_readonly LOGIN PASSWORD 'insightquery_readonly';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE insightquery TO insightquery_readonly;
GRANT USAGE ON SCHEMA public TO insightquery_readonly;

-- Deliberately NO `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES` here.
-- That was tried and reverted after live testing showed it does exactly what it
-- says: grants SELECT on every current *and future* table in the schema, which
-- silently included query_log (containing every generated SQL string this system
-- has ever logged, across all users' questions), documents, and document_chunks —
-- none of which validate_sql()'s table allow-list ever intended this role to read.
-- Table-level SELECT grants are applied explicitly, by name, in
-- scripts/grant_readonly.sql — run once after migrations create the tables — so the
-- DB-level grant boundary matches the four-table allow-list exactly, not "whatever
-- happens to exist in the schema."
REVOKE CREATE ON SCHEMA public FROM insightquery_readonly;
