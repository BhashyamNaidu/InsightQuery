import pytest

from app.nlsql.validator import validate_sql


class TestSafeQueriesAccepted:
    def test_simple_select(self):
        result = validate_sql("SELECT * FROM crimes LIMIT 10")
        assert result.ok
        assert "LIMIT 10" in result.sql

    def test_aggregation_group_by(self):
        result = validate_sql(
            "SELECT primary_type, COUNT(*) AS n FROM crimes GROUP BY primary_type ORDER BY n DESC"
        )
        assert result.ok
        assert "LIMIT 200" in result.sql  # default limit injected

    def test_join_across_allowed_tables(self):
        result = validate_sql(
            "SELECT c.primary_type, d.name FROM crimes c "
            "JOIN police_districts d ON c.district_code = d.code LIMIT 50"
        )
        assert result.ok

    def test_cte_referencing_only_allowed_tables(self):
        result = validate_sql(
            "WITH monthly AS (SELECT date_trunc('month', occurred_at) AS m, COUNT(*) AS n "
            "FROM crimes GROUP BY m) SELECT * FROM monthly LIMIT 20"
        )
        assert result.ok

    def test_limit_at_exactly_max_is_allowed(self):
        result = validate_sql("SELECT * FROM crimes LIMIT 200", max_row_limit=200)
        assert result.ok

    def test_missing_limit_gets_default_injected(self):
        result = validate_sql("SELECT * FROM crimes")
        assert result.ok
        assert "LIMIT 200" in result.sql
        assert any("default LIMIT" in w for w in result.warnings)


class TestDestructiveStatementsRejected:
    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE crimes",
            "DELETE FROM crimes WHERE id = 1",
            "UPDATE crimes SET arrest = true",
            "INSERT INTO crimes (id) VALUES (1)",
            "TRUNCATE TABLE crimes",
            "ALTER TABLE crimes ADD COLUMN hacked TEXT",
            "CREATE TABLE evil (id INT)",
            "GRANT ALL ON crimes TO public",
        ],
    )
    def test_rejected(self, sql):
        result = validate_sql(sql)
        assert not result.ok
        assert result.sql is None


class TestInjectionAndStackingRejected:
    def test_statement_stacking(self):
        result = validate_sql("SELECT * FROM crimes; DROP TABLE crimes;")
        assert not result.ok

    def test_comment_based_smuggling(self):
        result = validate_sql("SELECT * FROM crimes WHERE 1=1 -- ' OR 1=1")
        assert not result.ok
        assert "comment" in result.reason.lower()

    def test_block_comment_smuggling(self):
        result = validate_sql("SELECT * FROM crimes /* sneaky */ WHERE id = 1")
        assert not result.ok

    def test_classic_or_1_equals_1_is_syntactically_valid_but_table_scoped(self):
        # Not itself dangerous once scoped to an allowed table with no side effects;
        # the point is it must not let a second statement or a disallowed table in.
        result = validate_sql("SELECT * FROM crimes WHERE 1=1 OR 1=1")
        assert result.ok


class TestScopeEnforcement:
    def test_unknown_table_rejected(self):
        result = validate_sql("SELECT * FROM users")
        assert not result.ok
        assert "not in the allowed table list" in result.reason

    def test_information_schema_rejected(self):
        result = validate_sql("SELECT * FROM information_schema.tables")
        assert not result.ok

    def test_pg_catalog_rejected(self):
        result = validate_sql("SELECT * FROM pg_catalog.pg_tables")
        assert not result.ok

    def test_query_log_table_not_accessible(self):
        # query_log exists in the DB but must never be reachable from generated SQL.
        result = validate_sql("SELECT * FROM query_log")
        assert not result.ok

    def test_document_tables_not_accessible(self):
        result = validate_sql("SELECT * FROM documents")
        assert not result.ok

    def test_disallowed_column_rejected(self):
        result = validate_sql("SELECT embedding FROM crimes")
        assert not result.ok
        assert "column" in result.reason.lower()


class TestFunctionAbuseRejected:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT pg_sleep(10)",
            "SELECT * FROM crimes WHERE pg_sleep(5) IS NULL",
            "SELECT dblink('host=evil', 'select 1')",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT set_config('statement_timeout', '0', false)",
        ],
    )
    def test_rejected(self, sql):
        result = validate_sql(sql)
        assert not result.ok


class TestLimitEnforcement:
    def test_excessive_limit_rejected(self):
        result = validate_sql("SELECT * FROM crimes LIMIT 999999")
        assert not result.ok
        assert "exceeds the maximum" in result.reason

    def test_custom_max_row_limit_respected(self):
        result = validate_sql("SELECT * FROM crimes LIMIT 500", max_row_limit=1000)
        assert result.ok


class TestMalformedInput:
    def test_empty_string(self):
        result = validate_sql("")
        assert not result.ok

    def test_whitespace_only(self):
        result = validate_sql("   \n\t  ")
        assert not result.ok

    def test_garbage_input(self):
        result = validate_sql("this is not sql at all !!!")
        assert not result.ok

    def test_none_like_input_handled(self):
        result = validate_sql(None)  # type: ignore[arg-type]
        assert not result.ok
