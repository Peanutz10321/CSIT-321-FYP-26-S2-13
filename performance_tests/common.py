"""Shared configuration, safety guards, payload builders and manifest handling.

Both scripts in this package import from here so that a guard can only ever be
weakened in one place. Nothing in this module performs I/O against the API on its
own: it builds the client and validates the target, and the callers decide what to
send. That separation is what makes the "no mutating request before the guards
pass" property testable without a network.

Values mirrored from the backend are marked as such. They are duplicated rather
than imported because this package deliberately does not depend on ``backend.app``
— it drives the deployed HTTP API, which may be running a different revision than
the working tree.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

import httpx


# ── Shape of the data set ─────────────────────────────────────────────────────

VOTER_COUNT = 50
ELECTION_COUNT = 3
CANDIDATE_NAMES: tuple[str, ...] = (
    "Performance Candidate A",
    "Performance Candidate B",
)
BALLOT_TYPE = "single"
MAX_SELECTIONS = 1
SCHEMA_VERSION = 1

ELECTION_DESCRIPTION = (
    "Automated performance-test election. Generated data — not a real vote."
)

# Mirrors backend/app/security/password.py; checked locally so a short password
# fails before the first request rather than as a 422 on voter 001.
PASSWORD_MIN_LENGTH = 8
# Mirrors backend/app/models/user.py.
GROUP_MAX_LENGTH = 50

# Mirrors backend/app/core/time.py. The backend stores start_date/end_date as
# NAIVE Singapore time and compares them against a naive now_sgt(), so payloads
# must carry no UTC offset — an offset-aware value would make the vote route
# compare aware against naive and fail at request time.
SGT_OFFSET = timedelta(hours=8)

# The election is created already open, so voting can start immediately.
START_BACKDATE = timedelta(minutes=5)
DEFAULT_DURATION_HOURS = 24

# Endpoint paths, taken from the routers in backend/app/routes/.
HEALTH_PATH = "/health/db"
LOGIN_PATH = "/auth/login"
REGISTER_PATH = "/auth/register"
ELECTIONS_PATH = "/elections/"
ACTIVE_ELECTIONS_PATH = "/elections/active"

# Setup uses a longer timeout than the 30s default. Creating an election is the
# slowest write in the system: the route generates a 2048-bit Paillier keypair,
# encrypts and stores it, then inserts 50 eligibility rows and 50 audit events,
# all in one transaction. At 30s the client gave up while the server went on to
# commit successfully, leaving a real election that no manifest recorded.
SETUP_TIMEOUT_SECONDS = 120.0


# ── Environment variable names ────────────────────────────────────────────────

ENV_BASE_URL = "PERF_BASE_URL"
ENV_PRODUCTION_BASE_URL = "PERF_PRODUCTION_BASE_URL"
ENV_SETUP_ALLOWED = "PERF_SETUP_ALLOWED"
ENV_BATCH = "PERF_BATCH"
ENV_ORGANIZER_EMAIL = "PERF_ORGANIZER_EMAIL"
ENV_ORGANIZER_USERNAME = "PERF_ORGANIZER_USERNAME"
ENV_ORGANIZER_PASSWORD = "PERF_ORGANIZER_PASSWORD"
ENV_VOTER_PASSWORD = "PERF_VOTER_PASSWORD"
ENV_ELECTION_DURATION_HOURS = "PERF_ELECTION_DURATION_HOURS"
# Arms loopback-only local testing. Off unless it is exactly "true"; see
# parse_local_test_allowed and validate_target.
ENV_LOCAL_TEST_ALLOWED = "PERF_LOCAL_TEST_ALLOWED"

# A staging target has to say so in its own name. Substring matching on the host
# (and, as a fallback, the whole URL) is crude, but it is the check that makes
# "I exported the wrong variable" fail closed instead of writing 50 accounts into
# the wrong deployment.
STAGING_TOKENS = ("staging", "performance")


# ── Errors ────────────────────────────────────────────────────────────────────


class PerfError(RuntimeError):
    """Base class for every failure this package raises deliberately."""


class ConfigError(PerfError):
    """Configuration is missing, malformed or unusable."""


class SafetyError(PerfError):
    """A safety guard refused the run. No mutating request has been made."""


class ManifestError(PerfError):
    """The manifest is missing, inconsistent, or belongs to another run."""


class ApiError(PerfError):
    """The API answered in a way the script will not guess its way past."""


class ReadOnlyViolationError(PerfError):
    """A read-only client was asked to make a mutating request."""


# ── Time ──────────────────────────────────────────────────────────────────────


def now_sgt() -> datetime:
    """Naive Singapore time, matching backend/app/core/time.py exactly.

    The backend computes ``datetime.utcnow() + 8h``. This is the same instant
    without the deprecated call, and it deliberately stays naive.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None) + SGT_OFFSET


