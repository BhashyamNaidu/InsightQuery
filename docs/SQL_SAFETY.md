# SQL Safety: Design and Adversarial Test Matrix

## Why this is the highest-value part of the system

InsightQuery lets an LLM propose SQL against a real database. That is exactly the
pattern responsible for most "chat with your data" security incidents in the wild —
either the model is coerced (by a crafted question or, in more advanced attacks, by
poisoned data it's shown) into writing destructive or exfiltrating SQL, or a
well-intentioned model simply writes something too expensive or too broad. InsightQuery
never executes what the LLM writes directly. Everything below is the boundary between
"the LLM suggested this" and "this ran against the database."

## The pipeline

```
question --> LLM proposes SQL --> app.nlsql.validator.validate_sql()
                                         |
                              rejected? --+--> logged, returned to caller, nothing executes
                                         |
                                     accepted (possibly with LIMIT injected)
                                         |
                              app.nlsql.executor.execute_readonly()
                                         |
                        connects as the `insightquery_readonly` Postgres role
                        (SELECT-only grants on 4 tables, see scripts/init_db_roles.sql)
                        with a per-connection statement_timeout
```

Two independent layers have to fail for a write, a data exfiltration, or a
denial-of-service query to succeed: the validator (app-level, AST-based) and the
database role's grants (DB-level, enforced by Postgres itself regardless of any
application bug). Neither is treated as sufficient on its own.

## What the validator checks (`app/nlsql/validator.py`)

1. **Single statement, no stacking.** `sqlglot.parse()` must return exactly one
   statement. `SELECT 1; DROP TABLE crimes;` is two statements and is rejected outright.
2. **No comments.** `--` and `/*` are rejected unconditionally. Legitimate generated SQL
   here never needs a comment, and comments are a classic way to smuggle a stacked
   statement or hide a payload past a naive string check.
3. **Statement type allow-list.** Only `exp.Select`/`exp.Union` pass. `INSERT`, `UPDATE`,
   `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `MERGE`, and anything sqlglot
   can't classify (`exp.Command`, a common bucket for exotic/administrative syntax) are
   rejected by type, not by keyword-matching the SQL text.
4. **Table/schema allow-list.** Every `exp.Table` node in the parsed AST (including inside
   joins, subqueries, and CTE bodies) must resolve to one of `crimes`, `iucr_codes`,
   `police_districts`, `community_areas`. `information_schema`, `pg_catalog`, and
   `pg_toast` are explicitly blocked so a model can't enumerate schema metadata as a
   reconnaissance step. CTE names themselves (`WITH monthly AS (...)`) are recognized as
   virtual, in-scope tables — the SELECT that *defines* the CTE is still checked against
   the real allow-list.
5. **Column allow-list.** Every `exp.Column` reference must be a real column of one of the
   four allowed tables, or an alias the statement itself defines (so
   `COUNT(*) AS n ... ORDER BY n` isn't a false positive). This is coarse — it doesn't
   bind a column to a specific table via full semantic qualification — see *Known
   limitation* below.
6. **Function deny-list.** `pg_sleep`, `dblink*`, `pg_read_file`, `pg_read_binary_file`,
   `pg_ls_dir`, `set_config`, `current_setting`, `pg_terminate_backend`,
   `pg_cancel_backend`, `copy_from_program` — introspection, side-effect, and
   resource-exhaustion functions with no legitimate use in an analytics query.
7. **Row limit enforcement.** A `LIMIT` above the configured max (`SQL_ROW_LIMIT`,
   default 200) is rejected; a missing `LIMIT` gets one injected rather than executing
   unbounded.
8. **Locking clauses rejected.** `FOR UPDATE`/`FOR SHARE` have no place in a read-only
   analytics query and are rejected.

## Defense in depth beyond the validator

- **`insightquery_readonly` Postgres role** (`scripts/init_db_roles.sql`): `SELECT`-only
  grants on exactly the four allowed tables, no `CREATE` on the schema, no other grants at
  all. If the validator had a bug that let a `DELETE` through, the database itself would
  still refuse it — this is the actual backstop, not a formality.
- **Statement timeout** set per-connection (`SQL_STATEMENT_TIMEOUT_MS`, default 5s) so an
  accepted-but-expensive query (e.g. an unindexed cross join a human reviewer might have
  allowed through) can't hang the connection pool.
- **Every generated SQL string and its validation verdict is logged** to `query_log`
  *before* execution is attempted, so a rejected query — or a crash mid-execution — is
  still auditable.

## Known limitation (documented, not hidden)

The column check is table-agnostic: it confirms a referenced column name exists
*somewhere* in the allowed schema, not that it belongs to the specific table it's written
against. Fully resolving that requires semantic qualification via sqlglot's optimizer fed
a live schema catalog — meaningfully more implementation and maintenance surface for a
guarantee that adds little here, because none of the four allowed tables holds any
sensitive or privileged column; a cross-table column mix-up produces a Postgres error at
worst, not a security exposure. If a future version of this schema added a table with
sensitive columns, this would need to be revisited before adding it to the allow-list.

## Adversarial test matrix (`tests/test_sql_validator.py`, 35 tests)

| Category | Examples tested |
|---|---|
| Destructive statements | `DROP TABLE`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `CREATE`, `GRANT` |
| Injection / stacking | `SELECT ...; DROP TABLE ...;`, `--` and `/*` comment smuggling, tautologies (`1=1 OR 1=1`, confirmed harmless once scope-limited) |
| Scope escape | unknown tables, `information_schema`, `pg_catalog`, and — importantly — the app's *own* non-analytics tables (`query_log`, `documents`) are rejected exactly like an attacker-chosen table |
| Function abuse | `pg_sleep`, `dblink`, `pg_read_file`, `set_config` |
| Limit enforcement | over-limit rejected, under/at-limit accepted, missing limit auto-injected |
| Malformed input | empty string, whitespace, garbage text, `None` |
| Legitimate-but-tricky SQL | joins across allowed tables, CTEs, `GROUP BY`/`ORDER BY` on select-list aliases — these must pass, and two of them initially didn't (see git history) until the allow-list was taught to recognize CTE names and aliases as in-scope |

Every rejection returns a specific, logged reason string — never a silent no-op and never
a generic "invalid query," because both the caller and the audit log need to know *why*.
