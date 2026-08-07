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
| **Vote/finalization concurrency** | Voting takes a shared row lock (`FOR SHARE`); the deadline-driven finalize takes an exclusive one (`FOR UPDATE`). A vote therefore either commits before the tally or is rejected afterwards, so a valid receipt always corresponds to a counted ballot. Two concurrent finalizations tally exactly once; the loser of the race re-reads the completed row and does no work. |
| **Database constraints** | Uniqueness on `ballots.election_voter_id` (one ballot per enrolment), `ballots.receipt_code`, `ballots.ballot_commitment`, `users.external_id` / `username` / `email`, and `(election_id, voter_id)` on enrolments. Duplicate voting is prevented by the database, not only by an application check. |
| **Ballot commitments** | HMAC-SHA256 over a canonical serialisation of the ballot id, election id, receipt code, **complete ciphertext**, a digest of the ballot configuration and candidate set, and the submission time — keyed with a dedicated `RECEIPT_SIGNING_SECRET`. Generated for every ballot, stored on the row, and returned on the receipt. **Not currently verified:** there is no verification endpoint, no frontend check, and the tally does not validate ballots against their commitments before publishing results. The stored value is evidence that can be checked out of band; the running application does not detect a mismatch. Verification is deferred future work. |
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

Tally (on finalization): ciphertexts are summed homomorphically, the private
key is loaded from the keystore, and ONLY the per-candidate aggregate is
decrypted and cached in candidate_results.
```

Elections are finalized automatically. There is no manual close endpoint: when an
election is still active and its deadline has passed, the next request for its
results runs the tally exactly once, caches the per-candidate totals, marks the
election completed, and records the `election_closed` and `results_published`
audit events. Finalization is therefore lazy — it happens on the first read after
the deadline, not at the deadline itself. Voting is unaffected by that delay,
because the vote path rejects ballots outside the voting window on the clock
rather than on the election's status. Every later read is served from the cached
results with no tally, no private-key load, and no write.

| Layer | Technology |
|---|---|
| Frontend | React 19, React Router 7, Tailwind CSS 3, Vite 8 |
| Backend | FastAPI 0.139, Uvicorn 0.51, Pydantic 2 / pydantic-settings |
| ORM & migrations | SQLAlchemy 2.0, Alembic 1.18 |
| Database | PostgreSQL (Supabase-compatible), `psycopg2-binary` |
| Cryptography | `phe` 1.5 (Paillier), `cryptography` 50 (Fernet), `python-jose` (JWT), `passlib` + `bcrypt` |
| Backend tests | pytest 9, httpx |
| Frontend tests | Vitest 4, React Testing Library, jsdom |
| CI | GitHub Actions |

Exact pins live in `backend/requirements.txt` and `frontend/package-lock.json`.

---

## Project structure

```
backend/
  alembic/
    versions/            # 0001 baseline → 0005 user group (current head)
  app/
    core/                # time helpers (naive SGT)
    models/              # SQLAlchemy models
    routes/              # auth, users, admin users, elections, votes, results
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
| Node.js | **20.19+** or **22.12+** (CI uses the Node 20 channel) | `vite@8.1.5` engines in `frontend/package-lock.json` |
| PostgreSQL | 16 in CI and in both documented containers (development and test) | `CI.yml`, `backend/MIGRATIONS.md` |
| Git | any recent version | — |

Vite 8 requires Node `^20.19.0 || >=22.12.0`. A Node 20.0–20.18 release is below that
floor: `npm ci` reports an `EBADENGINE` warning rather than failing outright, so the
install appears to succeed and the build breaks later.

PostgreSQL is the real deployment and migration target. **SQLite is used only by the
safe local backend test suite** (`DATABASE_URL=sqlite:///./test.db` in `.env.test`);
migration, locking, constraint and seeding behaviour cannot be verified on it, which
is why those tests require PostgreSQL.

