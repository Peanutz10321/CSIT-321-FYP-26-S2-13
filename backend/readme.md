# Backend — FastAPI e-voting API

This is a navigation page. The full setup and onboarding guide lives in the
[root readme](../readme.md); it is not duplicated here.

## Documentation

| Document | Contents |
|---|---|
| [Root readme](../readme.md) | Prerequisites, cloning, database creation, configuration, running locally, testing, troubleshooting |
| [`MIGRATIONS.md`](MIGRATIONS.md) | Alembic workflow, revision history and current head, Supabase stamp/upgrade procedure, schema verification, guarded demo seeding, ballot commitments, audit chain, audit-table role provisioning |
| [`DEPENDENCIES.md`](DEPENDENCIES.md) | Dependency file roles, regenerating pins, auditing and its one documented suppression, runtime configuration reference |

## Quick reference

All commands run from this `backend/` directory, with the virtual environment
active and `.env` filled in. See
[Running locally](../readme.md#running-locally) for the full sequence — including
creating the database, which must exist first.

```bash
pip install -r requirements.txt                          # production set
pip install -r requirements.txt -r requirements-dev.txt  # adds pytest and audit tooling

alembic upgrade head                 # apply migrations (current head: 0005_user_group)
python -m scripts.verify_schema      # read-only schema check
uvicorn app.main:app --reload        # http://127.0.0.1:8000
```

### Tests

```bash
pytest tests -q          # safe SQLite suite; *_postgres.py files skip
```

The PostgreSQL-gated suite needs a disposable `evoting_test` container and
`ALLOW_DESTRUCTIVE_DB_TESTS=true`. It drops and recreates the `public` schema, so
read [Backend — PostgreSQL-gated suite](../readme.md#backend--postgresql-gated-suite)
before running it.

### Layout

```
alembic/versions/     # 0001 baseline → 0005 user group
app/
  core/               # time helpers (naive SGT)
  models/             # SQLAlchemy models
  routes/             # auth, users, admin users, elections, votes, results
  schemas/            # Pydantic request/response models
  security/           # jwt, password, role deps, homomorphic, keystore,
                      #   ballot_commitment, audit, audit_hash_v1
  services/           # user_service, election_lock
  config.py           # Settings + startup validation
  database.py
  main.py             # app, CORS, router registration
scripts/              # verify_schema, verify_audit_permissions (read-only),
                      #   seed_demo (DESTRUCTIVE), guards
tests/                # pytest suite (*_postgres.py require PostgreSQL)
```

> `scripts/seed_demo.py` truncates every application table. Point it only at a
> disposable local or demo database — see
> [First System Admin account](../readme.md#first-system-admin-account).
