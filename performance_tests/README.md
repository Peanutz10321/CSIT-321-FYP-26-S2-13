# Performance-test data preparation

Scripts that prepare a staging deployment for a load test of the homomorphic
e-voting backend, and then verify the result is actually usable.

They create, through the public HTTP API only:

| What | How many |
| --- | --- |
| Organizer account | 1 (created, or reused if the batch already has one) |
| Voter accounts | 50 |
| Active single-choice elections | 3 |
| Candidates per election | 2 (`Performance Candidate A`, `Performance Candidate B`) |
| Eligible voters per election | the **same** 50 voters |

The same fifty voters are eligible for all three elections — 50 accounts total,
not 150. Duplicate-vote prevention is per election, so one voter can cast one
ballot in each of the three runs.

## Safety boundaries

Read this before running anything.

- **This creates permanent staging records.** There is deliberately no delete,
  cleanup, reset or truncate mode. The backend exposes no way to delete a user,
  and only *draft* elections can be deleted — these are created active. Whatever
  you create, you live with. Pick a batch you are happy to leave behind.
- **Never point these at production.** Guards 2–5 below exist to make that
  impossible by accident, but they are a safety net, not a substitute for
  checking `PERF_BASE_URL` yourself.
- **No database access.** The scripts speak HTTP. They never open a database
  connection, never insert or update rows directly, and share nothing with
  `backend/scripts/seed_demo.py`, which truncates tables and must not be used
  here.
- **Nothing secret is written to disk.** Passwords and JWTs are held in memory
  for the length of the run. The manifest is scanned before every write and the
  write is refused if it contains a password, token, connection string or key.
- **Verification changes nothing.** It builds its client with a request hook that
  raises on any PUT, PATCH, DELETE or non-login POST before the request is sent.

### The eight guards on the setup script

No mutating request is made until all of these pass:

