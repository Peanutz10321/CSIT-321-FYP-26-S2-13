# Dependencies, Configuration and Auditing

## Dependency files

| File | Role |
|---|---|
| `requirements.in` | Production **source of truth** — direct dependencies only |
| `requirements.txt` | **Generated.** Fully pinned production set. Do not edit by hand |
| `requirements-dev.in` | Test and audit tooling — direct only |
| `requirements-dev.txt` | **Generated.** Fully pinned dev set |

`requirements-dev.in` constrains itself with `-c requirements.txt`, so the two
files can never resolve the same package to different versions.

Every generated line carries a `# via` annotation naming what pulled it in.
`# via -r requirements.in` marks a direct dependency; anything else is transitive.

### Regenerating the pins

```bash
cd backend
pip install pip-tools                       # once
pip-compile --strip-extras requirements.in
pip-compile --strip-extras requirements-dev.in
```

Regenerate only when `*.in` changes. `pip-compile` does not upgrade pins unless
asked, so a routine run is a no-op. To deliberately move a package:

```bash
pip-compile --strip-extras --upgrade-package fastapi requirements.in
```

Avoid bare `--upgrade`: it moves everything at once and makes a failure hard to
attribute.

### Installing

```bash
pip install -r requirements.txt                        # deployment
pip install -r requirements.txt -r requirements-dev.txt  # development and CI
```

## Auditing

### Backend

```bash
cd backend
pip-audit -r requirements.txt --strict
```

Audits what actually ships. The dev file is excluded on purpose: test and audit
tooling is not deployed, and including it would report findings that cannot
affect the running service.

**One finding is currently suppressed in CI**, with reasoning:

| Advisory | Package | Type | Fix | Why suppressed |
|---|---|---|---|---|
| `PYSEC-2026-1325` / `CVE-2024-23342` | `ecdsa` 0.19.2 | **Transitive** (via `python-jose`) | **None published** | Minerva timing attack on ECDSA signing, key generation and ECDH. This API signs JWTs with **HS256** (HMAC) and has no ECDSA code path, so the affected routines are never reached. Upstream considers side-channel resistance out of scope, so there is nothing to upgrade to. |

That suppression rests on the algorithm staying HMAC, and this is now **enforced,
not merely assumed**: `JWT_ALGORITHM` in `app/config.py` is typed
`Literal["HS256"]`, so the application refuses to start with any EC/RSA (or other)
algorithm. The ecdsa code path in `python-jose` is therefore unreachable by
configuration. If that pin is ever widened to allow an `ES*`/`RS*` algorithm, the
vulnerable path becomes reachable and the `--ignore-vuln` must be removed from CI;
`tests/test_cors_config.py` pins the HS256-only rule so a widening cannot pass
review silently.

Suppressions are listed explicitly on the command line rather than by lowering
the severity threshold, so adding one is visible in review.

### Frontend

```bash
cd frontend
npm audit                      # everything, unfiltered
npm run audit                  # the CI gate: better-npm-audit at --level high
```

The lockfile is committed and `npm ci` installs from it exactly. Remediation is
never automatic: `npm audit fix` can change resolved versions across the tree, so
findings are triaged and fixed as their own reviewed change.

The CI gate runs `better-npm-audit audit --level high` (via the `audit` npm
script) rather than `npm audit --audit-level=high` directly. This is identical in
effect except that a single advisory can be suppressed with a written
justification in `frontend/.nsprc`, instead of lowering the severity threshold or
ignoring the whole report. Plain `npm audit` stays unfiltered, so the suppression
is visible and scoped to exactly one advisory ID.

**One finding is currently suppressed**, with reasoning:

| Advisory | Package | Fix | Why suppressed |
|---|---|---|---|
| `GHSA-qwww-vcr4-c8h2` | `react-router` (via `react-router-dom` 7.18.1) | None applicable | RSC-Mode CSRF bypass. This frontend is a Vite single-page app and does **not** use React Server Components, so the vulnerable RSC action path is unreachable. |

`react-router-dom` is pinned to **7.18.1 exactly**. No `react-router-dom` 7.x
release is free of a high advisory: `<= 7.17.0` carries a larger cluster —
including an unauthenticated RCE and open-redirect/XSS reachable from
`<Link>`/`useNavigate` in an ordinary SPA — while `7.12.0 – 8.2.0` carries only
the RSC-Mode advisory above, which does not apply here. `7.18.1` is therefore the
safest available pin: it escapes the entire earlier cluster and leaves a single
advisory that is unreachable by this app's architecture. The suppression expires
on **2026-08-31** and must then be re-reviewed. Remove it when a supported fixed
7.x release ships, or replace it as part of a planned, tested migration to v8.

