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

import pytest

# Imported as a module, deliberately. `from app.main import app` would pin this
# file to whichever FastAPI instance existed when it was first imported, and
# app.main is not a stable singleton across a test session: tests/test_cors_config.py
# rebuilds it with importlib.reload to exercise CORS configurations, which rebinds
# app.main.app to a new instance each time. Reading the attribute at call time
# always inspects the app the application currently exposes.
import app.main


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
    """Every (method, path) pair the application currently serves.

    Read from the generated OpenAPI document rather than by walking app.routes.
    Walking app.routes depends on a FastAPI internal that changed: up to 0.136
    include_router copied each sub-route into app.routes, so filtering for
    APIRoute found everything; from 0.139 it appends one internal
    _IncludedRouter per call and leaves the sub-routes nested inside it, so the
    same filter finds only the two routes declared with @app.get in main.py.
    That silently turned every "route is absent" assertion here into a vacuous
    pass on the pinned version.

    The OpenAPI schema is stable across those versions and is also the better
    definition of the thing under test: what the API advertises to clients.
    """
    schema = app.main.app.openapi()

    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }


def test_the_app_under_test_has_its_routers_mounted():
    """Guard for every assertion below.

    An "is not registered" assertion is vacuously true against an app whose
    routers were never mounted, so a half-built app would report the removed
    surface as gone while proving nothing. This fails first, and says so,
    instead of leaving that to be inferred from a wall of assertion errors.
    """
    routes = registered_routes()

    assert len(routes) > 10, (
        f"only {len(routes)} route(s) registered: {sorted(routes)}. "
        "app.main.app is missing its routers, so the absence assertions in "
        "this file would pass without testing anything."
    )


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