1. `PERF_SETUP_ALLOWED` is exactly `true` — not `TRUE`, `1` or `yes`.
2. `PERF_BASE_URL` is a valid HTTPS URL.
3. `PERF_PRODUCTION_BASE_URL` is set.
4. The two URLs are different once normalised (case, port, trailing slash).
5. The staging hostname contains `staging` or `performance`.
   *(Guards 2 and 5 are replaced by a loopback-only rule — and by nothing else —
   when `PERF_LOCAL_TEST_ALLOWED=true`; see
   [Local testing](#local-testing-against-127001). Guards 1, 3, 4 and 6-8 always
   apply.)*
6. You retype the target URL when prompted, unless you passed `--yes`.
7. The target, batch and exact volumes are printed *before* that prompt.
8. `GET /health/db` returns 200 and reports `"database": "connected"`.

Guards 2–5 and 8 apply to the verification script too. Guard 1 does not:
verification changes nothing, so it is not gated behind the arming flag.

## Required environment variables

| Variable | Required | Default |
| --- | --- | --- |
| `PERF_BASE_URL` | yes | — |
| `PERF_PRODUCTION_BASE_URL` | yes | — |
| `PERF_LOCAL_TEST_ALLOWED` | no | `false` — exactly `true` arms [loopback-only local mode](#local-testing-against-127001) |
| `PERF_SETUP_ALLOWED` | setup only | — (must be exactly `true`) |
| `PERF_BATCH` | recommended | current date/time, `YYYYMMDDHHMM` |
| `PERF_ORGANIZER_EMAIL` | no | `perf_organizer_<batch>@test.com` |
| `PERF_ORGANIZER_USERNAME` | no | `perf_organizer_<batch>` |
| `PERF_ORGANIZER_PASSWORD` | yes | **none — never defaulted** |
| `PERF_VOTER_PASSWORD` | setup, and `--check-logins` | **none — never defaulted** |
| `PERF_ELECTION_DURATION_HOURS` | no | `24` |

Passwords have no default and must be at least 8 characters, matching the
backend's registration rule. A short one is rejected before the first request
rather than as a 422 partway through the run.

`PERF_BATCH` must be 1–24 alphanumeric characters — it is embedded in every
generated username and email address. **Set it explicitly.** The default is
derived from the clock and changes every minute, so a run that relies on the
default cannot be resumed.

See [.env.example](.env.example) for an annotated template. It contains
placeholders only; do not fill it in and commit it.

## Setup

Run everything from the repository root, with the backend virtualenv active.

### PowerShell

```powershell
# From the repository root
.\backend\venv\Scripts\Activate.ps1

$env:PERF_BASE_URL            = "https://<your-staging-host>.example.com"
$env:PERF_PRODUCTION_BASE_URL = "https://<your-production-host>.example.com"
$env:PERF_SETUP_ALLOWED       = "true"
$env:PERF_BATCH               = "<YYYYMMDDHHMM>"
$env:PERF_ORGANIZER_PASSWORD  = Read-Host "Organizer password" -AsSecureString `
    | ForEach-Object { [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) }
$env:PERF_VOTER_PASSWORD      = Read-Host "Voter password" -AsSecureString `
    | ForEach-Object { [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) }
$env:PERF_ELECTION_DURATION_HOURS = "24"
```

Using `Read-Host` keeps the passwords out of your shell history. Setting them
with a plain `$env:PERF_VOTER_PASSWORD = "…"` puts them in
`ConsoleHost_history.txt`.

### Run it

```powershell
python -m performance_tests.setup_performance_data
```

You will see the plan, and then be asked to retype the target URL:

```
  Performance-test data setup
  ----------------------------------------------------
  Target URL          : https://<your-staging-host>.example.com
  Batch               : 20260810A
  Organizer accounts  : 1 (created or reused)
  Voter accounts      : 50 (created)
  Elections           : 3 (created, active)
  ----------------------------------------------------
  This creates PERMANENT staging records. There is no cleanup mode.

Type the target URL to confirm (https://<your-staging-host>.example.com):
```

Anything other than the exact normalised target aborts the run before a single
request is sent. In CI or a scripted run, skip the prompt with `--yes` — every
other guard still applies:

```powershell
python -m performance_tests.setup_performance_data --yes
```

There is no separate `--dry-run` flag. Confirmation *is* the dry run: the plan is
printed first, and pressing Ctrl-C or typing anything else leaves the deployment
untouched. To see what a run would generate without contacting anything at all,
run the unit tests — they exercise the full flow against a mock transport.

Progress is reported per account:

```
Health check passed: database connected.
Organizer perf_organizer_20260810A@test.com not found — registering.
Organizer registered and logged in.
Created voter 001/050
Created voter 002/050
...
Created election 1/3 (PERF-20260810A-RUN-01, 6f1e…)
```

## Resuming an interrupted run

The manifest is rewritten atomically — temp file, then `os.replace` — after
**every** successful creation, so at most the account in flight is lost. Rerun
with the **same** `PERF_BATCH` and the script continues where it stopped:

```powershell
$env:PERF_BATCH = "20260810A"   # the same batch as the interrupted run
python -m performance_tests.setup_performance_data --yes
```

If it stopped after voter 23, the next run starts at voter 24 and creates 27
more. Nothing is queried from the database to work this out: manifest entry *N*
is voter *N*, which is validated on load, so the resume point is the manifest
length.

Elections already in the manifest are re-fetched and checked — correct organizer,
expected title, active, exactly the two expected candidates, exactly the 50
expected eligible voters — and skipped only if all of that holds. If any of it
does not, the run **stops** rather than creating a second election with the same
title that nobody can tell apart.

### Recovering an election the server committed after a timeout

`POST /elections/` is the slowest write in the system — it generates a 2048-bit
Paillier keypair, encrypts and stores it, and inserts 50 eligibility rows and 50
audit events in a single transaction. On a slow deployment that can outrun the
client timeout: **the client gives up, the server commits anyway**, and a real
election exists that no manifest records. A plain rerun would then create a
second election with the same title and no way to tell which one the load test
should use.

Two changes address that:

- **Setup uses a 120-second HTTP timeout** (up from 30). Only setup — verification
  and the load test keep the 30-second default.
- **Before creating each missing election, setup looks for one already committed
  under that exact title.** It queries the organizer's own
  `GET /elections/active?search=<title>` and then matches on the title
  **exactly**. The server-side `search` is an `ILIKE %…%`, i.e. a substring,
  case-insensitive filter, so it only narrows the list — `PERF-B-RUN-01` never
  recovers `PERF-B-RUN-010`, `perf-b-run-01` or `PERF-B-RUN-01-COPY`.

What happens next:

| Exact matches | Behaviour |
| --- | --- |
| 0 | Create the election normally. |
| 1 | Validate it in full, then adopt it — **no second POST**. |
| 2 or more | **Refuse**, write nothing, and tell you to resolve the duplicates or use a new `PERF_BATCH`. |

A recovered election is held to exactly the same standard as a created one. It is
re-read from the authoritative single-election routes (not trusted from the
search result) and must match on title, status, run number, organizer, ballot
type, `max_selections`, both expected candidates and the full set of 50 eligible
voters. Anything short of that raises and leaves the manifest untouched. Only
after it passes is it appended through the same atomic, secret-scanned writer,
and the run reports:

```
Recovered election 2/3 (PERF-<batch>-RUN-02, <id>) — it had already been
committed by the server, most likely after a client timeout. No new election
was created.
```

Ownership needs no separate check: for an organizer, `GET /elections/active`
already filters to elections they created.

The run also stops, rather than guessing, when:

- the manifest belongs to a different batch or a different base URL;
- the manifest entries are out of order or internally inconsistent;
- registration returns `400 Account already exists.` for an account that is *not*
  in the manifest. That response carries no `external_id`, and the public API
  offers no way to look one up, so the account cannot be recorded. Start a new
  `PERF_BATCH`.

## Verification

Read-only. Run it after setup, and again immediately before the load test:

```powershell
python -m performance_tests.verify_performance_data
```

It checks that:

- the manifest is schema-valid and belongs to this batch and base URL;
- there are exactly 50 voters, unique on username, email and external id;
- there are exactly 3 elections;
- each election is active, has the expected batch-specific title, uses a
  single-choice ballot with `max_selections == 1`, has exactly the two expected
  candidates, and ends in the future;
- each election's eligible-voter list is exactly the 50 manifest voters, with no
  extras;
- **every** voter has `voted_at == null`, i.e. the data set is unused.

Every check runs before the summary prints, so one run reports every problem
rather than only the first. The exit status is `0` when ready and `1` when not:

```
  [PASS] Manifest schema and batch/base-url match
  [PASS] Manifest holds 50 voters (expected 50)
  [FAIL] Election run 2 (…): status is active (got 'completed')

  NOT READY — 1 of 34 checks failed.
```

### `--check-logins`

Optionally verify all 50 voter passwords actually work:

```powershell
$env:PERF_VOTER_PASSWORD = "<the password used at setup>"
python -m performance_tests.verify_performance_data --check-logins
```

Off by default, because it is 50 extra requests and 50 bcrypt verifications
against staging — exactly the load the real test is meant to measure. Worth
running once after setup, then not again.

Note that `POST /auth/login` is the single non-GET request either verification
mode makes. It creates no records: it reads one user row and returns a token. The
read-only client blocks every other POST, and all PUT, PATCH and DELETE, before
the request leaves the process.

## Where the manifest goes

```
performance_tests/data/performance_manifest_<batch>.json
```

It holds the batch, base URL, organizer username and email, the 50 voters
(username, email, `external_id`), and the 3 elections (run number, election id,
title, status, dates, both candidate ids and names, and the `candidate_id` the
load test should use).

It never holds a voter or organizer password, a JWT, a database URL, or any
Render, Supabase or cryptographic secret. That is enforced, not just intended:
the manifest is walked before every write and the write is refused if a forbidden
key or a token-shaped value is present.

### Why it must not be committed

The manifest names real accounts on a real deployment — usernames, email
addresses, external ids and election ids that are valid credentials-adjacent
identifiers for a running system. It is per-run throwaway data with no value in
version control, and it is ignored by the repository `.gitignore`:

```gitignore
performance_tests/data/*
!performance_tests/data/.gitkeep
performance_tests/results/*
!performance_tests/results/.gitkeep
performance_tests/.env*
!performance_tests/.env.example
```

`data/` is ignored wholesale rather than by extension, because the atomic writer
also produces a transient `<manifest>.json.tmp` that an `*.json` rule would miss.
`data/.gitkeep` and `.env.example` stay trackable. If you ever need to share a
manifest, send it out of band — do not add it to a commit, and never `git add -f`
it.

---

# Load testing with Locust

**Setup and verification must both be complete and green first.** The load test
needs the election ids, candidate ids and 50 voter credentials that only exist
once setup has run, and a run against half-prepared data measures the wrong
thing. The sequence is always:

1. `setup_performance_data` — until it reports 50 voters and 3 elections.
2. `verify_performance_data` — until it prints `READY`.
3. Only then run Locust.

> **Operational status — Render run 1 is complete.**
> The synchronized 10-voter test on batch `FYPVOTE01` election run 1 finished with
> 10 accepted votes and 0 failures. **Render runs 2 and 3 are unused and must stay
> that way** until they are deliberately spent. Their manifest
> (`performance_manifest_FYPVOTE01.json`) and the CSVs under `results/` are the
> record of that run — do not modify or delete them.
>
> For a like-for-like local comparison, see
> [Local testing against 127.0.0.1](#local-testing-against-127001).

> **Operational status — the original prepared elections have expired.**
> The three elections from the original setup batch are past their end dates, so
> no vote test can run against them: the plan refuses an expired election before
> spawning, and `--vote-run-ready` reports it. Read testing is complete and
> unaffected. Replacement active elections must be created manually, the manifest
> regenerated, and the full verifier re-run before any vote test — see
> [Bringing up replacement elections](#bringing-up-replacement-elections). No
> election id or date is hardcoded anywhere in this package; everything is read
> from the manifest at run time.

## Installation

The performance tooling is **not** a backend dependency and must never be
installed into the deployed application environment. Its direct dependencies
live in a separate requirements file:

```powershell
python -m pip install -r performance_tests/requirements.txt
```

That installs `httpx` for setup, verification and preflight checks, plus Locust
and its gevent/requests stack for load generation. Until Locust is installed,
the Locust-binding unit test skips (everything else still runs).

## Environment variables

All the variables from the setup section still apply — `PERF_BASE_URL`,
`PERF_PRODUCTION_BASE_URL`, `PERF_BATCH`, `PERF_ORGANIZER_*` and, crucially,
`PERF_VOTER_PASSWORD`, which every virtual user logs in with. In addition:

| Variable | Required | Meaning |
| --- | --- | --- |
| `PERF_SCENARIO` | yes | `read` or `vote`, matched **exactly** |
| `PERF_MIN_WAIT_SECONDS` | no | Read think time floor, default `1` |
| `PERF_MAX_WAIT_SECONDS` | no | Read think time ceiling, default `3` |
| `PERF_VOTE_LOAD_ALLOWED` | vote only | Must be exactly lowercase `true` |
| `PERF_VOTE_ELECTION_RUN` | vote only | `1`, `2` or `3` — never defaulted |

`PERF_SCENARIO` is compared exactly: `Read`, `READ` and `"vote "` with a trailing
space are all rejected rather than guessed at. `PERF_SETUP_ALLOWED` is **not**
needed — the load test creates no accounts or elections.

## ⚠️ Vote runs are permanent

**A vote run permanently consumes each participating voter's single ballot for
the selected election.** The backend has no unvote endpoint, and this package has
no cleanup, reset or account-generation mode. Once voter 001 has voted in
election 1, that pairing is spent forever.

Consequences to plan around:

- **Never rerun a vote scenario against an election that has already been
  voted in.** Every voter that already voted returns
  `400 You have already voted in this election`, which is recorded as a
  **failure** — so the rerun measures nothing and its numbers are garbage.
- Each of the three elections is an independent budget. The same 50 voters can
  vote once in run 1, once in run 2 and once in run 3, which is exactly why three
  elections were prepared: **three clean measurements, one prepared data set.**
- Read runs are unlimited and repeatable. Only vote runs are consumed.

Run `verify_performance_data` first: it fails if any voter already has a
non-null `voted_at`, which is the check that catches an accidental second run
*before* Locust starts.

## Read scenario

Fifty prepared voters, each claimed by exactly one virtual user, each logging in
once and then issuing authenticated reads with a 1–3 second think time.

### Smoke test — 1 user, 30 seconds

```powershell
$env:PERF_SCENARIO = "read"
locust -f performance_tests/locustfile.py `
    --headless --users 1 --spawn-rate 1 --run-time 30s `
    --csv performance_tests/results/read_smoke
```

### The three commissioned read runs

```powershell
# 10 concurrent readers, 3 minutes
locust -f performance_tests/locustfile.py `
    --headless --users 10 --spawn-rate 2 --run-time 3m `
    --csv performance_tests/results/read_10

# 25 concurrent readers, 3 minutes
locust -f performance_tests/locustfile.py `
    --headless --users 25 --spawn-rate 5 --run-time 3m `
    --csv performance_tests/results/read_25

# 50 concurrent readers, 3 minutes — the full prepared pool
locust -f performance_tests/locustfile.py `
    --headless --users 50 --spawn-rate 5 --run-time 3m `
    --csv performance_tests/results/read_50
```

More than 50 users is refused: there are only 50 prepared voters and a voter is
never shared between two concurrent users.

The read tasks, by weight, are all real routes taken from the backend:

| Weight | Request | Route |
| --- | --- | --- |
| 4 | `GET /elections/active` | voter's eligible active elections |
| 3 | `GET /elections/[id]` | one election's details |
| 2 | `GET /votes/history` (+ `GET /votes/[id]` when non-empty) | the voter's ballots |
| 1 | `GET /elections/history` | past elections |
| 1 | `GET /users/me` | profile |

Request names are **normalised** — `GET /elections/[id]`, not the raw URL — so
three election ids aggregate into one statistics row instead of fragmenting the
metrics into single-sample buckets.

The read scenario deliberately never calls `GET /results/elections/{id}`. That
endpoint is the backend's *only* trigger for finalization: against an election
whose deadline has passed it runs the homomorphic tally and flips the status to
`completed`. That is a mutation, not a read, and it has no place in a read load
test.

## Vote scenario — synchronized

### Why there is a barrier

The vote test exists to measure **concurrent `POST /votes/` processing** — Paillier
encryption under the election row lock. If voters simply voted as they spawned,
the numbers would be dominated by staggered logins and bcrypt verification. That
is authentication congestion, and it is not the thing being measured.

So preparation and voting are separated:

1. Voters spawn **gradually** (`--spawn-rate 0.2`).
2. Each claims a unique prepared voter account.
3. Each logs in.
4. Each runs its read-only readiness checks.
5. Each then **waits at a barrier**.
6. The barrier releases only when **every** expected voter is ready.
7. All the ballots are submitted together.
8. Each voter attempts exactly one vote, then stops.

### All-or-nothing preparation

**If any voter fails any preparation step, the whole run is abandoned and no
ballot is sent at all.** A failed login, an ineligible voter, a voter who has
already voted, a malformed response, or the readiness timeout expiring — each
aborts the coordinator, which wakes every waiting voter and refuses to let any of
them vote.

This matters because ballots are irreversible. A partial run would spend real
votes while measuring a concurrency level that was never actually reached — the
worst of both outcomes. Better to abort, fix the cause, and get a clean run.

### Fixed run/cohort pairing

| Election run | Voters | `--users` |
| --- | --- | --- |
| 1 | 10 | `--users 10` |
| 2 | 25 | `--users 25` |
| 3 | 50 | `--users 50` |

A mismatch is **refused before users spawn**. `PERF_VOTE_ELECTION_RUN=1` with
`--users 50` stops with an error rather than spending forty extra ballots at a
concurrency the experiment never called for.

### Readiness checks

Before a voter is allowed to wait at the barrier, two authenticated read-only
requests must succeed — both of which the voter may make on its own behalf, so no
organizer session is involved inside the load test:

| Request | Establishes |
| --- | --- |
| `GET /elections/{id}` | The election exists (404 otherwise) and **this voter is eligible** — the route answers 403 to a voter with no eligibility row. The body then supplies status, start/end dates, ballot type, `max_selections` and candidates, all checked against the manifest. |
| `GET /votes/history` | Whether this voter has **already voted** in the selected election. A ballot in one of the *other* two runs is fine and does not block. |

`GET /results/elections/{id}` is never called — it is the only trigger for
finalization and would tally and close the election.

### ⚠️ Irreversible, once only

**Each vote run permanently consumes one ballot per participating voter for that
election, and must never be repeated against the same election.** There is no
unvote endpoint and no cleanup mode. A repeat run returns
`400 You have already voted in this election` for every voter — recorded as a
**failure** — so it measures nothing and destroys the comparison.

### Commands

Gradual authentication, simultaneous release. Run these **one at a time**,
checking results in between, and run the selected-election verifier immediately
before each one.

```powershell
$env:PERF_SCENARIO = "vote"
$env:PERF_VOTE_LOAD_ALLOWED = "true"
$env:PERF_VOTE_READY_TIMEOUT_SECONDS = "600"

# ── Election run 1 — 10 voters ────────────────────────────────────────────
$env:PERF_VOTE_ELECTION_RUN = "1"
python -m performance_tests.verify_performance_data --vote-run-ready 1
locust -f performance_tests/locustfile.py `
    --headless --users 10 --spawn-rate 0.2 --run-time 3m `
    --csv performance_tests/results/vote_run1_10

# ── Election run 2 — 25 voters ────────────────────────────────────────────
$env:PERF_VOTE_ELECTION_RUN = "2"
python -m performance_tests.verify_performance_data --vote-run-ready 2
locust -f performance_tests/locustfile.py `
    --headless --users 25 --spawn-rate 0.2 --run-time 5m `
    --csv performance_tests/results/vote_run2_25

# ── Election run 3 — 50 voters ────────────────────────────────────────────
$env:PERF_VOTE_ELECTION_RUN = "3"
python -m performance_tests.verify_performance_data --vote-run-ready 3
locust -f performance_tests/locustfile.py `
    --headless --users 50 --spawn-rate 0.2 --run-time 8m `
    --csv performance_tests/results/vote_run3_50
```

`--spawn-rate 0.2` is one new voter every five seconds, so 50 voters take about
250 seconds just to spawn. The run times above leave room for that plus each
voter's login and readiness reads, and then the synchronized ballots. `--run-time`
is an upper bound — the run ends as soon as the last ballot is in.

`PERF_VOTE_READY_TIMEOUT_SECONDS` (default `600`) is how long a prepared voter
holds at the barrier before the run is abandoned. It must comfortably exceed the
spawn time of the largest cohort; the default leaves a wide margin over the 250
seconds run 3 needs. It is validated as a positive number.

### Single-process only

Vote runs are refused in distributed or multi-process mode:

- `--master` — refused
- `--worker` — refused
- `--processes` other than 1 — refused

Each process would build its own voter pool and its own barrier, so two processes
would allocate the same voters twice and release two independent half-cohorts.
The result would be duplicate-vote failures and a concurrency level that never
happened. The read scenario is unaffected by this restriction.

### End-of-run summary

At test stop the coordinator prints non-secret tallies — no receipts, no tokens:

```
  Expected voters: 10
  Prepared voters: 10
  Vote attempts:   10
  Accepted votes:  10
  Failed votes:    0
  Aborted:         no
```

Locust's own CSV remains the source for timing percentiles.

A vote is attempted **once**. The attempt is marked before the request is sent,
so a timeout or a connection error is never retried — the server may already have
recorded the ballot, and a retry would either double-count or produce a
misleading duplicate-vote failure.

## Selected-election verification

The full `verify_performance_data` check covers all three elections and every
voter, so it correctly reports `NOT READY` the moment run 1 has been voted in —
even though runs 2 and 3 are still pristine and perfectly testable.

Use the narrower mode before each vote test:

```powershell
python -m performance_tests.verify_performance_data --vote-run-ready 2
```

It checks only the requested election: correct manifest and deployment, election
active and unexpired and already started, the expected 50 eligible voters still
attached, none of them having voted **in that run**, and the expected
ballot/candidate configuration. Ballots in the other runs do not make it fail.

It is read-only and checks strictly less than the full mode — it does not replace
it. Run the full verifier once after setup, then this one before each vote test.

## Local testing against 127.0.0.1

The same scripts can drive a backend running on your own machine, so a local
result can be compared against the Render `FYPVOTE01` numbers. This is off by
default and narrowly gated.

### The rule

`PERF_LOCAL_TEST_ALLOWED` must be exactly `true` (lowercase). `TRUE`, `1`, `yes`
and `true ` are **errors**, not a silent "off" — a user who typed `TRUE` believes
local mode is armed, so saying nothing would be the worst outcome.

| Flag | `PERF_BASE_URL` must be |
| --- | --- |
| unset / `false` | HTTPS **and** a hostname containing `staging` or `performance` |
| `true` | a **loopback** target only — `localhost`, `127.0.0.0/8` or `[::1]`, over http or https |

Local mode does not widen what is reachable; it swaps one narrow rule for
another. In local mode a public target is refused **even over HTTPS**, so a run
armed for local testing can never quietly reach staging.

Refused in local mode: `0.0.0.0`, `192.168.x.x`, `10.x.x.x`, `172.16.x.x`, public
IPs, external hostnames, `localhost.example.com` and `notlocalhost` (loopback is
established by exact identity, never substring matching), URLs embedding
`user:pass@`, malformed or out-of-range ports, and any URL whose *path or query*
merely mentions localhost.

Unchanged in both modes: `PERF_PRODUCTION_BASE_URL` is required, a target that
normalizes to it is refused, malformed URLs and invalid ports are refused, and
Locust's `--host` must equal the validated `PERF_BASE_URL`.

Arming local mode arms **nothing else**. `PERF_SETUP_ALLOWED=true` is still
required to create accounts and elections; `PERF_VOTE_LOAD_ALLOWED=true` is still
required to vote; the synchronized barrier, the 10/25/50 run mapping and the
single-process restriction all apply exactly as they do against Render.

### Terminal 1 — the local backend

Run the **same backend commit** you deployed to Render, bound to loopback only.

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- `--host 127.0.0.1` binds to loopback only. **Do not use `0.0.0.0`** — that
  exposes the server to your whole network, and the perf scripts refuse it as a
  target anyway.
- **Do not pass `--reload`.** The reloader adds a file watcher and process
  supervision that distort timings. The repo's own docs use `--reload` for
  development; a performance run must not.
- The backend reads its configuration from `backend/.env`, which already exists
  and **must not be edited**. Before starting, confirm out of band that
  `DATABASE_URL` points at the **testing** Supabase database and never
  production, and that `JWT_SECRET`, `KEYSTORE_MASTER_SECRET` and
  `RECEIPT_SIGNING_SECRET` are set (the app refuses to start otherwise). No real
  URL or secret belongs in this file or in any command you paste.
- Paillier is 2048-bit in `backend/app/security/homomorphic.py` and is not
  configurable, so the local run uses the same cryptographic cost as Render by
  construction.

Check it is up by opening `http://127.0.0.1:8000/health/db` in a browser.

### Terminal 2 — the performance scripts

```powershell
# From the repository root
.\backend\venv\Scripts\Activate.ps1

$env:PERF_BASE_URL            = "http://127.0.0.1:8000"
$env:PERF_PRODUCTION_BASE_URL = "https://<real-production-backend>"
$env:PERF_LOCAL_TEST_ALLOWED  = "true"
$env:PERF_BATCH               = "FYPLOCAL01"
$env:PERF_ELECTION_DURATION_HOURS = "168"
$env:PERF_SETUP_ALLOWED       = "true"

# Passwords are typed in, never committed and never written to a file.
$env:PERF_ORGANIZER_PASSWORD = Read-Host "Organizer password" -AsSecureString `
    | ForEach-Object { [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) }
$env:PERF_VOTER_PASSWORD     = Read-Host "Voter password" -AsSecureString `
    | ForEach-Object { [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) }
```

`PERF_ELECTION_DURATION_HOURS = 168` gives the local elections a week, so they do
not expire mid-experiment the way the first Render batch did.

### Create and verify the local batch

```powershell
python -m performance_tests.setup_performance_data
$env:PERF_SETUP_ALLOWED = "false"

python -m performance_tests.verify_performance_data --check-logins
python -m performance_tests.verify_performance_data --vote-run-ready 1
```

Disarming `PERF_SETUP_ALLOWED` immediately after setup means the rest of the
session cannot create anything else by accident.

### The local synchronized 10-voter run

> **⚠️ Irreversible. Run once, and do not run it while reading this.**
> It casts 10 permanent ballots into local election run 1. There is no unvote
> endpoint and no cleanup mode. A repeat returns
> `400 You have already voted in this election` for every voter.

```powershell
$env:PERF_SCENARIO = "vote"
$env:PERF_VOTE_LOAD_ALLOWED = "true"
$env:PERF_VOTE_ELECTION_RUN = "1"
$env:PERF_VOTE_READY_TIMEOUT_SECONDS = "600"

python -m locust -f performance_tests/locustfile.py `
    --headless --users 10 --spawn-rate 0.2 --run-time 3m `
    --exit-code-on-error 1 `
    --csv performance_tests/results/vote_FYPLOCAL01_run1_10
```

Same shape as the Render run: 10 synchronized voters, `0.2 users/second`
authentication ramp, two-candidate single-choice election, 2048-bit Paillier.

### Comparing with Render

Compare **only** these three figures from `POST /votes/`, against the Render
`FYPVOTE01` run 1 baseline:

| Metric | Render `FYPVOTE01` run 1 |
| --- | --- |
| `POST /votes/` p50 | ≈ 15 s |
| `POST /votes/` p95 | ≈ 16 s |
| Failure rate | 0 % (10 accepted, 0 failed) |

Nothing else is comparable. Request counts, RPS, the read-scenario rows and any
timing that includes login all reflect different hardware, a different network
path and a different ramp, and reading them side by side would mislead. The
local run has no Render network hop and no cold-start behaviour, so a large p50
difference is an expected property of the environment, not a regression.

### Manifest separation

A local batch stores its normalized loopback URL (`http://127.0.0.1:8000`) in its
manifest, and the manifest's `base_url` is checked against the validated target on
every load. A Render command therefore cannot use a local manifest and a local
command cannot use the Render manifest — even if both are given the same
`PERF_BATCH`, the run stops with "Refusing to mix data from two deployments".
Use a distinct batch anyway (`FYPLOCAL01`), which keeps them in separate files.

## Bringing up replacement elections

The vote tests need three **active** elections with future end dates. Once the
replacements exist, follow this sequence exactly. Steps 5, 7 and 9 are each
irreversible and each may be performed **once**.

1. **Create three replacement active elections** with future end dates, two
   candidates each and the same 50 eligible voters. Do this deliberately — the
   setup script creates a whole new batch, which is one way, but any route that
   produces the same shape is fine.
2. **Update or regenerate the manifest** so it carries the replacement election
   ids and candidate ids. The manifest is the single source of truth for the load
   test; nothing is hardcoded.
3. **Run the full verifier** and wait for `READY`:
   ```powershell
   python -m performance_tests.verify_performance_data
   ```
4. `python -m performance_tests.verify_performance_data --vote-run-ready 1`
5. **Synchronized 10-voter test on run 1** (irreversible — once only).
6. `python -m performance_tests.verify_performance_data --vote-run-ready 2`
7. **Synchronized 25-voter test on run 2** (irreversible — once only).
8. `python -m performance_tests.verify_performance_data --vote-run-ready 3`
9. **Synchronized 50-voter test on run 3** (irreversible — once only).

After step 5 the full verifier will report `NOT READY` — that is expected and
correct, because run 1 has been consumed. From that point on use
`--vote-run-ready N`, which is why it exists.

The exact Locust commands for steps 5, 7 and 9 are in
[Vote scenario — synchronized](#commands) above.

## Results

CSV output goes to `performance_tests/results/` via `--csv <prefix>`, producing
`<prefix>_stats.csv`, `<prefix>_failures.csv`, `<prefix>_stats_history.csv` and
`<prefix>_exceptions.csv`. The whole directory is gitignored apart from
`.gitkeep` — results reference real staging accounts and are not committed.

### Reading the metrics

| Metric | Locust column | What it tells you |
| --- | --- | --- |
| **Request count** | `Request Count` | Total requests for that name. Your sample size — a percentile over a handful of requests means nothing. |
| **Failure count / rate** | `Failure Count`, `Failure Count/Request Count` | How many requests were rejected or malformed. **For a vote run this should be 0.** Anything above 0 means ballots were lost, rejected or duplicated, and the run's timings describe a broken interaction rather than a healthy one. |
| **Median (50th percentile)** | `Median Response Time` | The typical experience. Robust to a few slow outliers, so this is the number to quote for "how fast does it feel". |
| **95th percentile** | `95%` | 19 of 20 requests were at least this fast. This is where queuing and lock contention show up first — on the vote path especially, since each ballot does Paillier encryption under an election row lock. A p95 far above the median means the system is fine *most* of the time and badly degraded for a tail of users. |
| **Requests per second** | `Requests/s` | Achieved throughput. Compare against the offered load: if RPS plateaus while users increase and p95 climbs, you have found the saturation point. |

Read the failure count **first**. Timings from a run with failures are not a
measurement of the system working — they are a measurement of it refusing.

For the vote runs specifically, expect the median to be materially higher than
the read runs: every ballot performs homomorphic encryption and takes a shared
lock on the election row. That is the interesting result, not a defect.

## Target safety

Locust's `--host` cannot be used to slip past the guards. At start-up the
locustfile:

1. resolves `PERF_SCENARIO` (exact match) and refuses anything else;
2. loads `PERF_BASE_URL` and `PERF_PRODUCTION_BASE_URL` and applies the same
   validation the setup script uses — HTTPS, production supplied, the two
   different once normalised, and the staging host named `staging`/`performance`;
3. requires `--host` (or `LOCUST_HOST`), if given at all, to normalise to exactly
   the validated `PERF_BASE_URL` — otherwise it refuses. If no host is given, it
   pins Locust to the validated target itself;
4. loads and strictly validates the manifest — 50 voters, 3 elections;
5. for the vote scenario, requires `PERF_VOTE_LOAD_ALLOWED=true` and a run of
   1/2/3, and refuses an election that is missing, not active, expired or wrongly
   configured;
6. re-reads the target election from the live API before users spawn, through the
   **read-only** client, so an election that has been completed since setup is
   caught.

All of that happens before a single virtual user is spawned. Any failure prints
an error and exits non-zero.

## Tests

```powershell
python -m pytest performance_tests/tests -q
```

The tests are fully mocked. The setup/verification tests drive an
`httpx.MockTransport`, and an autouse fixture makes constructing a client without
one an immediate error. The load-test tests drive `FakeLocustClient`, an
in-memory stand-in for Locust's `HttpSession` with no transport at all. Nothing
here can reach localhost, Render, Supabase or any other host, and no test reads a
real environment variable or `.env` file.

`load_plan.py` imports neither `locust` nor `requests` — asserted by a test —
which is what keeps the suite runnable and offline whether or not Locust is
installed. One test (`test_locustfile_imports_and_defines_one_user_class`) skips
until you install `performance_tests/requirements.txt`.

## Layout

```
performance_tests/
    __init__.py
    common.py                     configuration, guards, payloads, manifest I/O
    setup_performance_data.py     creates the data (guarded, resumable)
    verify_performance_data.py    read-only readiness check
    load_plan.py                  scenarios, voter pool, request behaviour
    locustfile.py                 thin Locust adapter over load_plan
    requirements.txt              pinned performance-tooling dependencies
    .env.example                  annotated template, placeholders only
    README.md
    data/.gitkeep                 generated manifests land here, ignored by git
    results/.gitkeep              Locust CSV output lands here, ignored by git
    tests/
        conftest.py               mock API, no-network guard
        test_setup_performance_data.py
        test_verify_performance_data.py
        test_locustfile.py        load plan + virtual-user behaviour
```

The load test is split in two on purpose. `load_plan.py` holds all the logic and
imports no Locust, so every behaviour — target safety, voter allocation, login,
reads, the single-vote rule — is unit-tested without Locust installed and with
nothing in the import graph that can open a socket. `locustfile.py` is the
adapter: it resolves the plan, validates `--host`, and defines the one `HttpUser`
class the chosen scenario needs.

Values mirrored from the backend — the SGT offset, the 8-character password
minimum, the 50-character group limit — are duplicated in `common.py` rather than
imported, because these scripts drive a *deployed* API that may be running a
different revision than your working tree. They are marked as mirrors where they
are defined.

One detail worth knowing if you change the election payloads: the backend stores
`start_date` and `end_date` as **naive** Singapore time and compares them against
a naive `now_sgt()` (`backend/app/core/time.py`). Sending an offset-aware
timestamp such as `...+08:00` makes the vote route compare an aware datetime
against a naive one, which fails at request time. `common.format_sgt` exists to
keep that from happening.
