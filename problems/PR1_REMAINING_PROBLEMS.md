# PR1 Remaining Problems

**Status:** Deferred by team decision after PR1 review

**Scope:** Migration baseline and live Supabase verification

**Resolved separately:** The destructive PostgreSQL-test guard is implemented in PR1.

These items remain unresolved. They should not be described as completed in the
report or PR notes until the corresponding code or documentation changes land.

## P1 — `seed_demo.py` still bypasses Alembic

`backend/scripts/seed_demo.py` still calls `Base.metadata.create_all(bind=engine)`.
On a fresh database this can create the current tables without creating an
`alembic_version` record. A later `alembic upgrade head` may then try to create
tables that already exist and fail.

### Required correction

- Remove the production/demo `create_all()` call.
- Require `alembic upgrade head` before seeding.
- Make the seed script fail clearly when the schema is absent or behind head.

## P1 — Root setup instructions omit the migration step

The root `README.md` currently instructs developers to start Uvicorn immediately
after installing dependencies. Since application startup no longer calls
`create_all()`, a fresh installation can start with no application tables.

### Required correction

Add `alembic upgrade head` before the documented Uvicorn command and link to
`backend/MIGRATIONS.md` for existing-database procedures.

## P2 — Live database roles, grants, indexes, and constraints are not recorded

The revised remediation plan asks for the deployed table structure, indexes,
constraints, and database roles to be recorded. The current verifier checks
selected properties but does not produce or preserve that inventory, and it
does not inspect role grants.

### Required correction

- Capture a sanitized schema inventory with no credentials.
- Record the application role's effective table privileges.
- Record relevant Supabase roles/RLS assumptions and the security owner who
  verified them.
- Store the verification date and Alembic revision.

## P2 — `verify_schema.py` overstates what it proves

The script reports that the database "matches the models", but it currently
checks only:

- required model tables and columns exist;
- database-nullable columns are not stricter in the model;
- selected uniqueness guarantees exist.

It does not fully compare column types, defaults, foreign keys, enum labels,
unexpected columns, reverse nullability differences, indexes, roles, grants,
or RLS policies.

### Required correction

Either expand the verifier to cover those properties or change its success
message to the narrower and accurate statement: "required schema checks passed".
Continue using `alembic check` as the stronger model-drift check.

## Migration immutability constraint

Supabase is already at `0002_ballot_config`. Do not edit migration `0001` or
`0002`. Any subsequent schema correction must be a new forward migration,
starting with `0003`.