With that one suppression in place, `npm run audit` reports no findings at the
`high` level; the backend `pip-audit` is likewise clean apart from the documented
`ecdsa` suppression above.

## Runtime configuration

Copy the templates and fill them in:

```bash
cp backend/.env.example backend/.env
cp backend/.env.test.example backend/.env.test
cp frontend/.env.example frontend/.env.local
```

### Backend

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Use a direct/session connection for migrations |
| `JWT_SECRET` | yes | |
| `JWT_ALGORITHM` | no | Pinned to `HS256`; any other value is rejected at startup — see the audit note above |
| `KEYSTORE_MASTER_SECRET` | yes | Fernet key for election private keys |
| `RECEIPT_SIGNING_SECRET` | yes | ≥32 UTF-8 bytes, must differ from the two above |
| `ENVIRONMENT` | no | One of `development`, `test`, `production` (case/whitespace-normalised). Any other value is rejected at startup; only `production` enables stricter checks |
| `CORS_ALLOWED_ORIGINS` | in production | Comma-separated origins |

`ENVIRONMENT` is a **closed set**: `development`, `test` or `production`, matched
after trimming and lower-casing (so `" Production "` is accepted). An unknown
value — including a near-miss typo like `prodution` — is refused at startup rather
than silently treated as development. This closes a fail-open gap where a
mistyped `production` would quietly run with development's looser CORS rules.

### CORS

`CORS_ALLOWED_ORIGINS` is a comma-separated list of `scheme://host[:port]`
entries. Trailing slashes are stripped, duplicates collapsed, surrounding
whitespace ignored. A malformed entry rejects the whole list at startup rather
than being dropped.

Each entry must be a bare origin and nothing more. Validation is strict:

- scheme must be `http` or `https`;
- the host must be a valid hostname or IP literal (IPv6 in brackets, e.g.
  `http://[::1]:8000`);
- an explicit port must be numeric and in `1–65535`;
- **no** embedded credentials (`https://user:pass@host`), **no** path, query,
  parameters or fragment, and **no** internal whitespace or control characters.

So `https://vote.example.edu` and `http://localhost:5173` are accepted, while
`https://user:pass@example.com`, `https://example.com:bad`, `https://example.com/app`
and `https://exa mple.com` are each rejected — and because one bad entry fails the
whole list, a malformed origin can never be silently skipped.

```bash
# development
CORS_ALLOWED_ORIGINS=http://localhost:5173

# production
CORS_ALLOWED_ORIGINS=https://vote.example.edu,https://admin.example.edu
```

**Production must use explicit HTTPS origins and must never use `*`.** With
`ENVIRONMENT=production` the application refuses to start if an origin uses
plain HTTP, if the wildcard is configured, or if no origin is configured at all
— a silent empty list would block the frontend with no explanation. HTTP
origins remain available only outside production for local development.

An unset value outside production means *no* cross-origin access, not an
implicit wildcard.

`allow_credentials` is switched off automatically when the wildcard is used. The
CORS specification forbids `Access-Control-Allow-Origin: *` on credentialed
requests and browsers reject the response, so sending both is not merely
insecure — it silently breaks authenticated cross-origin calls.

### Frontend

`VITE_API_BASE_URL` is the backend base URL. Vite inlines it at **build** time,
so a bundle carries the value present when it was built.

```bash
# local development — falls back to http://localhost:8000 when unset
npm run dev

# production — the variable is REQUIRED and must be https
VITE_API_BASE_URL=https://api.example.edu npm run build
```

The value is validated by a single rule — `validateApiBaseUrl()` in
`src/utils/apiConfig.js` — shared by both the runtime resolver and the Vite build
guard, so the two cannot disagree on what is valid. A value must be an absolute
`http`/`https` URL with an optional base path and **nothing else**: no other
scheme (blocking `javascript:`/`ftp:`/`file:`), no embedded credentials, no query
string or fragment, and no malformed or out-of-range port. In a **production**
build it must additionally be `https`.

A production build with a missing, blank, malformed, or plain-`http` value **fails
the build** — `vite.config.js` throws during config load, so the build aborts
before any bundle is produced. (It does *not* emit a bundle that throws at
runtime; the mistake surfaces in CI or at deploy time, never as a broken page in a
browser.) The error names `VITE_API_BASE_URL` and gives an example, e.g.:

```
VITE_API_BASE_URL must use https in a production build, got "http://api.example.edu". …
```

Development keeps the `http://localhost:8000` fallback when the value is unset or
blank, but a value that *is* provided is still validated in either mode — a
malformed value is a mistake, not a reason to silently fall back. Trailing slashes
are normalised, so `https://api.example.edu/` and `https://api.example.edu` behave
identically.

All request URLs are built through `buildApiUrl()` in `src/utils/apiConfig.js`;
no component constructs a backend URL of its own.