def format_sgt(value: datetime) -> str:
    """Serialize a naive SGT datetime the way the API expects to receive it.

    Seconds resolution, no trailing offset. Pydantic parses this back to a naive
    ``datetime``, which is what the election and vote routes compare against.
    """
    if value.tzinfo is not None:
        raise ConfigError(
            "Election timestamps must be naive Singapore time; got an "
            "offset-aware datetime, which the backend cannot compare."
        )
    return value.replace(microsecond=0).isoformat()


def parse_api_datetime(value: str) -> datetime:
    """Parse a datetime returned by the API back into a naive SGT datetime.

    Responses echo whatever was stored, which is naive. A value that does arrive
    with an offset is normalised to naive SGT so a comparison never mixes the two.
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None) + SGT_OFFSET
    return parsed


def default_batch(clock: datetime | None = None) -> str:
    """A timestamp-derived batch identifier.

    Alphanumeric only, because the batch is embedded in usernames and email
    addresses. Note that this changes every minute: a run that needs to *resume*
    must pass the original batch explicitly (see README.md).
    """
    moment = clock or now_sgt()
    return moment.strftime("%Y%m%d%H%M")


# ── Naming ────────────────────────────────────────────────────────────────────

_BATCH_PATTERN = re.compile(r"^[A-Za-z0-9]{1,24}$")


def validate_batch(batch: str) -> str:
    """Batch identifiers end up inside emails and usernames, so keep them plain."""
    batch = (batch or "").strip()
    if not _BATCH_PATTERN.match(batch):
        raise ConfigError(
            f"{ENV_BATCH} must be 1-24 alphanumeric characters (no punctuation, "
            f"spaces or underscores); got {batch!r}"
        )
    return batch


def voter_username(index: int, batch: str) -> str:
    """``perf_voter_001_<batch>`` … ``perf_voter_050_<batch>`` (1-based index)."""
    return f"perf_voter_{index:03d}_{batch}"


def voter_email(index: int, batch: str) -> str:
    return f"{voter_username(index, batch)}@test.com"


def voter_group(batch: str) -> str:
    group = f"PERFORMANCE-TEST-USERS-{batch}"
    if len(group) > GROUP_MAX_LENGTH:
        raise ConfigError(
            f"Group name {group!r} is {len(group)} characters, over the backend's "
            f"{GROUP_MAX_LENGTH}-character limit. Use a shorter {ENV_BATCH}."
        )
    return group


def election_title(batch: str, run: int) -> str:
    return f"PERF-{batch}-RUN-{run:02d}"


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PerfConfig:
    base_url: str
    production_base_url: str
    setup_allowed: str | None
    batch: str
    organizer_email: str
    organizer_username: str
    organizer_password: str
    voter_password: str | None
    election_duration_hours: int
    # Loopback-only local mode. Callers pass this into validate_target explicitly.
    local_test_allowed: bool = False


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise ConfigError(f"{name} must be set")
    return value


def _required_password(env: Mapping[str, str], name: str) -> str:
    """Passwords are read from the environment and never defaulted."""
    value = env.get(name) or ""
    if not value.strip():
        raise ConfigError(
            f"{name} must be set. Passwords have no default in this package."
        )
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ConfigError(
            f"{name} must be at least {PASSWORD_MIN_LENGTH} characters, to match "
            f"the backend's registration rule."
        )
    return value


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    require_voter_password: bool = True,
) -> PerfConfig:
    """Build the configuration from environment variables.

    Reading — not validating the target. ``validate_target`` and
    ``require_setup_allowed`` are separate calls so a caller cannot accidentally
    obtain a config object that has silently been blessed as safe.

    ``require_voter_password`` is False for verification, which only needs the
    voter password in ``--check-logins`` mode.
    """
    env = os.environ if env is None else env

    batch = validate_batch(env.get(ENV_BATCH) or default_batch())
    # Built eagerly so an over-long batch fails here rather than on the first
    # registration request.
    voter_group(batch)

    raw_hours = (env.get(ENV_ELECTION_DURATION_HOURS) or "").strip()
    if raw_hours:
        try:
            hours = int(raw_hours)
        except ValueError:
            raise ConfigError(
                f"{ENV_ELECTION_DURATION_HOURS} must be a whole number of hours; "
                f"got {raw_hours!r}"
            )
    else:
        hours = DEFAULT_DURATION_HOURS

    if hours < 1:
        raise ConfigError(f"{ENV_ELECTION_DURATION_HOURS} must be at least 1")

    voter_password: str | None
    if require_voter_password:
        voter_password = _required_password(env, ENV_VOTER_PASSWORD)
    else:
        voter_password = env.get(ENV_VOTER_PASSWORD) or None

    return PerfConfig(
        base_url=_required(env, ENV_BASE_URL),
        production_base_url=_required(env, ENV_PRODUCTION_BASE_URL),
        setup_allowed=env.get(ENV_SETUP_ALLOWED),
        batch=batch,
        organizer_email=(
            env.get(ENV_ORGANIZER_EMAIL) or f"perf_organizer_{batch}@test.com"
        ).strip(),
        organizer_username=(
            env.get(ENV_ORGANIZER_USERNAME) or f"perf_organizer_{batch}"
        ).strip(),
        organizer_password=_required_password(env, ENV_ORGANIZER_PASSWORD),
        voter_password=voter_password,
        election_duration_hours=hours,
        local_test_allowed=parse_local_test_allowed(env.get(ENV_LOCAL_TEST_ALLOWED)),
    )


# ── Safety guards ─────────────────────────────────────────────────────────────


def normalize_base_url(url: str) -> str:
    """Canonical form used for the "staging is not production" comparison.

    Lowercases scheme and host, drops the default port, strips any trailing
    slash, and discards query and fragment. Without this, ``https://api.example.com``
    and ``https://API.example.com:443/`` would read as two different targets.
    """
    parts = urlsplit((url or "").strip())
    if not parts.scheme or not parts.netloc:
        raise SafetyError(f"{url!r} is not an absolute URL (expected https://host)")

    host = (parts.hostname or "").lower()

    # urlsplit accepts any netloc and only validates the port when it is read, so
    # a non-numeric or out-of-range port surfaces here as a raw ValueError. Left
    # uncaught it would escape the guard layer as an unhandled traceback rather
    # than the deliberate refusal every other bad target produces.
    try:
        port = parts.port
    except ValueError:
        raise SafetyError(
            f"{url!r} has an invalid port. Refusing to validate the target."
        )

    # urlsplit strips the brackets from an IPv6 literal, so they have to be put
    # back before a port can be appended — "::1:8000" would be an unusable URL
    # and would compare unequal to itself after a round trip.
    if ":" in host:
        host = f"[{host}]"

    if port is not None and not (
        (parts.scheme.lower() == "https" and port == 443)
        or (parts.scheme.lower() == "http" and port == 80)
    ):
        host = f"{host}:{port}"

    path = parts.path.rstrip("/")
    return f"{parts.scheme.lower()}://{host}{path}"


def _looks_like_staging(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    whole = url.lower()
    return any(token in host or token in whole for token in STAGING_TOKENS)


def is_loopback_host(host: str | None) -> bool:
    """Exact loopback identity for a URL hostname.

    Never substring matching — that is what makes ``localhost.example.com``,
    ``notlocalhost`` and ``127.0.0.1.evil.com`` all correctly non-loopback. Either
    the host is exactly ``localhost``, or it must parse as an IP address whose own
    ``is_loopback`` flag is set (127.0.0.0/8 and ::1).

    ``0.0.0.0`` is unspecified rather than loopback, so it is refused: binding or
    pointing at it is not the same as talking to this machine only.
    """
    if not host:
        return False

    if host.lower() == "localhost":
        return True

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_local_test_allowed(value: str | None) -> bool:
    """Read PERF_LOCAL_TEST_ALLOWED. Exactly ``true`` arms loopback-only mode.

    Unset and empty both mean "off". Anything other than the two exact lowercase
    spellings is an error rather than a silent "off": a user who typed ``TRUE``
    believes local mode is armed, and letting that fall through to the HTTPS rule
    would produce a confusing "must be HTTPS" refusal instead of naming the real
    problem.
    """
    if value is None or value == "":
        return False

    if value == "true":
        return True

    if value == "false":
        return False

    raise ConfigError(
        f"{ENV_LOCAL_TEST_ALLOWED} must be exactly 'true' or 'false' — lowercase, "
        f"with no surrounding whitespace. Got {value!r}."
    )


def _require_loopback_target(raw_url: str, normalized: str) -> None:
    """In local mode the target must be this machine, and nothing else.

    Arming ``PERF_LOCAL_TEST_ALLOWED`` does not widen what is reachable; it swaps
    one narrow rule (HTTPS + a staging-named host) for another (loopback only).
    A public HTTPS staging URL is refused here too, because a run armed for local
    testing that silently reached staging would be the exact confusion this flag
    exists to prevent.
    """
    parts = urlsplit(raw_url.strip())
    scheme = parts.scheme.lower()

    if scheme not in ("http", "https"):
        raise SafetyError(
            f"{ENV_BASE_URL} must be http:// or https:// in local mode; "
            f"got scheme {scheme!r}."
        )

    # Checked explicitly: the hostname of "http://user:pass@localhost:8000" is
    # still "localhost", so the loopback test alone would wave it through.
    if parts.username or parts.password:
        raise SafetyError(
            f"{ENV_BASE_URL} must not embed a username or password. Credentials "
            f"belong in the environment, never in the target URL."
        )

    host = (parts.hostname or "").lower()

    if not is_loopback_host(host):
        raise SafetyError(
            f"{ENV_LOCAL_TEST_ALLOWED}=true permits only a loopback target — "
            f"'localhost', 127.0.0.0/8 or ::1. The host of {raw_url!r} is "
            f"{host or '(none)'!r}, which is not loopback. Local mode never "
            f"reaches another machine."
        )


def require_setup_allowed(value: str | None) -> None:
    """Guard 1: the script is disarmed unless PERF_SETUP_ALLOWED is exactly ``true``.

    Exact match, not a truthiness test: ``TRUE``, ``1`` and ``yes`` are all
    refused, so the variable cannot be armed by accident or by a shell that
    normalises values.
    """
    if value != "true":
        raise SafetyError(
            f"Refusing to run: {ENV_SETUP_ALLOWED} must be exactly 'true' "
            f"(got {value!r}). Nothing has been created."
        )


def validate_target(
    base_url: str,
    production_base_url: str,
    *,
    local_allowed: bool = False,
) -> str:
    """Guards 2-5. Returns the normalized target URL.

    Applied by *both* scripts, so a read-only verification run cannot be pointed
    at production either.

    ``local_allowed`` is passed explicitly by every caller and is never read from
    the environment here — a validator that consults os.environ on its own cannot
    be tested honestly, and the whole point of this function is that its verdict
    depends only on its arguments. It defaults to False, so any call site that
    has not opted in keeps the original staging rules exactly.

    Two mutually exclusive rule sets:

    * ``local_allowed=False`` (the default, and every Render/staging run):
      HTTPS, and a hostname that names itself 'staging' or 'performance'.
    * ``local_allowed=True``: a loopback target only, over http or https. The
      staging-name rule does not apply — loopback identity is a stronger
      guarantee than a naming convention — but a public URL of any scheme is
      refused.

    Both modes require PERF_PRODUCTION_BASE_URL, refuse a target that normalizes
    to it, and refuse malformed URLs and invalid ports.
    """
    if not (base_url or "").strip():
        raise SafetyError(f"{ENV_BASE_URL} must be set")

    if not (production_base_url or "").strip():
        raise SafetyError(
            f"{ENV_PRODUCTION_BASE_URL} must be set. It is required so the script "
            f"has something concrete to refuse to talk to."
        )

    staging = normalize_base_url(base_url)
    production = normalize_base_url(production_base_url)

    if local_allowed:
        _require_loopback_target(base_url, staging)
    elif not staging.startswith("https://"):
        raise SafetyError(
            f"{ENV_BASE_URL} must be HTTPS. Refusing to send credentials over "
            f"{urlsplit(staging).scheme or 'an unknown scheme'}. "
            f"(Set {ENV_LOCAL_TEST_ALLOWED}=true only to test against loopback.)"
        )

    if staging == production:
        raise SafetyError(
            f"Refusing to run: {ENV_BASE_URL} and {ENV_PRODUCTION_BASE_URL} "
            f"resolve to the same target. This script must never touch production."
        )

    if _looks_like_staging(production):
        raise SafetyError(
            f"Refusing to run: {ENV_PRODUCTION_BASE_URL} itself looks like a "
            f"staging URL, so the production comparison would be meaningless. "
            f"Set it to the real production base URL."
        )

    if not local_allowed and not _looks_like_staging(staging):
        raise SafetyError(
            f"Refusing to run: {ENV_BASE_URL} does not identify itself as a test "
            f"target. Its hostname must contain 'staging' or 'performance'."
        )

    return staging


def describe_plan(
    config: PerfConfig,
    staging_url: str,
    *,
    organizer_count: int = 1,
    voter_count: int = VOTER_COUNT,
    election_count: int = ELECTION_COUNT,
) -> str:
    """Guard 7: the exact target and volume, printed before the confirmation."""
    return "\n".join(
        [
            "",
            "  Performance-test data setup",
            "  " + "-" * 52,
            f"  Target URL          : {staging_url}",
            f"  Batch               : {config.batch}",
            f"  Organizer accounts  : {organizer_count} (created or reused)",
            f"  Voter accounts      : {voter_count} (created)",
            f"  Elections           : {election_count} (created, active)",
            "  " + "-" * 52,
            "  This creates PERMANENT staging records. There is no cleanup mode.",
            "",
        ]
    )


def confirm_target(
    staging_url: str,
    *,
    assume_yes: bool,
    prompt: Any = input,
    stream: Any = None,
) -> None:
    """Guard 6: the operator retypes the target URL, unless ``--yes`` was passed."""
    if assume_yes:
        return

    answer = prompt(f"Type the target URL to confirm ({staging_url}): ")
    if normalize_base_url((answer or "").strip() or "about:blank") != staging_url:
        raise SafetyError("Confirmation did not match the target URL. Aborted.")


# ── HTTP client ───────────────────────────────────────────────────────────────

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _read_only_guard(request: httpx.Request) -> None:
    """Refuse anything that could change server state.

    ``POST /auth/login`` is the single exception: verification has to authenticate
    as the organizer to read the eligibility list at all, and the login route
    creates nothing — it reads one user row and returns a token. Every other POST,
    and every PUT, PATCH and DELETE, is blocked before it is sent.
    """
    method = request.method.upper()
    if method in SAFE_METHODS:
        return
    if method == "POST" and request.url.path.rstrip("/") == LOGIN_PATH:
        return
    raise ReadOnlyViolationError(
        f"Read-only client blocked a {method} request to {request.url.path}"
    )


def build_client(
    base_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    read_only: bool = False,
    timeout: float = 30.0,
) -> httpx.Client:
    """Build the HTTP client. Tests inject an ``httpx.MockTransport`` here.

    ``transport`` is the seam that keeps the unit tests off the network: nothing
    in this package constructs a client without going through this function.
    """
    hooks = {"request": [_read_only_guard]} if read_only else {}
    return httpx.Client(
        base_url=base_url,
        transport=transport,
        timeout=timeout,
        event_hooks=hooks,
        headers={"User-Agent": "evoting-performance-setup/1"},
    )


def check_health(client: httpx.Client) -> dict[str, Any]:
    """Guard 8: GET /health/db must succeed and report a connected database."""
    try:
        response = client.get(HEALTH_PATH)
    except httpx.HTTPError as exc:
        raise SafetyError(f"Health check failed: could not reach {HEALTH_PATH} ({exc})")

    if response.status_code != 200:
        raise SafetyError(
            f"Health check failed: {HEALTH_PATH} returned "
            f"{response.status_code}. Nothing has been created."
        )

    try:
        body = response.json()
    except ValueError:
        raise SafetyError(f"Health check failed: {HEALTH_PATH} returned non-JSON")

    if body.get("database") != "connected":
        raise SafetyError(
            f"Health check failed: database reported as "
            f"{body.get('database')!r}, expected 'connected'."
        )

    return body


def login(client: httpx.Client, email: str, password: str) -> str:
    """Log in and return the access token.

    Returns the token to the caller rather than storing it on a module global, so
    there is no ambient place for it to be picked up and serialized.
    """
    response = client.post(LOGIN_PATH, json={"email": email, "password": password})

    if response.status_code == 200:
        token = (response.json() or {}).get("access_token")
        if not token:
            raise ApiError("Login succeeded but no access_token was returned")
        return token

    if response.status_code == 401:
        raise ApiError(f"Invalid credentials for {email}")

    raise ApiError(
        f"Unexpected {response.status_code} from {LOGIN_PATH}: "
        f"{short_detail(response)}"
    )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def short_detail(response: httpx.Response) -> str:
    """The API's error detail, truncated, for an operator-facing message."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])[:200]
    return str(body)[:200]


