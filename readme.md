# Homomorphic E-Voting System

An e-voting prototype built as a Final Year Project (CSIT-321-FYP-26-S2-13).

Voters cast ballots through a React frontend. A FastAPI backend encrypts each ballot
with the [Paillier cryptosystem](https://en.wikipedia.org/wiki/Paillier_cryptosystem)
and tallies elections **homomorphically** — per-candidate totals are computed by
summing ciphertexts, so only the aggregate is ever decrypted, never an individual
ballot.

---

## Implemented capabilities


### System administrator

| Capability | Endpoint |
|---|---|
| Authenticate | `POST /auth/login` |
| List, search and filter users (by username, email, external ID, role, status) | `GET /admin/users` |
| Inspect a single user | `GET /admin/users/{user_id}` |
| Suspend / unsuspend an account | `PATCH /admin/users/{user_id}/suspend`, `/unsuspend` |
| Set an account status (`active`, `inactive`, `suspended`) | `PATCH /admin/users/{user_id}/status` |

### Election organizer

| Capability | Endpoint |
|---|---|
| Self-register and authenticate | `POST /auth/register`, `POST /auth/login` |
| Create an active election (candidates + eligible voters required) | `POST /elections/` |
| Save an incomplete draft | `POST /elections/draft` |
| List own drafts | `GET /elections/drafts` |
| Update a draft (title, description, dates, candidates, ballot configuration) | `PUT /elections/{id}` |
| Delete a draft | `DELETE /elections/{id}` |
| Activate a draft (generates the keypair) | `PATCH /elections/{id}/activate` |
| Add an eligible voter (draft status only) | `POST /elections/{id}/voters` |
| List eligible voters | `GET /elections/{id}/voters` |
| Extend the deadline of an active election (and optionally rename it) | `PATCH /elections/{id}/extend-deadline` |
| Close an election and publish the tally | `POST /elections/{id}/close` |
| View own elections and results | `GET /elections/...`, `GET /results/elections/{id}` |

Organizers are restricted to elections they created. Ballots may be configured as
**single-choice** or **multi-select** with a `max_selections` limit; the limit cannot
exceed the candidate count once the list is final.

### Voter

| Capability | Endpoint |
|---|---|
| Self-register and authenticate | `POST /auth/register`, `POST /auth/login` |
| View active elections they are eligible for | `GET /elections/active` |
| Cast exactly one encrypted ballot, or abstain | `POST /votes/` |
| View own vote history (searchable, date-filterable) | `GET /votes/history` |
| Retrieve a receipt | `GET /votes/{vote_id}` |
| Verify a ballot against its commitment | `GET /votes/{vote_id}/verify` |
| View results of completed elections they were enrolled in | `GET /results/elections/{id}` |

Abstention is expressed as an empty selection (`candidate_ids: []`) and still
produces a genuinely encrypted all-zero ballot, so an abstention is
indistinguishable from a selection in storage.

### Registration policy

| Role | Public self-registration |
|---|---|
| Voter | Allowed |
| Election organizer | Allowed |
| System administrator | **Forbidden** — rejected with `403`; provisioned out of band |

---

## Security model

Each item below corresponds to a mechanism in the committed code.

| Area | Implementation |
|---|---|
| **Password storage** | bcrypt via passlib. Plaintext passwords are never stored or logged. Minimum 8 characters, enforced by the request schema. |
| **Authentication** | JWT bearer tokens, HS256. The algorithm is typed as a literal, so the app refuses to start with an RS\*/ES\* algorithm — this closes the algorithm-confusion class and keeps the unpatched `ecdsa` advisory unreachable. |
| **Authorization** | Role and status are re-read **from the database on every request**, not trusted from the token claims. Separate dependencies gate the administrator, organizer and voter roles. |
| **Suspension** | Rejected at login *and* on every authenticated request, so an already-issued token stops working the moment an account is suspended. |
| **Ballot encryption** | Paillier (2048-bit) on the backend. Each ballot is a multi-hot vector — `E(1)` per selection, `E(0)` for every other candidate — with fresh randomisation, so stored ciphertexts cannot be matched against attacker-computed encryptions. |
| **Tallying** | Ciphertexts are summed homomorphically per candidate; only the aggregate is decrypted. Individual ballots are never decrypted. |
| **Key storage** | The Paillier private key is Fernet-encrypted under `KEYSTORE_MASTER_SECRET` and stored in a separate `election_keys` table — never on the election row. It is loaded only at tally time. |
| **Vote/close concurrency** | Voting takes a shared row lock (`FOR SHARE`); closing takes an exclusive one (`FOR UPDATE`). A vote therefore either commits before the tally or is rejected afterwards, so a valid receipt always corresponds to a counted ballot. Two concurrent closes tally exactly once. |
| **Database constraints** | Uniqueness on `ballots.election_voter_id` (one ballot per enrolment), `ballots.receipt_code`, `ballots.ballot_commitment`, `users.external_id` / `username` / `email`, and `(election_id, voter_id)` on enrolments. Duplicate voting is prevented by the database, not only by an application check. |
| **Ballot commitments** | HMAC-SHA256 over a canonical serialisation of the ballot id, election id, receipt code, **complete ciphertext**, a digest of the ballot configuration and candidate set, and the submission time — keyed with a dedicated `RECEIPT_SIGNING_SECRET`. Returned on every receipt. Comparison is constant-time and fails closed on malformed stored values. |
| **Audit log** | Append-only and hash-chained: each row stores its sequence number, the previous entry's hash, and a SHA-256 over its own canonical JSON. Appends lock a singleton head row, so concurrent writers cannot fork the chain. Audit rows commit atomically with the action they describe. `details` fields are restricted to an allowlist, and voter selections are never recorded. |
| **Audit table privileges** | The runtime role must be a **dedicated non-owner role** that can `INSERT`/`SELECT` audit rows but not `UPDATE`, `DELETE` or `TRUNCATE` them. `scripts/verify_audit_permissions.py` checks *effective* privileges via `has_table_privilege`, catching inherited and `PUBLIC` grants. |
| **Destructive-operation guards** | The demo seed and the PostgreSQL test suite both fail closed: the seed needs four independent conditions (arming flag, host allowlist, database allowlist, `--reset`), all empty by default; destructive tests hardcode localhost + a database named exactly `evoting_test` and require `ALLOW_DESTRUCTIVE_DB_TESTS=true`. |
| **Dependency supply chain** | Production and dev dependencies are fully pinned via `pip-compile`, with a committed `package-lock.json` on the frontend. CI audits both. See [`backend/DEPENDENCIES.md`](backend/DEPENDENCIES.md). |
| **CORS** | Validated at startup. Unset means *no* cross-origin access rather than an implicit wildcard; a wildcard cannot be combined with credentials; and `ENVIRONMENT=production` additionally requires at least one origin, forbids `*`, and requires HTTPS on every entry. An unrecognised `ENVIRONMENT` value is rejected rather than silently treated as development. |
| **Frontend API URL** | Validated by the same function at runtime and at build time. A production build **aborts** if `VITE_API_BASE_URL` is missing, non-HTTPS, or malformed, rather than shipping a bundle that points at localhost. |

---

## Architecture and technology

```
Browser (React 19 / Vite)
    │  HTTPS, JSON, JWT bearer token
    │  plaintext selection leaves the browser
    ▼
FastAPI backend
    │  • authenticate, re-read role/status from DB
    │  • check eligibility and ballot configuration
    │  • ENCRYPT the ballot here (Paillier, per-election public key)
    │  • compute the HMAC ballot commitment
    │  • append a hash-chained audit entry
    ▼
PostgreSQL  (Supabase-compatible)
       ciphertexts, commitments, receipts, audit chain,
       Fernet-wrapped election private keys

Tally (on close): ciphertexts are summed homomorphically, the private key
is loaded from the keystore, and ONLY the per-candidate aggregate is
decrypted and cached in candidate_results.
```

| Layer | Technology |
|---|---|
| Frontend | React 19, React Router 7, Tailwind CSS 3, Vite 8 |
| Backend | FastAPI 0.139, Uvicorn 0.51, Pydantic 2 / pydantic-settings |
| ORM & migrations | SQLAlchemy 2.0, Alembic 1.18 |
| Database | PostgreSQL (Supabase-compatible), `psycopg2-binary` |
| Cryptography | `phe` 1.5 (Paillier), `cryptography` 49 (Fernet), `python-jose` (JWT), `passlib` + `bcrypt` |
| Backend tests | pytest 9, httpx |
| Frontend tests | Vitest 4, React Testing Library, jsdom |
| CI | GitHub Actions |

Exact pins live in `backend/requirements.txt` and `frontend/package-lock.json`.

---

## Project structure

```
backend/
  alembic/
    versions/            # 0001 baseline → 0004 audit chain
  app/
    core/                # time helpers (naive SGT)
    models/              # SQLAlchemy models
    routes/              # auth, users, admin users, admin stats,
                         #   elections, votes, results
    schemas/             # Pydantic request/response models
    security/            # jwt, password, security (role deps), homomorphic,
                         #   keystore, ballot_commitment, audit, audit_hash_v1
    services/            # user_service, election_lock
    config.py            # Settings + startup validation
    database.py
    main.py              # app, CORS, router registration
  scripts/
    verify_schema.py             # read-only schema check
    verify_audit_permissions.py  # read-only privilege check
    seed_demo.py                 # DESTRUCTIVE with --reset
    demo_seed_guard.py
    destructive_test_guard.py
  tests/                 # pytest suite (*_postgres.py require PostgreSQL)
  DEPENDENCIES.md
  MIGRATIONS.md
  requirements.in / requirements.txt
  requirements-dev.in / requirements-dev.txt

frontend/
  src/
    components/          # shared UI primitives
    pages/               # route components + co-located *.test.jsx
    utils/               # api.js, apiConfig.js + tests
    test/setup.js        # Vitest setup
  eslint.config.js
  vite.config.js         # includes the production API-URL build guard
  package.json

.github/workflows/CI.yml
```

---

## Prerequisites

| Requirement | Version | Source |
|---|---|---|
| Python | 3.11 (used by CI; 3.10+ expected to work) | `.github/workflows/CI.yml` |
| Node.js | 20 | `.github/workflows/CI.yml` |
| PostgreSQL | 16 in CI and the documented test container | `CI.yml`, `backend/MIGRATIONS.md` |
| Git | any recent version | — |

PostgreSQL is the real deployment and migration target. **SQLite is used only by the
safe local backend test suite** (`DATABASE_URL=sqlite:///./test.db` in `.env.test`);
migration, locking, constraint and seeding behaviour cannot be verified on it, which
is why those tests require PostgreSQL.

Docker is optional but is the documented way to obtain a disposable test database.

---

## Configuration

Copy the templates — never commit a real `.env`:

```bash
cp backend/.env.example backend/.env
cp backend/.env.test.example backend/.env.test
cp frontend/.env.example frontend/.env.local
```

### Backend (`backend/.env`)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string. Use the direct/session connection for migrations — a transaction pooler can break DDL. |
| `JWT_SECRET` | Yes | Signs access tokens. **Operational guidance:** use an independently random value of at least 32 bytes. Note that, unlike the receipt secret, this length is **not** enforced at startup. |
| `JWT_ALGORITHM` | No | Defaults to `HS256`, and `HS256` is the only accepted value. Normally leave it unset. |
| `KEYSTORE_MASTER_SECRET` | Yes | **Fernet-format key** wrapping each election's Paillier private key.<br>`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `RECEIPT_SIGNING_SECRET` | Yes | Keys the ballot commitment. Must be **≥ 32 UTF-8 bytes** and **different from both** `JWT_SECRET` and `KEYSTORE_MASTER_SECRET`; the app refuses to start otherwise. Rotating it invalidates every existing commitment.<br>`python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ENVIRONMENT` | No | Exactly one of `development`, `test`, `production` (case/whitespace normalised). Any other value is rejected at startup rather than defaulting to development. |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated `scheme://host[:port]`, no trailing path. Empty means no cross-origin access. Under `ENVIRONMENT=production`: at least one origin is required, `*` is rejected, and every entry must use HTTPS. |

### Backend test-only (`backend/.env.test`)

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Keep it SQLite. `conftest.py` refuses another backend unless it is named in `ALLOWED_TEST_DATABASES`, because per-test cleanup deletes rows. |
| `TESTING` | `true` — the suite refuses to run without it. |
| `TEST_POSTGRES_URL` | Disposable PostgreSQL for the migration/race/seed tests. Must name the database exactly `evoting_test` on a local host. |
| `ALLOW_DESTRUCTIVE_DB_TESTS` | Deliberately **not** stored in the file — it arms `DROP SCHEMA public CASCADE`. Pass it per command. |

### Frontend

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Base URL of the backend, e.g. `http://localhost:8000` locally or `https://api.example.edu` in production. |

Vite inlines `VITE_*` variables at **build time** — a bundle carries whatever value
was set when it was built, and there is no runtime override. Development falls back
to `http://localhost:8000` when unset; a **production build does not fall back** and
aborts instead. Production builds additionally require **HTTPS**:

```bash
VITE_API_BASE_URL=https://api.example.edu npm run build
```

Dependency and audit details are documented in
[`backend/DEPENDENCIES.md`](backend/DEPENDENCIES.md) rather than duplicated here.

---

## Database setup and migrations

The schema is managed by Alembic. The application does **not** create tables at
startup, and you should not call `Base.metadata.create_all()` — it only ever creates
missing *tables* and silently skips new columns on tables that already exist.

### Fresh database

```bash
cd backend
pip install -r requirements.txt
# set DATABASE_URL in backend/.env first
alembic upgrade head
python -m scripts.verify_schema      # read-only confirmation
```

### Existing database (including a deployed Supabase project)

The baseline tables already exist there, so revision `0001` must be **stamped, not
run**. The full procedure — inspect, stamp, upgrade, re-verify — is documented in
[`backend/MIGRATIONS.md`](backend/MIGRATIONS.md).

> **Back up the database and inspect it with `python -m scripts.verify_schema`
> before applying anything that writes.** Do not reduce the stamp/upgrade sequence
> to a single `alembic upgrade head` against a database that already has the
> baseline tables — it will fail on the existing objects.

---

## Running locally

Two terminals: one backend, one frontend.

### Terminal 1 — backend

```bash
cd backend

python -m venv venv
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (cmd)
venv\Scripts\activate.bat
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt     # pinned production set
alembic upgrade head                # apply migrations
uvicorn app.main:app --reload
```

Backend: <http://127.0.0.1:8000>

### Terminal 2 — frontend

```bash
cd frontend
npm ci        # lockfile is committed; prefer this over `npm install`
npm run dev
```

Frontend: <http://localhost:5173>

`VITE_API_BASE_URL` may be left unset for local development — the app falls back to
`http://localhost:8000`. Set it in `frontend/.env.local` if your backend runs
elsewhere.

---

## Demo data

`backend/scripts/seed_demo.py` populates a demo dataset (users, elections, real
encrypted ballots, and a genuinely closed/tallied election).

> **With `--reset` this truncates every application table.** It is not part of the
> quick-start path. Never point it at a shared, staging or production Supabase
> project.

It fails closed unless *all four* conditions hold: `DEMO_SEED_ALLOWED=true`, the
target host is in `DEMO_SEED_ALLOWED_HOSTS`, the target database is in
`DEMO_SEED_ALLOWED_DATABASES`, and `--reset` is passed. `DEMO_SEED_PASSWORD` is
required and has no default. The schema must already be migrated to head.

The guarded procedure and the full variable table are in
[`backend/MIGRATIONS.md`](backend/MIGRATIONS.md#seeding-the-demo-database).

---

## Running tests and quality checks

### Backend — safe suite (SQLite)

```bash
cd backend
pytest tests -q
```

Requires `backend/.env.test` (copy from `.env.test.example`); the suite refuses to
start unless `APP_ENV=test` and `TESTING=true` are loaded. The PostgreSQL-only files
are skipped when `TEST_POSTGRES_URL` is unset.

### Backend — PostgreSQL-gated suite

These cover migrations, uniqueness constraints, the vote/close race, audit-table
privileges and demo seeding. **The fixtures drop and recreate the `public` schema**,
so they demand a disposable, explicitly allowlisted database.

```bash
docker run --rm -d -p 55432:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=evoting_test \
  --name evoting-test-pg postgres:16

export TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:55432/evoting_test
ALLOW_DESTRUCTIVE_DB_TESTS=true pytest tests -q

docker rm -f evoting-test-pg
```

The guard rejects anything that is not PostgreSQL, on a local host, named exactly
`evoting_test`, with `ALLOW_DESTRUCTIVE_DB_TESTS=true`. **Never point these at a
live Supabase project or any database whose contents matter.**

### Frontend

```bash
cd frontend
npm test                                              # Vitest
npm run lint                                          # ESLint
VITE_API_BASE_URL=https://api.example.edu npm run build   # production build
```

### Dependency audits

```bash
cd backend && pip-audit -r requirements.txt --strict   # see DEPENDENCIES.md for the one documented suppression
cd frontend && npm run audit                           # better-npm-audit, level=high
```

---

## Continuous integration

[`.github/workflows/CI.yml`](.github/workflows/CI.yml) runs on pushes to `main` and
`refactor/**`, on pull requests to `main`, and on manual dispatch. Two jobs:

| Job | Steps |
|---|---|
| **backend** | Python 3.11; install pinned production + dev requirements; `pip-audit` on `requirements.txt` (with one documented, justified suppression); run the **full** pytest suite — including the PostgreSQL files — against a `postgres:16` service container with `ALLOW_DESTRUCTIVE_DB_TESTS=true`. |
| **frontend** | Node 20; `npm ci`; `npm run audit`; `npm run lint`; `npm run build` with a placeholder HTTPS API URL; `npm test`. |

---

## Operational verification

Read-only scripts, safe to run against any target including production. Both exit
non-zero on failure, so they can gate a deployment.

```bash
cd backend
python -m scripts.verify_schema                            # configured DATABASE_URL
python -m scripts.verify_schema --db-url "$URL"            # explicit target

python -m scripts.verify_audit_permissions                 # run AS the application role
python -m scripts.verify_audit_permissions --db-url "$APP_ROLE_DATABASE_URL"
```

- `verify_schema` — confirms every model table/column exists, nullability matches,
  and the uniqueness constraints the application relies on are present.
- `verify_audit_permissions` — confirms the connecting role can append to but not
  rewrite or erase the audit trail, checking *effective* privileges.

Audit-chain integrity is verified in-process via `verify_audit_chain(db)` from
`app.security.audit` (used by the test suite and the demo seed). **There is
currently no standalone CLI for it.**

> These three are strictly **read-only**. They are distinct from `alembic upgrade`,
> which writes schema, and from `seed_demo.py --reset`, which destroys data.

---

## API documentation

With the backend running, FastAPI serves interactive documentation at its defaults
(neither is disabled in `app/main.py`):

- Swagger UI — <http://127.0.0.1:8000/docs>
- ReDoc — <http://127.0.0.1:8000/redoc>
- OpenAPI schema — <http://127.0.0.1:8000/openapi.json>

A health check is available at `GET /health/db`.

---

## Supporting documentation

| Document | Contents |
|---|---|
| [`backend/MIGRATIONS.md`](backend/MIGRATIONS.md) | Alembic workflow, revision history, Supabase stamp/upgrade procedure, schema verification, guarded demo seeding, ballot commitments, audit chain, and audit-table role provisioning. |
| [`backend/DEPENDENCIES.md`](backend/DEPENDENCIES.md) | Dependency file roles, regenerating pins, auditing, and the reasoning behind the one suppressed advisory. |

---

## Repository

```bash
git clone https://github.com/Peanutz10321/CSIT-321-FYP-26-S2-13
cd CSIT-321-FYP-26-S2-13
```