Docker is optional. It is the documented way to obtain both the local development
database and the disposable test database, but a native PostgreSQL install works
equally well.

---

## Get the code

Everything below assumes you start from the repository root, and each command
block states the directory it must be run from.

```bash
git clone https://github.com/Peanutz10321/CSIT-321-FYP-26-S2-13
cd CSIT-321-FYP-26-S2-13
```

The repository root is the directory containing `backend/`, `frontend/` and this
file.

---

## Create the development database

The application needs its own PostgreSQL database named `evoting`. It is **not**
created for you: the backend never issues DDL, and `alembic upgrade head` fails if
the database does not already exist.

> This is a **different database from the one the PostgreSQL test suite uses.**
> The test database is called `evoting_test`, listens on port 55432, and is
> dropped and recreated by the tests. Never point `DATABASE_URL` at it, and never
> point `TEST_POSTGRES_URL` at the database created here. See
> [Running tests and quality checks](#running-tests-and-quality-checks).

### Option A — Docker (persistent named volume)

Run from anywhere. The credentials below are **development-only placeholders**;
do not reuse them for anything reachable from a network.

```bash
docker volume create evoting-dev-data

docker run -d --name evoting-dev-pg -p 5432:5432 \
  -e POSTGRES_USER=evoting_dev \
  -e POSTGRES_PASSWORD=dev-only-not-a-real-password \
  -e POSTGRES_DB=evoting \
  -v evoting-dev-data:/var/lib/postgresql/data \
  postgres:16
```

PowerShell — same command, backtick continuations instead of `\`:

```powershell
docker volume create evoting-dev-data

docker run -d --name evoting-dev-pg -p 5432:5432 `
  -e POSTGRES_USER=evoting_dev `
  -e POSTGRES_PASSWORD=dev-only-not-a-real-password `
  -e POSTGRES_DB=evoting `
  -v evoting-dev-data:/var/lib/postgresql/data `
  postgres:16
```

The named volume means `docker stop` / `docker start evoting-dev-pg` preserves your
data. Deliberately **no `--rm`** here — the test container uses `--rm` because it is
meant to be thrown away; this one is not.

Matching `DATABASE_URL` for `backend/.env`:

```
DATABASE_URL=postgresql://evoting_dev:dev-only-not-a-real-password@localhost:5432/evoting
```

### Option B — native PostgreSQL 16

With a local server already running and `psql` on your `PATH`:

```bash
createdb evoting
```

If your login role differs from your OS user, or you want a dedicated role:

```bash
psql -c "CREATE ROLE evoting_dev LOGIN PASSWORD 'dev-only-not-a-real-password';"
createdb -O evoting_dev evoting
```

Then use the same `DATABASE_URL` shown above, adjusting host, port and credentials
to match your server.

### Confirm it is reachable

```bash
docker exec evoting-dev-pg psql -U evoting_dev -d evoting -c "select 1;"   # Docker
psql "postgresql://evoting_dev:dev-only-not-a-real-password@localhost:5432/evoting" -c "select 1;"   # native
```

---

## Configuration

Copy the templates — never commit a real `.env`. Run from the repository root:

```bash
cp backend/.env.example backend/.env
cp backend/.env.test.example backend/.env.test
cp frontend/.env.example frontend/.env.local
```

PowerShell:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item backend\.env.test.example backend\.env.test
Copy-Item frontend\.env.example frontend\.env.local
```

> **Copying is not enough.** `backend/.env.example` ships with `JWT_SECRET`,
> `KEYSTORE_MASTER_SECRET` and `RECEIPT_SIGNING_SECRET` **deliberately empty**, and
> with a placeholder `DATABASE_URL`. All four must hold real values before the
> application is usable. The first thing you will see if you skip this is
> `ValidationError: RECEIPT_SIGNING_SECRET must be at least 32 bytes`. Fill them in
> before running anything, including `alembic`.
>
> `backend/.env.test` is the exception: it is throwaway by design and works as
> copied.

**A blank value is refused at startup**, so none of the four can be silently
forgotten. What each check does and does not cover:

| Variable | If left empty | Format checked? |
|---|---|---|
| `RECEIPT_SIGNING_SECRET` | Rejected — under 32 bytes | Yes: ≥32 bytes, and must differ from the other two secrets |
| `JWT_SECRET` | Rejected — `JWT_SECRET must not be empty` | **No.** Any non-blank value is accepted, including a short one |
| `KEYSTORE_MASTER_SECRET` | Rejected — `KEYSTORE_MASTER_SECRET must not be empty` | **No.** A non-blank value that is not a valid Fernet key still fails later, at election activation |
| `DATABASE_URL` | Rejected, but indirectly — SQLAlchemy raises `Could not parse SQLAlchemy URL from given URL string` | No |

Emptiness is all that is enforced for `JWT_SECRET` and `KEYSTORE_MASTER_SECRET`. A
weak-but-present `JWT_SECRET` is accepted, so use the generator above rather than
typing something short — the length guidance is yours to follow, not the app's to
enforce.

### Generate the three secrets

Run from `backend/` with the virtual environment active (see
[Running locally](#running-locally)), or with any Python that has `cryptography`
installed:

```bash
# KEYSTORE_MASTER_SECRET — must be a Fernet key, not arbitrary random text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# JWT_SECRET and RECEIPT_SIGNING_SECRET — run once for each, never reuse the value
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generate `JWT_SECRET` and `RECEIPT_SIGNING_SECRET` **separately**.
`RECEIPT_SIGNING_SECRET` must differ from both other secrets or the application
refuses to start.

### Backend (`backend/.env`)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | **Yes** | PostgreSQL connection string for the `evoting` database created above. Use the direct/session connection for migrations — a transaction pooler can break DDL. |
| `JWT_SECRET` | **Yes** | Signs access tokens. **Operational guidance:** use an independently random value of at least 32 bytes. Note that, unlike the receipt secret, this length is **not** enforced at startup. |
| `JWT_ALGORITHM` | No | Defaults to `HS256`, and `HS256` is the only accepted value. Normally leave it unset. |
| `KEYSTORE_MASTER_SECRET` | **Yes** | **Fernet-format key** wrapping each election's Paillier private key. An arbitrary random string is *not* accepted — it must be a real Fernet key. |
| `RECEIPT_SIGNING_SECRET` | **Yes** | Keys the ballot commitment. Must be **≥ 32 UTF-8 bytes** and **different from both** `JWT_SECRET` and `KEYSTORE_MASTER_SECRET`; the app refuses to start otherwise. |
| `ENVIRONMENT` | No | Defaults to `development`. Exactly one of `development`, `test`, `production` (case/whitespace normalised). Any other value is rejected at startup rather than defaulting to development. |
| `CORS_ALLOWED_ORIGINS` | Conditional | Not needed for an API-only backend (Swagger UI, `curl`, tests). **Required as soon as you use the React frontend**, because the browser calls the API from a different origin. Set `http://localhost:5173` for local development. |

**Two secrets carry consequences if you change them later:**

- **`KEYSTORE_MASTER_SECRET` must be retained** for as long as any existing
  election keys must remain usable. It Fernet-wraps every election's Paillier
  private key; losing or rotating it makes those keys undecryptable, so affected
  elections can never be tallied. Back it up with the database, not in it.
- **Rotating `RECEIPT_SIGNING_SECRET` invalidates every existing ballot
  commitment.** Previously issued receipts no longer recompute against the stored
  value. Choose it once per deployment and leave it alone.

**CORS in more detail:**

- Unset means **no** cross-origin access — a fail-closed default, not an implicit
  wildcard. The backend still starts; the browser is what refuses.
- Local development: `CORS_ALLOWED_ORIGINS=http://localhost:5173` (the value shipped
  in `.env.example`).
- `ENVIRONMENT=production` additionally requires **at least one origin**, rejects the
  wildcard `*` outright, and requires **HTTPS** on every entry. List exact frontend
  origins, e.g. `https://vote.example.edu,https://admin.example.edu`.
- Entries are `scheme://host[:port]` with no trailing path. One malformed entry
  rejects the whole list at startup rather than being silently dropped.

### Backend test-only (`backend/.env.test`)

This file is throwaway by design and works exactly as copied — do not put real
secrets or a real connection string in it.

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Keep it SQLite. `conftest.py` refuses another backend unless it is named in `ALLOWED_TEST_DATABASES`, because per-test cleanup deletes rows. |
| `TESTING` | `true` — the suite refuses to run without it. |
| `TEST_POSTGRES_URL` | **Commented out in the template on purpose.** While it is unset the five `*_postgres.py` files skip, so `pytest tests -q` is safe by default. Export it only when you have the disposable `evoting_test` container running. |
| `ALLOW_DESTRUCTIVE_DB_TESTS` | Deliberately **not** stored in the file — it arms `DROP SCHEMA public CASCADE`. Pass it per command. |

`APP_ENV=test` is set by `tests/conftest.py` itself, which is what makes the suite
load `.env.test` rather than `.env`. You do not set it by hand.

### Frontend

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Base URL of the backend, e.g. `http://localhost:8000` locally or `https://api.example.edu` in production. |

Vite inlines `VITE_*` variables at **build time** — a bundle carries whatever value
was set when it was built, and there is no runtime override. Development falls back
to `http://localhost:8000` when unset; a **production build does not fall back** and
aborts instead. Production builds additionally require **HTTPS**.

The inline `VAR=value command` form is **bash-only** — it is a syntax error in
PowerShell and does nothing useful in `cmd`. Set the variable first on Windows:

```bash
# macOS / Linux (bash)
VITE_API_BASE_URL=https://api.example.edu npm run build
```

```powershell
# Windows (PowerShell)
$env:VITE_API_BASE_URL = "https://api.example.edu"
npm run build
```

```bat
:: Windows (cmd) — no space before && , or it lands in the value
set VITE_API_BASE_URL=https://api.example.edu&& npm run build
```

Dependency and audit details are documented in
[`backend/DEPENDENCIES.md`](backend/DEPENDENCIES.md) rather than duplicated here.

---

## Database setup and migrations

The schema is managed by Alembic. The application does **not** create tables at
startup, and you should not call `Base.metadata.create_all()` — it only ever creates
missing *tables* and silently skips new columns on tables that already exist.

The current head is **`0005_user_group`**. A fresh database runs the full chain:
`0001_baseline` → `0002_ballot_config` → `0003_ballot_commitment` →
`0004_audit_chain` → `0005_user_group`. Revision purposes are listed in
[`backend/MIGRATIONS.md`](backend/MIGRATIONS.md#revisions).

### Fresh database

Run from `backend/`, with the database created and `backend/.env` filled in first —
`alembic` loads the same settings the app does, so **all four required variables**
(`DATABASE_URL`, `JWT_SECRET`, `KEYSTORE_MASTER_SECRET`, `RECEIPT_SIGNING_SECRET`)
must be set or it fails before it connects.

```bash
cd backend
alembic upgrade head                 # 0001 → 0005
python -m scripts.verify_schema      # read-only confirmation
```

`verify_schema` printing `OK - database schema matches the models.` and exiting `0`
means the database is ready.

### Existing database (including a deployed Supabase project)

**Start with `alembic current`.** It is the only command that tells you what
revision Alembic has recorded, and the answer decides everything that follows:

- **It prints a revision** — the database is already under Alembic control. Back up,
  then `alembic upgrade head`. **Do not stamp**: stamping overwrites the recorded
  revision, rewinding it, and the upgrade then replays migrations that have already
  run. `0003_ballot_commitment` is an unguarded rename and fails on replay.
- **It prints nothing** — the database is unversioned. If its tables match the `0001`
  baseline, `alembic stamp 0001_baseline` records that fact without running DDL, and
  `alembic upgrade head` applies `0002` onward.

`python -m scripts.verify_schema` is **not** a substitute for `alembic current` — it
compares tables and columns against the models and never reads `alembic_version`.

The full decision procedure is in
[`backend/MIGRATIONS.md`](backend/MIGRATIONS.md#existing-database-the-deployed-supabase-project).

> **Back up the database before anything that writes**, and never reduce the
> sequence to a bare `alembic upgrade head` or a bare `alembic stamp` without first
> establishing the recorded revision.

---

## Running locally

The full sequence, in order. Steps 1–3 are covered above; do not skip them.

1. [Clone the repository](#get-the-code)
2. [Create the `evoting` development database](#create-the-development-database)
3. [Copy the env templates and fill in the four required backend values](#configuration)
4. Create and activate a virtual environment
5. Install backend dependencies
6. Run Alembic migrations
7. Verify the schema
8. Start the backend
9. Install frontend dependencies
10. Start the frontend
11. Verify everything is up

Steps 4–8 run in one terminal, 9–10 in a second.

### Terminal 1 — backend (steps 4–8)

Run from `backend/`.

**macOS / Linux (bash):**

```bash
cd backend

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt     # pinned production set
alembic upgrade head                # step 6 — apply migrations
python -m scripts.verify_schema     # step 7 — read-only confirmation
uvicorn app.main:app --reload       # step 8
```

**Windows (PowerShell):**

```powershell
cd backend

py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
alembic upgrade head
python -m scripts.verify_schema
uvicorn app.main:app --reload
```

If `Activate.ps1` is blocked by the execution policy, unblock it **for the current
process only** — this reverts when the terminal closes and changes nothing
system-wide:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\venv\Scripts\Activate.ps1
```

**Windows (cmd):**

```
cd backend
py -3.11 -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
alembic upgrade head
python -m scripts.verify_schema
uvicorn app.main:app --reload
```

Backend: <http://127.0.0.1:8000>

### Terminal 2 — frontend (steps 9–10)

Run from `frontend/`. Identical on all three platforms:

```bash
cd frontend
npm ci        # lockfile is committed; prefer this over `npm install`
npm run dev
```

Frontend: <http://localhost:5173>

`VITE_API_BASE_URL` may be left unset for local development — the app falls back to
`http://localhost:8000`. Set it in `frontend/.env.local` if your backend runs
elsewhere. It is only *required* for a production build.

### Step 11 — verify

**Open <http://localhost:5173> in a browser.** That is the application; the backend
port serves the API and its documentation, not the UI.

| Check | Command or URL | Expected |
|---|---|---|
| Backend process | <http://127.0.0.1:8000> | `{"message":"E-Voting backend is running"}` |
| Database connectivity | <http://127.0.0.1:8000/health/db> | `{"database":"connected","time":"…"}` |
| API documentation | <http://127.0.0.1:8000/docs> | Swagger UI loads |
| Frontend | <http://localhost:5173> | The landing page renders |
| Frontend → backend | Register a voter through the UI | Account is created, and you can log in |

If the UI loads but every action fails, the cause is almost always
`CORS_ALLOWED_ORIGINS` — see [Common startup problems](#common-startup-problems).

Register a voter or organizer through the UI to get started. **System Admin
accounts cannot be self-registered** — see [First System Admin
account](#first-system-admin-account).

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

The seed prints its login accounts on success. The password for **every** account is
whatever you set in `DEMO_SEED_PASSWORD`:

| Account | Role |
|---|---|
| `admin@demo.com` | System administrator |
| `organizer@demo.com` | Election organizer |
| `voter1@demo.com` … `voter4@demo.com` | Voters (the summary prints the first two; all four exist) |
| `suspended@demo.com` | A suspended voter, for testing the suspension path |

---

## First System Admin account

System administrators **cannot self-register**: `POST /auth/register` rejects the
`system_admin` role with `403`, and there is no endpoint anywhere in the API that
creates one. Admin accounts are provisioned out of band.

This matters because every `/admin/users` endpoint — and the Manage Users screens in
the frontend — requires an existing System Admin token, so there is no way to
bootstrap the first one through the running application.

### Disposable local / demo database

Use the guarded demo seed. It creates `admin@demo.com` along with the other demo
accounts listed under [Demo data](#demo-data).

> **This truncates every application table.** `--reset` is mandatory — the script
> refuses to run without it. Point it **only** at a disposable local or demo
> database that you are willing to erase. Never at a shared, staging or production
> project.

Run from `backend/`, against a migrated database:

```bash
cd backend

export DEMO_SEED_ALLOWED=true
export DEMO_SEED_ALLOWED_HOSTS=localhost
export DEMO_SEED_ALLOWED_DATABASES=evoting_demo   # must match your target database
export DEMO_SEED_PASSWORD='choose-your-own'       # no default; never printed

python -m scripts.seed_demo --reset
```

PowerShell:

```powershell
cd backend

$env:DEMO_SEED_ALLOWED = "true"
$env:DEMO_SEED_ALLOWED_HOSTS = "localhost"
$env:DEMO_SEED_ALLOWED_DATABASES = "evoting_demo"
$env:DEMO_SEED_PASSWORD = "choose-your-own"

python -m scripts.seed_demo --reset
```

`DEMO_SEED_PASSWORD` is supplied through the environment and has no default; the
script never prints it. Choose your own value — do not commit it, and do not reuse a
real password. Then sign in as `admin@demo.com` with that value.

---

## Running tests and quality checks

### Backend — safe suite (SQLite)

The test tooling lives in `requirements-dev.txt`, **not** in `requirements.txt`.
Install both, or `pytest` will not exist:

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest tests -q
```

Requires `backend/.env.test` (copy from `.env.test.example`); the suite refuses to
start unless `APP_ENV=test` and `TESTING=true` are loaded. `conftest.py` sets
`APP_ENV` itself; `TESTING=true` comes from the file.

This run needs **no PostgreSQL and no database of your own** — it uses a throwaway
SQLite file. The five `*_postgres.py` files skip themselves while
`TEST_POSTGRES_URL` is unset, which is why the template ships it commented out. A
clean run reports those as *skipped*, not failed.

> If you see dozens of errors reading
> `Refusing destructive database tests unless ALLOW_DESTRUCTIVE_DB_TESTS=true`, then
> `TEST_POSTGRES_URL` is set — either uncommented in your `backend/.env.test` or
> exported in your shell. Unset it for the safe run.

### Backend — PostgreSQL-gated suite

These cover migrations, uniqueness constraints, the vote/finalization race,
audit-table privileges and demo seeding. **The fixtures drop and recreate the
`public` schema**, so they demand a disposable, explicitly allowlisted database.

> This container is **separate from and incompatible with** your `evoting`
> development database. It is named `evoting_test`, runs on port 55432, uses `--rm`
> and no volume, and is destroyed at the end. Never substitute your development
> database here — the guard is what stops you, and it is not decoration.

**macOS / Linux (bash):**

```bash
docker run --rm -d -p 55432:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=evoting_test \
  --name evoting-test-pg postgres:16

cd backend
export TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:55432/evoting_test
ALLOW_DESTRUCTIVE_DB_TESTS=true pytest tests -q

docker rm -f evoting-test-pg
```

**Windows (PowerShell):**

```powershell
docker run --rm -d -p 55432:5432 `
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=evoting_test `
  --name evoting-test-pg postgres:16

cd backend
$env:TEST_POSTGRES_URL = "postgresql://postgres:postgres@localhost:55432/evoting_test"
$env:ALLOW_DESTRUCTIVE_DB_TESTS = "true"
pytest tests -q

Remove-Item Env:\ALLOW_DESTRUCTIVE_DB_TESTS
Remove-Item Env:\TEST_POSTGRES_URL
docker rm -f evoting-test-pg
```

Unset both variables afterwards, or your next "safe" run will try to reach a
container that no longer exists.

The guard rejects anything that is not PostgreSQL, on a local host, named exactly
`evoting_test`, with `ALLOW_DESTRUCTIVE_DB_TESTS=true`. **Never point these at a
live Supabase project or any database whose contents matter.**

### Frontend

```bash
cd frontend
npm test          # Vitest
npm run lint      # ESLint
```

The production build needs an HTTPS API URL. Inline assignment is bash-only:

```bash
VITE_API_BASE_URL=https://api.example.edu npm run build      # bash
```

```powershell
$env:VITE_API_BASE_URL = "https://api.example.edu"           # PowerShell
npm run build
```

### Dependency audits

```bash
# backend — the ignored advisory is the one documented in DEPENDENCIES.md
cd backend
pip-audit -r requirements.txt --strict --ignore-vuln PYSEC-2026-1325

# frontend — better-npm-audit at --level high, one advisory suppressed via .nsprc
cd frontend
npm run audit
```

The backend command must match CI exactly, including the suppression. Without
`--ignore-vuln` it exits non-zero on the unfixable `ecdsa` advisory; with a lowered
severity threshold it would hide unrelated findings too. The suppression is valid
**only while JWT signing is enforced as HS256** and the ECDSA code path stays
unreachable — see [`backend/DEPENDENCIES.md`](backend/DEPENDENCIES.md#backend) for
the full justification.

---

## Continuous integration

[`.github/workflows/CI.yml`](.github/workflows/CI.yml) runs on pushes to `main` and
`refactor/**`, on pull requests to `main`, and on manual dispatch. Two jobs:

| Job | Steps |
|---|---|
| **backend** | Python 3.11; install pinned production + dev requirements; `pip-audit` on `requirements.txt` (with one documented, justified suppression); run the **full** pytest suite — including the PostgreSQL files — against a `postgres:16` service container with `ALLOW_DESTRUCTIVE_DB_TESTS=true`. |
| **frontend** | Node 20; `npm ci`; `npm run audit`; `npm run lint`; `npm run build` with a placeholder HTTPS API URL; `npm test`. |

### How CI differs from a local run

| | Local | CI |
|---|---|---|
| Configuration | `backend/.env` and `backend/.env.test` | Environment variables injected directly in the workflow; no `.env` files exist |
| PostgreSQL | Disposable container you start yourself on **55432** | `postgres:16` service container on the default **5432** |
| Dependencies | You must install `requirements.txt` **and** `requirements-dev.txt` | Both installed in one step |
| PostgreSQL tests | Skipped unless you export `TEST_POSTGRES_URL` and arm the guard | Always run, with `ALLOW_DESTRUCTIVE_DB_TESTS=true` set explicitly |
| Verbosity | `pytest tests -q` | `pytest tests -v` |

The practical consequence: **a green local run is a weaker signal than a green CI
run**, because locally the migration, constraint, race-condition and seeding tests
skip by default. Run the PostgreSQL-gated suite before opening a pull request that
touches migrations, models or the vote/close path.

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

## Common startup problems

| Symptom | Likely cause | Smallest fix |
|---|---|---|
| `ValidationError: RECEIPT_SIGNING_SECRET must be at least 32 bytes` | You copied `.env.example` but did not fill in the secrets — they ship empty. | Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and set it in `backend/.env`. It must also differ from `JWT_SECRET` and `KEYSTORE_MASTER_SECRET`. |
| `ValueError: RECEIPT_SIGNING_SECRET must be different from JWT_SECRET and KEYSTORE_MASTER_SECRET` | The same value was pasted into more than one secret. | Generate a fresh value for each of the three. |
| `ValueError: JWT_SECRET must not be empty` / `KEYSTORE_MASTER_SECRET must not be empty` | The value is blank or whitespace-only — `.env.example` ships both empty. | Fill them in with the generators above. Note the check is presence only: a short `JWT_SECRET` passes, so still use a 32-byte random value. |
| `binascii.Error` / `ValueError: Fernet key must be 32 url-safe base64-encoded bytes` | `KEYSTORE_MASTER_SECRET` is arbitrary random text rather than a Fernet key. | Regenerate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Note this makes existing election keys undecryptable — only do it on a database you can discard. |
| `psycopg2.OperationalError: could not connect to server` | PostgreSQL is not running, or the host/port in `DATABASE_URL` is wrong. | Start the container (`docker start evoting-dev-pg`) and confirm the port matches. See [Create the development database](#create-the-development-database). |
| `psycopg2.OperationalError: database "evoting" does not exist` | The server is up but the database was never created. | Create it — `createdb evoting`, or recreate the container with `-e POSTGRES_DB=evoting`. |
| `No module named pytest` | Only `requirements.txt` was installed. The test tooling is in `requirements-dev.txt`. | `pip install -r requirements.txt -r requirements-dev.txt` from `backend/`. |
| `alembic: command not found`, or Alembic exits with a `ValidationError` | The virtual environment is not active, or `backend/.env` is incomplete. Alembic loads the same settings the app does. | Activate the venv and fill in all four required variables before running `alembic upgrade head`. |
| Browser console: `blocked by CORS policy` / `No 'Access-Control-Allow-Origin' header` | `CORS_ALLOWED_ORIGINS` is unset or does not match the frontend origin. The backend starts fine — only the browser refuses. | Set `CORS_ALLOWED_ORIGINS=http://localhost:5173` in `backend/.env` and restart the backend. |
| Frontend loads but every request fails with a connection error | The backend is not running, or `VITE_API_BASE_URL` points somewhere else. | Confirm <http://127.0.0.1:8000/health/db> responds, and check `frontend/.env.local`. |
| `npm run build` fails: `VITE_API_BASE_URL is missing or blank` / `must use https in a production build` | Production builds require an explicit HTTPS URL and never fall back to localhost. | bash: `VITE_API_BASE_URL=https://api.example.edu npm run build`. PowerShell: set `$env:VITE_API_BASE_URL` first, then run the build — the inline form is bash-only. This is intentional; see [Configuration](#frontend). |
| Dozens of `Refusing destructive database tests unless ALLOW_DESTRUCTIVE_DB_TESTS=true` errors | `TEST_POSTGRES_URL` is set, so the PostgreSQL files were collected instead of skipped. | Unset it for the safe run, or arm the guard and start the `evoting_test` container. See [Running tests](#backend--safe-suite-sqlite). |
| `Refusing destructive migration tests unless the database is 'evoting_test'` | `TEST_POSTGRES_URL` points at the wrong database — very possibly your development one. | Point it at the disposable `evoting_test` container. Do not "fix" this by renaming your development database. |
| PowerShell: `Activate.ps1 cannot be loaded because running scripts is disabled` | The default execution policy blocks local scripts. | `Set-ExecutionPolicy -Scope Process Bypass` in that terminal, then activate. Process scope reverts on close — do not change the machine policy. |
| `pip-audit` exits `1` on `ecdsa` / `PYSEC-2026-1325` | The documented suppression was omitted. | Use `pip-audit -r requirements.txt --strict --ignore-vuln PYSEC-2026-1325`, matching CI. |

---

## Supporting documentation

| Document | Contents |
|---|---|
| [`backend/MIGRATIONS.md`](backend/MIGRATIONS.md) | Alembic workflow, revision history, Supabase stamp/upgrade procedure, schema verification, guarded demo seeding, ballot commitments, audit chain, and audit-table role provisioning. |
| [`backend/DEPENDENCIES.md`](backend/DEPENDENCIES.md) | Dependency file roles, regenerating pins, auditing, and the reasoning behind the one suppressed advisory. |