# ── Payload builders ──────────────────────────────────────────────────────────


def build_voter_payload(index: int, batch: str, password: str) -> dict[str, Any]:
    """One registration payload, matching RegisterRequest in auth_schema.py."""
    return {
        "username": voter_username(index, batch),
        "email": voter_email(index, batch),
        "password": password,
        "role": "voter",
        "group": voter_group(batch),
    }


def build_voter_payloads(batch: str, password: str) -> list[dict[str, Any]]:
    """All fifty payloads, in order, 1-based."""
    return [
        build_voter_payload(index, batch, password)
        for index in range(1, VOTER_COUNT + 1)
    ]


def build_election_payload(
    run: int,
    batch: str,
    external_ids: Sequence[str],
    *,
    duration_hours: int = DEFAULT_DURATION_HOURS,
    clock: datetime | None = None,
) -> dict[str, Any]:
    """One payload for POST /elections/, matching ElectionCreate.

    The start date is backdated five minutes so the election is inside its voting
    period the moment it exists — the vote route rejects ``now < start_date``.
    """
    if len(external_ids) != VOTER_COUNT:
        raise ConfigError(
            f"Election payload needs exactly {VOTER_COUNT} eligible voters, "
            f"got {len(external_ids)}"
        )
    if len(set(external_ids)) != len(external_ids):
        # The backend answers 400 on a duplicate; catching it here names the
        # problem instead of failing halfway through the election run.
        raise ConfigError("Eligible voter external ids contain duplicates")

    moment = clock or now_sgt()

    return {
        "title": election_title(batch, run),
        "description": ELECTION_DESCRIPTION,
        "start_date": format_sgt(moment - START_BACKDATE),
        "end_date": format_sgt(moment + timedelta(hours=duration_hours)),
        "ballot_type": BALLOT_TYPE,
        "max_selections": MAX_SELECTIONS,
        "candidates": [
            {"name": name, "display_order": order}
            for order, name in enumerate(CANDIDATE_NAMES, start=1)
        ],
        "eligible_voter_external_ids": list(external_ids),
    }


