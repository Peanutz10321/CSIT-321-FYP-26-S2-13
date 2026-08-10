"""Fixtures for the performance-test data scripts.

Every test in this package runs against an ``httpx.MockTransport``. No test may
open a socket: the transport answers from a handler defined in-process, and the
recorder below asserts on exactly what would have been sent. There is no fixture
here that reads a real environment, a real ``.env`` file or a real database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

import httpx
import pytest

from performance_tests import common


STAGING_URL = "https://staging-api.example.com"
PRODUCTION_URL = "https://api.example.com"
BATCH = "20260810A"
ORGANIZER_PASSWORD = "organizer-password-1"
VOTER_PASSWORD = "voter-password-1"

# A syntactically plausible JWT, so a test can prove one never reaches the
# manifest. It is a fixture value, not a credential for anything.
FAKE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl"


def base_env(**overrides: str) -> dict[str, str]:
    """A complete, valid environment. Tests remove or override one key at a time."""
    env = {
        common.ENV_BASE_URL: STAGING_URL,
        common.ENV_PRODUCTION_BASE_URL: PRODUCTION_URL,
        common.ENV_SETUP_ALLOWED: "true",
        common.ENV_BATCH: BATCH,
        common.ENV_ORGANIZER_EMAIL: f"perf_organizer_{BATCH}@test.com",
        common.ENV_ORGANIZER_USERNAME: f"perf_organizer_{BATCH}",
        common.ENV_ORGANIZER_PASSWORD: ORGANIZER_PASSWORD,
        common.ENV_VOTER_PASSWORD: VOTER_PASSWORD,
        common.ENV_ELECTION_DURATION_HOURS: "24",
    }
    env.update(overrides)
    return {key: value for key, value in env.items() if value is not None}


@dataclass
class RecordedRequest:
    method: str
    path: str
    json_body: Any
    headers: dict[str, str]

    @property
    def is_mutating(self) -> bool:
        return self.method not in common.SAFE_METHODS


@dataclass
class FakeApi:
    """An in-memory stand-in for the deployed backend.

    It answers the handful of endpoints these scripts touch, records every request
    it is asked to serve, and lets a test bend one endpoint at a time through the
    ``*_override`` hooks. Anything it is not told about is a 404, so an
    unanticipated call fails the test rather than passing silently.
    """

    batch: str = BATCH
    organizer_registered: bool = False
    healthy: bool = True
    health_status: int = 200
    voters: dict[str, dict[str, Any]] = field(default_factory=dict)
    elections: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[RecordedRequest] = field(default_factory=list)
    register_override: Callable[[httpx.Request, Any], httpx.Response | None] | None = None
    election_voters_override: Callable[[str], list[dict[str, Any]] | None] | None = None
    active_elections_override: Callable[[str | None], list[dict[str, Any]] | None] | None = None

    # ── recorded traffic helpers ──────────────────────────────────────────────

    @property
    def mutating_requests(self) -> list[RecordedRequest]:
        return [request for request in self.requests if request.is_mutating]

    @property
    def paths(self) -> list[str]:
        return [f"{request.method} {request.path}" for request in self.requests]

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [request for request in self.requests if request.path == path]

    # ── transport ─────────────────────────────────────────────────────────────

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content) if request.content else None
        except json.JSONDecodeError:
            body = None

        self.requests.append(
            RecordedRequest(
                method=request.method.upper(),
                path=request.url.path,
                json_body=body,
                headers=dict(request.headers),
            )
        )

        path = request.url.path
        method = request.method.upper()

        if method == "GET" and path == common.HEALTH_PATH:
            return self._health()
        if method == "POST" and path == common.LOGIN_PATH:
            return self._login(body or {})
        if method == "POST" and path == common.REGISTER_PATH:
            return self._register(request, body or {})
        if method == "POST" and path == common.ELECTIONS_PATH:
            return self._create_election(body or {})
        if method == "GET" and path == "/elections/active":
            return self._active_elections(request.url.params.get("search"))
        if method == "GET" and path.endswith("/voters"):
            return self._eligible_voters(path.split("/")[2])
        if method == "GET" and path.startswith("/elections/"):
            return self._election_detail(path.split("/")[2])

        return httpx.Response(404, json={"detail": f"no stub for {method} {path}"})

    # ── endpoint stubs ────────────────────────────────────────────────────────

    def _health(self) -> httpx.Response:
        if self.health_status != 200:
            return httpx.Response(self.health_status, json={"detail": "unavailable"})
        return httpx.Response(
            200,
            json={
                "database": "connected" if self.healthy else "disconnected",
                "time": "2026-08-10 13:00:00+08",
            },
        )

    def _login(self, body: dict[str, Any]) -> httpx.Response:
        email = body.get("email", "")
        known = self.organizer_registered and email.startswith("perf_organizer_")
        known = known or email in {v["email"] for v in self.voters.values()}
        if not known:
            return httpx.Response(
                401, json={"detail": "Please provide a valid email and password"}
            )
        return httpx.Response(200, json={"access_token": FAKE_TOKEN, "token_type": "bearer"})

    def _register(self, request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        if self.register_override is not None:
            override = self.register_override(request, body)
            if override is not None:
                return override

        username = body.get("username", "")
        email = body.get("email", "")

        if email in {v["email"] for v in self.voters.values()}:
            return httpx.Response(400, json={"detail": "Account already exists."})

        record = {
            "id": str(uuid4()),
            "role": body.get("role", "voter"),
            "status": "active",
            "external_id": self._next_external_id(body.get("role", "voter")),
            "username": username,
            "full_name": None,
            "email": email,
            "group": body.get("group"),
            "created_at": "2026-08-10T13:00:00",
            "updated_at": "2026-08-10T13:00:00",
        }

        if body.get("role") == "organizer":
            self.organizer_registered = True
        else:
            self.voters[record["external_id"]] = record

        return httpx.Response(201, json=record)

    def _next_external_id(self, role: str) -> str:
        prefix = "ORG" if role == "organizer" else "VOT"
        return f"{prefix}-{len(self.voters) + 1:05d}"

    def _create_election(self, body: dict[str, Any]) -> httpx.Response:
        election_id = str(uuid4())
        candidates = [
            {
                "id": str(uuid4()),
                "name": candidate["name"],
                "description": None,
                "photo_url": None,
                "display_order": candidate.get("display_order") or index,
            }
            for index, candidate in enumerate(body.get("candidates", []), start=1)
        ]

        record = {
            "id": election_id,
            "organizer_id": str(uuid4()),
            "organizer_username": f"perf_organizer_{self.batch}",
            "title": body.get("title"),
            "description": body.get("description"),
            "status": "active",
            "ballot_type": body.get("ballot_type", "single"),
            "max_selections": body.get("max_selections", 1),
            "start_date": body.get("start_date"),
            "end_date": body.get("end_date"),
            "candidates": candidates,
        }

        self.elections[election_id] = {
            "response": record,
            "eligible": list(body.get("eligible_voter_external_ids", [])),
            "voted": set(),
        }
        return httpx.Response(201, json=record)

    def _active_elections(self, search: str | None) -> httpx.Response:
        """GET /elections/active, reproducing the route's real filter.

        The backend applies ``Election.title.ilike(f"%{search}%")`` — a
        substring, case-insensitive match — and, for an organizer, restricts to
        their own elections. Modelling the looseness faithfully is the point:
        the caller's exact-title filter has to be what actually decides.
        """
        if self.active_elections_override is not None:
            override = self.active_elections_override(search)
            if override is not None:
                return httpx.Response(200, json=override)

        rows = [
            stored["response"]
            for stored in self.elections.values()
            if stored["response"].get("status") == "active"
        ]

        if search:
            needle = search.lower()
            rows = [row for row in rows if needle in str(row.get("title", "")).lower()]

        return httpx.Response(200, json=rows)

    def _election_detail(self, election_id: str) -> httpx.Response:
        stored = self.elections.get(election_id)
        if not stored:
            return httpx.Response(404, json={"detail": "Election not found"})
        return httpx.Response(200, json=stored["response"])

    def _eligible_voters(self, election_id: str) -> httpx.Response:
        if self.election_voters_override is not None:
            override = self.election_voters_override(election_id)
            if override is not None:
                return httpx.Response(200, json=override)

        stored = self.elections.get(election_id)
        if not stored:
            return httpx.Response(404, json={"detail": "Election not found"})

        rows = []
        for external_id in stored["eligible"]:
            voter = self.voters.get(external_id, {})
            rows.append(
                {
                    "id": str(uuid4()),
                    "election_id": election_id,
                    "voter_id": voter.get("id", str(uuid4())),
                    "voter_external_id": external_id,
                    "voter_username": voter.get("username", external_id),
                    "voter_email": voter.get("email", f"{external_id}@test.com"),
                    "eligibility_status": "eligible",
                    "voted_at": (
                        "2026-08-10T14:00:00" if external_id in stored["voted"] else None
                    ),
                    "created_at": "2026-08-10T13:00:00",
                }
            )
        return httpx.Response(200, json=rows)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def data_dir(tmp_path):
    """Manifests are written under tmp_path, never into performance_tests/data/."""
    target = tmp_path / "data"
    target.mkdir()
    return target


@pytest.fixture
def config():
    return common.load_config(base_env())


@pytest.fixture
def silent():
    """A writer that swallows progress output but keeps it available for assertions."""
    lines: list[str] = []

    def write(message: str) -> None:
        lines.extend(message.splitlines() or [""])

    write.lines = lines  # type: ignore[attr-defined]
    return write


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Belt and braces: make an unmocked client construction fail loudly.

    ``build_client`` is the only place this package creates a client, and every
    test passes a MockTransport into it. This guard turns a future code path that
    forgets to do so into an immediate error instead of a real connection.
    """
    real_init = httpx.Client.__init__

    def guarded_init(self, *args, **kwargs):
        if kwargs.get("transport") is None:
            raise AssertionError(
                "A test tried to build an httpx.Client without a MockTransport. "
                "Performance-test unit tests must never touch the network."
            )
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", guarded_init)
