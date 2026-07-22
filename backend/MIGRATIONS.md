# Database Migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/). The
application no longer calls `Base.metadata.create_all()` at startup.

## Why

`create_all()` only creates **missing tables**. It never alters a table that
already exists, so it silently skips new columns, constraints, and enum types.

## Configuration

The database URL is **not** stored in `alembic.ini`. `alembic/env.py` reads it
from `app.config.settings`, i.e. the same `.env` (or `.env.test` when
`APP_ENV=test`) the backend uses. To target a different database for one
command, pass it explicitly:

```bash
alembic -x db_url="$SOME_DATABASE_URL" upgrade head
```

## Revisions

| Revision | Purpose |
|---|---|
| `0001_baseline` | The schema as `create_all()` had already built it on the deployed database, before the multi-select ballot work. |
| `0002_ballot_config` | Adds `elections.ballot_type` and `elections.max_selections`, plus the `ballot_type` enum type. |

The split exists so that both a fresh database and the already-deployed database
can reach the same final schema.

## Applying migrations

### Fresh database

```bash
cd backend
alembic upgrade head
```

Runs `0001` then `0002`.

### Existing database (the deployed Supabase project)

The tables in `0001` already exist there, so `0001` must be **stamped**, not
run — running it would fail on the existing objects.

```bash
cd backend

# 1. Confirm what is actually deployed. Read-only; safe to run against prod.
python -m scripts.verify_schema

# 2. Record the baseline as already applied (writes only to alembic_version).
alembic stamp 0001_baseline

# 3. Apply everything after the baseline.
alembic upgrade head

# 4. Confirm the result.
python -m scripts.verify_schema
```

`0002` is guarded by a column-existence check, so step 3 is safe even if
somebody had already added those columns by hand.

Take a Supabase backup before step 3.

## Adding a new migration

```bash
cd backend
alembic revision --autogenerate -m "short description"
```

Then **read the generated file before committing it**. Autogenerate is not
reliable for enum types, server defaults, or table/column renames — it tends to
emit a drop-and-recreate where an `ALTER` was intended. Fix those by hand.

Every model change needs a migration in the same pull request. The PostgreSQL
test `test_fresh_database_schema_matches_models_exactly` fails when a model and
the migrations drift apart.

## Verifying a database

```bash
python -m scripts.verify_schema                    # configured DATABASE_URL
python -m scripts.verify_schema --db-url "$URL"    # explicit target
```

Read-only. Exits non-zero on a mismatch, so it can gate a deployment. It checks
that every model table and column exists, that nullability matches, and that the
uniqueness constraints the application relies on are present — by column set
rather than constraint name, since several were auto-named by PostgreSQL.

## Running the PostgreSQL tests

The migration and constraint tests need a real PostgreSQL instance and are
skipped without one:

```bash
docker run --rm -d -p 55432:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=evoting_test \
  --name evoting-test-pg postgres:16

export TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:55432/evoting_test
export ALLOW_DESTRUCTIVE_DB_TESTS=true
pytest tests/test_migrations_postgres.py -v
```

The tests fail closed unless the URL uses PostgreSQL, targets localhost, names
the database exactly `evoting_test`, and `ALLOW_DESTRUCTIVE_DB_TESTS=true` is
set. The fixture drops and recreates the `public` schema before every test.
