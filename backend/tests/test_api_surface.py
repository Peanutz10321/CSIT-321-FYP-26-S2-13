"""The public API surface is deliberately bounded.

Four endpoints were removed on purpose:

  * manual election finalization (``POST /elections/{id}/close`` and the legacy
    ``PATCH /elections/{id}/complete``) — an expired election is finalized
    automatically when its results are requested, so there is no manual trigger;
  * ballot verification (``GET /votes/{id}/verify``) — commitments are still
    generated and stored, but nothing verifies them at request time;
  * administrator statistics (``GET /admin/stats``) — no client consumed it.

These tests read the live FastAPI route table rather than issuing requests, so
they fail if a route is reintroduced even when no client calls it. A 404 from a
request would not distinguish "route removed" from "route present but the
resource is missing".
"""

from fastapi.routing import APIRoute
import pytest

from app.main import app


REMOVED_ROUTES = [
    ("POST", "/elections/{election_id}/close"),
    ("PATCH", "/elections/{election_id}/complete"),
    ("GET", "/votes/{vote_id}/verify"),
    ("GET", "/admin/stats"),
]

# Positive control. Without it this file would still pass if the router table
# were empty or the app failed to mount its routers, which would make the
# absence assertions meaningless.
RETAINED_ROUTES = [
    ("GET", "/results/elections/{election_id}"),
    ("POST", "/votes/"),
    ("GET", "/votes/{vote_id}"),
    ("PATCH", "/elections/{election_id}/activate"),
    ("GET", "/admin/users"),
    ("PATCH", "/admin/users/{user_id}/suspend"),
    ("PATCH", "/admin/users/{user_id}/unsuspend"),
]


def registered_routes() -> set[tuple[str, str]]:
    """Every (method, path) pair the application currently serves."""
    return {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


@pytest.mark.parametrize(
    "method,path",
    REMOVED_ROUTES,
    ids=[f"{method} {path}" for method, path in REMOVED_ROUTES],
)
def test_removed_route_is_not_registered(method, path):
    assert (method, path) not in registered_routes()


@pytest.mark.parametrize(
    "method,path",
    RETAINED_ROUTES,
    ids=[f"{method} {path}" for method, path in RETAINED_ROUTES],
)
def test_retained_route_is_still_registered(method, path):
    assert (method, path) in registered_routes()


def test_no_route_path_mentions_a_removed_surface():
    """Catches a removed endpoint reappearing under a different method or prefix."""
    removed_suffixes = ("/close", "/complete", "/verify")
    offenders = sorted(
        path
        for _, path in registered_routes()
        if path.endswith(removed_suffixes) or path.startswith("/admin/stats")
    )

    assert offenders == []
