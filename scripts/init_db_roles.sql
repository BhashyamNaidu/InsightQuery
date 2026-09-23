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

-- Table-level SELECT grants are (re-)applied by scripts/grant_readonly.sql
-- after migrations create the tables (grants on not-yet-existing tables are no-ops).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO insightquery_readonly;

REVOKE CREATE ON SCHEMA public FROM insightquery_readonly;