def build_election_payloads(
    batch: str,
    external_ids: Sequence[str],
    *,
    duration_hours: int = DEFAULT_DURATION_HOURS,
    clock: datetime | None = None,
) -> list[dict[str, Any]]:
    return [
        build_election_payload(
            run, batch, external_ids, duration_hours=duration_hours, clock=clock
        )
        for run in range(1, ELECTION_COUNT + 1)
    ]


# ── Manifest ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent / "data"

# Keys that must never appear anywhere in a serialized manifest. Checked by name
# on every nested mapping, so a future field cannot quietly introduce one.
FORBIDDEN_MANIFEST_KEYS = frozenset(
    {
        "password",
        "passwords",
        "voter_password",
        "organizer_password",
        "password_hash",
        "hashed_password",
        "access_token",
        "refresh_token",
        "token",
        "jwt",
        "authorization",
        "secret",
        "secret_key",
        "private_key",
        "database_url",
        "render_api_key",
        "render_secret",
        "supabase_key",
        "supabase_url",
        "service_role_key",
    }
)

# Value shapes that betray a secret even under an innocent key name.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"^ey[A-Za-z0-9_-]{8,}\.", re.IGNORECASE),  # JWT
    re.compile(r"^bearer\s+\S+", re.IGNORECASE),
    re.compile(r"^postgres(ql)?://", re.IGNORECASE),
)


def manifest_path(batch: str, data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / f"performance_manifest_{batch}.json"


def new_manifest(base_url: str, batch: str, organizer: Mapping[str, str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "base_url": base_url,
        "batch": batch,
        "created_at": now_sgt().isoformat(timespec="seconds"),
        "organizer": {
            "username": organizer["username"],
            "email": organizer["email"],
        },
        "voters": [],
        "elections": [],
    }


def find_secret_leaks(manifest: Any, path: str = "$") -> list[str]:
    """Every place the manifest holds something that must not be persisted.

    Walks the structure rather than grepping the serialized text, so the reported
    location is precise. Returns a list of human-readable locations; empty means
    clean.
    """
    leaks: list[str] = []

    if isinstance(manifest, Mapping):
        for key, value in manifest.items():
            here = f"{path}.{key}"
            if str(key).strip().lower() in FORBIDDEN_MANIFEST_KEYS:
                leaks.append(here)
            leaks.extend(find_secret_leaks(value, here))
    elif isinstance(manifest, (list, tuple)):
        for index, value in enumerate(manifest):
            leaks.extend(find_secret_leaks(value, f"{path}[{index}]"))
    elif isinstance(manifest, str):
        if any(pattern.match(manifest) for pattern in _SECRET_VALUE_PATTERNS):
            leaks.append(f"{path} (value looks like a token or connection string)")

    return leaks


def assert_no_secrets(manifest: Mapping[str, Any]) -> None:
    leaks = find_secret_leaks(manifest)
    if leaks:
        raise ManifestError(
            "Refusing to write the manifest: it contains values that must never "
            "be persisted: " + ", ".join(leaks)
        )


def save_manifest(manifest: Mapping[str, Any], path: Path) -> None:
    """Write the manifest atomically: temp file in the same directory, then replace.

    Same directory so ``os.replace`` stays on one filesystem and is therefore
    atomic. A crash mid-write leaves the previous complete manifest in place, which
    is what makes resuming safe.
    """
    assert_no_secrets(manifest)

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")

    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temp_path, path)


def load_manifest(path: Path) -> dict[str, Any] | None:
    """Read an existing manifest, or None when there is nothing to resume from."""
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(
            f"Manifest at {path} could not be read ({exc}). Move it aside and "
            f"investigate before rerunning — do not delete it blindly, it may be "
            f"the only record of accounts that exist on the server."
        )

    if not isinstance(manifest, dict):
        raise ManifestError(f"Manifest at {path} is not a JSON object")

    return manifest


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    batch: str,
    base_url: str,
    strict: bool = False,
) -> None:
    """Check the manifest's shape and that it belongs to this run.

    ``strict`` additionally requires the data set to be complete — 50 voters and
    3 elections — which is what verification demands and what an in-progress setup
    must not.
    """
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"Manifest schema_version is {manifest.get('schema_version')!r}, "
            f"expected {SCHEMA_VERSION}"
        )

    if manifest.get("batch") != batch:
        raise ManifestError(
            f"Manifest belongs to batch {manifest.get('batch')!r}, but this run is "
            f"batch {batch!r}. Refusing to overwrite another batch's manifest."
        )

    stored_url = manifest.get("base_url")
    if normalize_base_url(str(stored_url)) != normalize_base_url(base_url):
        raise ManifestError(
            f"Manifest was created against {stored_url!r}, but this run targets "
            f"{base_url!r}. Refusing to mix data from two deployments."
        )

    organizer = manifest.get("organizer")
    if not isinstance(organizer, Mapping) or not organizer.get("email"):
        raise ManifestError("Manifest is missing the organizer block")

    voters = manifest.get("voters")
    if not isinstance(voters, list):
        raise ManifestError("Manifest 'voters' must be a list")

    if len(voters) > VOTER_COUNT:
        raise ManifestError(
            f"Manifest holds {len(voters)} voters, more than the expected "
            f"{VOTER_COUNT}. Refusing to continue from an inconsistent file."
        )

    seen_usernames: set[str] = set()
    seen_emails: set[str] = set()
    seen_external_ids: set[str] = set()

    for position, voter in enumerate(voters, start=1):
        if not isinstance(voter, Mapping):
            raise ManifestError(f"Voter entry {position} is not an object")

        for field_name in ("username", "email", "external_id"):
            if not str(voter.get(field_name) or "").strip():
                raise ManifestError(
                    f"Voter entry {position} is missing '{field_name}'"
                )

        # Entries are positional: entry N must be voter N of this batch. That is
        # what lets the resume point be computed from the length alone.
        expected_username = voter_username(position, batch)
        if voter["username"] != expected_username:
            raise ManifestError(
                f"Voter entry {position} is {voter['username']!r}, expected "
                f"{expected_username!r}. The manifest is out of order."
            )
        if voter["email"] != voter_email(position, batch):
            raise ManifestError(
                f"Voter entry {position} has email {voter['email']!r}, which does "
                f"not match its username."
            )

        for value, seen, label in (
            (voter["username"], seen_usernames, "username"),
            (voter["email"], seen_emails, "email"),
            (voter["external_id"], seen_external_ids, "external_id"),
        ):
            if value in seen:
                raise ManifestError(f"Duplicate voter {label} {value!r} in manifest")
            seen.add(value)

    elections = manifest.get("elections")
    if not isinstance(elections, list):
        raise ManifestError("Manifest 'elections' must be a list")

    if len(elections) > ELECTION_COUNT:
        raise ManifestError(
            f"Manifest holds {len(elections)} elections, more than the expected "
            f"{ELECTION_COUNT}."
        )

    for position, election in enumerate(elections, start=1):
        if not isinstance(election, Mapping):
            raise ManifestError(f"Election entry {position} is not an object")
        if election.get("run") != position:
            raise ManifestError(
                f"Election entry {position} has run {election.get('run')!r}; "
                f"entries must be in run order."
            )
        for field_name in ("election_id", "title", "candidate_id"):
            if not str(election.get(field_name) or "").strip():
                raise ManifestError(
                    f"Election entry {position} is missing '{field_name}'"
                )
        if election["title"] != election_title(batch, position):
            raise ManifestError(
                f"Election entry {position} is titled {election['title']!r}, "
                f"expected {election_title(batch, position)!r}"
            )

        candidates = election.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != len(CANDIDATE_NAMES):
            raise ManifestError(
                f"Election entry {position} must list exactly "
                f"{len(CANDIDATE_NAMES)} candidates"
            )
        names = [str((c or {}).get("name")) for c in candidates]
        if names != list(CANDIDATE_NAMES):
            raise ManifestError(
                f"Election entry {position} has candidates {names!r}, expected "
                f"{list(CANDIDATE_NAMES)!r}"
            )
        if election["candidate_id"] not in [str((c or {}).get("id")) for c in candidates]:
            raise ManifestError(
                f"Election entry {position} designates a candidate_id that is not "
                f"one of its own candidates"
            )

    if strict:
        if len(voters) != VOTER_COUNT:
            raise ManifestError(
                f"Manifest holds {len(voters)} voters, expected {VOTER_COUNT}. "
                f"Setup has not finished."
            )
        if len(elections) != ELECTION_COUNT:
            raise ManifestError(
                f"Manifest holds {len(elections)} elections, expected "
                f"{ELECTION_COUNT}. Setup has not finished."
            )

    assert_no_secrets(manifest)


def manifest_external_ids(manifest: Mapping[str, Any]) -> list[str]:
    return [str(voter["external_id"]) for voter in manifest.get("voters", [])]


def iter_lines(text: str) -> Iterable[str]:
    """Small helper so callers can print multi-line blocks through one writer."""
    return text.splitlines()
