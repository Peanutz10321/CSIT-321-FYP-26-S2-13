"""
Tests for CORS origin configuration and environment validation.

The API previously ran with allow_origins=["*"] and allow_credentials=True, which
is both unrestricted and rejected by browsers for credentialed requests. Origins
are now configured per environment, and a wildcard is refused outright when
running in production.

These also pin the PR5 secret validation, so a change here cannot quietly weaken
RECEIPT_SIGNING_SECRET.
"""

import contextlib

import pytest
from pydantic import ValidationError

from app.config import Settings, parse_cors_origins


VALID_SECRET = "r" * 32


def _settings(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET": "j" * 32,
        "KEYSTORE_MASTER_SECRET": "k" * 32,
        "RECEIPT_SIGNING_SECRET": VALID_SECRET,
        "TESTING": True,
    }
    values.update(overrides)
    return Settings(**values, _env_file=None)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parses_a_single_origin():
    assert parse_cors_origins("https://app.example.edu") == ["https://app.example.edu"]


def test_parses_a_comma_separated_list():
    assert parse_cors_origins(
        "https://a.example.edu,https://b.example.edu"
    ) == ["https://a.example.edu", "https://b.example.edu"]


def test_ignores_surrounding_whitespace_and_empty_entries():
    assert parse_cors_origins(" https://a.example.edu , , https://b.example.edu ") == [
        "https://a.example.edu",
        "https://b.example.edu",
    ]


def test_unset_configuration_yields_no_origins():
    """Fail closed: absent configuration must not become a wildcard."""
    assert parse_cors_origins("") == []
    assert parse_cors_origins(None) == []


def test_trailing_slashes_are_normalised():
    """A browser Origin header never has a trailing slash, so neither may config."""
    assert parse_cors_origins("https://app.example.edu/") == ["https://app.example.edu"]


def test_duplicate_origins_are_collapsed():
    assert parse_cors_origins(
        "https://a.example.edu,https://a.example.edu"
    ) == ["https://a.example.edu"]


def test_wildcard_is_preserved_as_a_single_entry():
    assert parse_cors_origins("*") == ["*"]


# ---------------------------------------------------------------------------
# Malformed configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "app.example.edu",                 # no scheme
        "ftp://app.example.edu",           # unsupported scheme
        "https://",                        # no host
        "https://app.example.edu/path",    # path component
        "https://app.example.edu?q=1",     # query component
        "not a url",
    ],
)
def test_malformed_origins_are_rejected(raw):
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _settings(CORS_ALLOWED_ORIGINS=raw)


def test_a_malformed_entry_rejects_the_whole_list():
    """One bad origin must not be silently dropped from an otherwise valid list."""
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _settings(CORS_ALLOWED_ORIGINS="https://good.example.edu,bad-origin")


def test_wildcard_mixed_with_specific_origins_is_rejected():
    """'*' plus a specific origin is ambiguous; require one or the other."""
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _settings(CORS_ALLOWED_ORIGINS="*,https://app.example.edu")


@pytest.mark.parametrize(
    "raw",
    [
        "https://user:pass@example.com",   # userinfo (credentials)
        "https://user@example.com",        # userinfo (username only)
        "https://example.com:bad",         # non-numeric port
        "https://example.com:99999",       # port out of range
        "https://example.com:",            # empty port
        "https://exa mple.com",            # space in host
        "https://exam\tple.com",           # embedded control character (tab)
        "https://exam\nple.com",           # embedded newline
        "https://-example.com",            # host label starts with a hyphen
        "https://example..com",            # empty host label
        "https://",                        # no host
        "https://example.com/path",        # path component
        "https://example.com?q=1",         # query component
        "https://example.com#frag",        # fragment
    ],
)
def test_strict_origin_rejects_malformed_entries(raw):
    """A CORS origin must be exactly scheme://host[:port] — nothing else."""
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _settings(CORS_ALLOWED_ORIGINS=raw)


@pytest.mark.parametrize(
    "raw",
    [
        "https://example.com",
        "http://localhost:5173",
        "https://vote.example.edu:8443",
        "http://127.0.0.1:8000",
        "https://sub.domain.example.edu",
    ],
)
def test_strict_origin_accepts_well_formed_entries(raw):
    assert _settings(CORS_ALLOWED_ORIGINS=raw).cors_allowed_origins == [raw]


def test_userinfo_origin_does_not_slip_through_in_a_list():
    """One credentialed entry rejects the whole list, not just itself."""
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _settings(
            CORS_ALLOWED_ORIGINS="https://good.example.edu,https://user:pass@evil.example.com"
        )


# ---------------------------------------------------------------------------
# Environment rules
# ---------------------------------------------------------------------------


def test_configured_origins_are_exposed_to_the_app():
    settings = _settings(
        CORS_ALLOWED_ORIGINS="https://a.example.edu,https://b.example.edu"
    )
    assert settings.cors_allowed_origins == [
        "https://a.example.edu",
        "https://b.example.edu",
    ]


def test_an_unlisted_origin_is_simply_absent():
    settings = _settings(CORS_ALLOWED_ORIGINS="https://a.example.edu")
    assert "https://evil.example.com" not in settings.cors_allowed_origins


def test_wildcard_is_allowed_outside_production():
    settings = _settings(ENVIRONMENT="development", CORS_ALLOWED_ORIGINS="*")
    assert settings.cors_allowed_origins == ["*"]


def test_wildcard_is_rejected_in_production():
    """The rule this PR exists to enforce."""
    with pytest.raises(ValidationError, match="wildcard"):
        _settings(ENVIRONMENT="production", CORS_ALLOWED_ORIGINS="*")


@pytest.mark.parametrize("environment", ["Production", "PRODUCTION", " production "])
def test_production_detection_is_case_and_whitespace_insensitive(environment):
    """A stray capital must not disable the production wildcard check."""
    with pytest.raises(ValidationError, match="wildcard"):
        _settings(ENVIRONMENT=environment, CORS_ALLOWED_ORIGINS="*")


def test_production_requires_at_least_one_origin():
    """Empty in production is a misconfiguration; surface it at startup."""
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        _settings(ENVIRONMENT="production", CORS_ALLOWED_ORIGINS="")


def test_production_accepts_explicit_https_origins():
    settings = _settings(
        ENVIRONMENT="production",
        CORS_ALLOWED_ORIGINS="https://vote.example.edu",
    )
    assert settings.is_production is True
    assert settings.cors_allowed_origins == ["https://vote.example.edu"]


@pytest.mark.parametrize(
    "origins",
    [
        "http://vote.example.edu",
        "http://localhost:5173",
        "https://vote.example.edu,http://admin.example.edu",
    ],
)
def test_production_rejects_plain_http_origins(origins):
    """An HTTP frontend can be modified in transit, so production must require TLS."""
    with pytest.raises(ValidationError, match="https"):
        _settings(ENVIRONMENT="production", CORS_ALLOWED_ORIGINS=origins)


def test_non_production_may_leave_origins_unset():
    settings = _settings(ENVIRONMENT="development", CORS_ALLOWED_ORIGINS="")
    assert settings.is_production is False
    assert settings.cors_allowed_origins == []


def test_credentials_are_disabled_when_the_wildcard_is_used():
    """Browsers reject '*' together with credentials, so the pair must not ship."""
    settings = _settings(ENVIRONMENT="development", CORS_ALLOWED_ORIGINS="*")
    assert settings.cors_allow_credentials is False


def test_credentials_are_enabled_for_explicit_origins():
    settings = _settings(CORS_ALLOWED_ORIGINS="https://app.example.edu")
    assert settings.cors_allow_credentials is True


# ---------------------------------------------------------------------------
# ENVIRONMENT must be a known value — it must not fail open on a typo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_environment_accepts_the_known_values(environment):
    assert _settings(
        ENVIRONMENT=environment,
        # production needs an origin; harmless for the others
        CORS_ALLOWED_ORIGINS="https://vote.example.edu",
    ).is_production is (environment == "production")


@pytest.mark.parametrize("environment", [" Production ", "PRODUCTION", "Development", " test "])
def test_environment_normalises_case_and_whitespace(environment):
    """' Production ' etc. still resolve to a known value, not a rejection."""
    settings = _settings(
        ENVIRONMENT=environment,
        CORS_ALLOWED_ORIGINS="https://vote.example.edu",
    )
    assert settings.ENVIRONMENT == environment.strip().lower()


@pytest.mark.parametrize(
    "environment", ["prod", "prodution", "stagingg", "staging", "dev", "", "produ ction"]
)
def test_unknown_environment_is_rejected(environment):
    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        _settings(ENVIRONMENT=environment)


@pytest.mark.parametrize("environment", ["prodution", "prod", "stagingg"])
def test_a_typo_environment_cannot_silently_enable_wildcard_cors(environment):
    """The fail-open bug: a mistyped 'production' must not be treated as dev and
    quietly permit '*'. It must be rejected outright."""
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT=environment, CORS_ALLOWED_ORIGINS="*")


# ---------------------------------------------------------------------------
# PR5 secret validation must survive this change
# ---------------------------------------------------------------------------


def test_receipt_signing_secret_minimum_length_still_enforced():
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        _settings(RECEIPT_SIGNING_SECRET="short")


@pytest.mark.parametrize("other", ["JWT_SECRET", "KEYSTORE_MASTER_SECRET"])
def test_receipt_signing_secret_separation_still_enforced(other):
    shared = "s" * 32
    with pytest.raises(ValidationError, match="must be different"):
        _settings(RECEIPT_SIGNING_SECRET=shared, **{other: shared})


# ---------------------------------------------------------------------------
# Required secrets must not be blank
#
# `str` is satisfied by "", and .env.example ships JWT_SECRET and
# KEYSTORE_MASTER_SECRET deliberately empty. Before this validation the app
# started normally with either one blank — signing every access token with an
# empty HMAC key, which anyone can guess and therefore forge tokens against.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["JWT_SECRET", "KEYSTORE_MASTER_SECRET"])
@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", "\n"])
def test_required_secret_rejects_blank_values(name, blank):
    """Empty and whitespace-only are both blank; neither may start the app."""
    with pytest.raises(ValidationError, match=f"{name} must not be empty"):
        _settings(**{name: blank})


@pytest.mark.parametrize("name", ["JWT_SECRET", "KEYSTORE_MASTER_SECRET"])
def test_required_secret_accepts_a_non_blank_value(name):
    assert getattr(_settings(**{name: "x" * 32}), name) == "x" * 32


@pytest.mark.parametrize("name", ["JWT_SECRET", "KEYSTORE_MASTER_SECRET"])
def test_required_secret_is_not_stripped(name):
    """Only presence is validated. Trimming the stored value would change every
    signature derived from it, silently invalidating tokens or election keys."""
    padded = "  " + "x" * 32 + "  "
    assert getattr(_settings(**{name: padded}), name) == padded


def test_short_secrets_are_still_accepted():
    """Deliberately NOT a length check.

    A minimum length would reject existing short-but-real deployment secrets on
    upgrade — including CI's own `JWT_SECRET: test` — so it belongs in its own
    announced change. This pins the current, narrower contract so a length rule
    cannot be added without updating this test.
    """
    settings = _settings(JWT_SECRET="test", KEYSTORE_MASTER_SECRET="k")

    assert settings.JWT_SECRET == "test"
    assert settings.KEYSTORE_MASTER_SECRET == "k"


def test_receipt_secret_length_is_reported_before_a_blank_jwt_secret():
    """Validator order is load-bearing for the setup documentation.

    A freshly copied .env.example leaves all three secrets empty. The docs tell
    the reader the first error is the RECEIPT_SIGNING_SECRET length one, so the
    blank check must stay defined after it.
    """
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        _settings(JWT_SECRET="", KEYSTORE_MASTER_SECRET="", RECEIPT_SIGNING_SECRET="")


# ---------------------------------------------------------------------------
# JWT algorithm is pinned to HS256
#
# CI suppresses the ecdsa advisory (PYSEC-2026-1325) on the grounds that this API
# signs with HMAC. That is only sound if the algorithm cannot be changed to an
# EC/RSA one at runtime, so the configuration must reject anything but HS256.
# ---------------------------------------------------------------------------


def test_jwt_algorithm_defaults_to_hs256():
    assert _settings().JWT_ALGORITHM == "HS256"


def test_jwt_algorithm_accepts_hs256_explicitly():
    assert _settings(JWT_ALGORITHM="HS256").JWT_ALGORITHM == "HS256"


@pytest.mark.parametrize("algorithm", ["ES256", "RS256", "none", "HS384", "hs256"])
def test_jwt_algorithm_rejects_anything_but_hs256(algorithm):
    """ES*/RS*/case variants/arbitrary values must be refused, not normalised."""
    with pytest.raises(ValidationError):
        _settings(JWT_ALGORITHM=algorithm)


# ---------------------------------------------------------------------------
# The middleware must actually honour the configuration
#
# Settings are read at import time, so the app is rebuilt inside each test with
# the origins under test rather than mutating the shared instance.
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def configured_app(raw_origins, environment="development"):
    """Build app.main.app with the given CORS config, then restore the shared
    module to its ORIGINAL configuration on exit.

    Restoration is owned by this context manager's ``finally``, not by monkeypatch.
    That matters: app.main reads settings at import time, so the reload done to
    rebuild it has to happen *after* the settings are put back — otherwise the
    shared module is rebuilt from the test's values and leaks them. Doing it with
    monkeypatch was the original bug: a fixture that depends on monkeypatch tears
    down before monkeypatch undoes its patches, so the teardown reload still saw
    the patched settings.
    """
    import importlib

    import app.config
    import app.main

    original_cors = app.config.settings.CORS_ALLOWED_ORIGINS
    original_environment = app.config.settings.ENVIRONMENT
    try:
        app.config.settings.CORS_ALLOWED_ORIGINS = raw_origins
        app.config.settings.ENVIRONMENT = environment
        yield importlib.reload(app.main).app
    finally:
        app.config.settings.CORS_ALLOWED_ORIGINS = original_cors
        app.config.settings.ENVIRONMENT = original_environment
        importlib.reload(app.main)


@pytest.fixture
def app_with_origins():
    """Return a builder for a configured app; restore the shared module afterward.

    Each build is entered on an ExitStack, so every configuration is unwound (and
    app.main reloaded back to the original settings) when the fixture tears down —
    independently of any other fixture's teardown order.
    """
    with contextlib.ExitStack() as stack:

        def _build(raw_origins, environment="development"):
            return stack.enter_context(configured_app(raw_origins, environment))

        yield _build


def test_configured_origin_receives_cors_headers(app_with_origins):
    from fastapi.testclient import TestClient

    rebuilt = app_with_origins("https://app.example.edu")

    response = TestClient(rebuilt).get(
        "/", headers={"Origin": "https://app.example.edu"}
    )

    assert response.headers.get("access-control-allow-origin") == "https://app.example.edu"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_unlisted_origin_receives_no_cors_headers(app_with_origins):
    """The browser blocks the response because the header is absent."""
    from fastapi.testclient import TestClient

    rebuilt = app_with_origins("https://app.example.edu")

    response = TestClient(rebuilt).get(
        "/", headers={"Origin": "https://evil.example.com"}
    )

    assert "access-control-allow-origin" not in response.headers


def test_unset_origins_allow_no_cross_origin_request(app_with_origins):
    from fastapi.testclient import TestClient

    rebuilt = app_with_origins("")

    response = TestClient(rebuilt).get(
        "/", headers={"Origin": "https://app.example.edu"}
    )

    assert "access-control-allow-origin" not in response.headers


def test_wildcard_outside_production_omits_credentials(app_with_origins):
    from fastapi.testclient import TestClient

    rebuilt = app_with_origins("*", environment="development")

    response = TestClient(rebuilt).get(
        "/", headers={"Origin": "https://anything.example.com"}
    )

    assert response.headers.get("access-control-allow-origin") == "*"
    # Must NOT be sent alongside a wildcard.
    assert "access-control-allow-credentials" not in response.headers


def test_shared_app_module_is_restored_after_a_configured_build():
    """Regression for the fixture-teardown leak — order-independent.

    Building a wildcard app must not leave the shared app.main / settings carrying
    that configuration once the context exits. This asserts setup AND restoration
    within one test, so it cannot pass merely because of the order other tests run
    in.
    """
    import app.config
    import app.main
    from fastapi.testclient import TestClient

    original_cors = app.config.settings.CORS_ALLOWED_ORIGINS
    original_environment = app.config.settings.ENVIRONMENT

    probe = {"Origin": "https://anything.example.com"}

    with configured_app("*", environment="development") as built:
        # Inside the context the built app is the wildcard app.
        assert (
            TestClient(built).get("/", headers=probe).headers.get(
                "access-control-allow-origin"
            )
            == "*"
        )

    # After exit: settings are back exactly as they were...
    assert app.config.settings.CORS_ALLOWED_ORIGINS == original_cors
    assert app.config.settings.ENVIRONMENT == original_environment

    # ...and the shared app.main module the context manager rebuilt no longer
    # carries the wildcard config. Deliberately NOT reloaded here — the point is
    # that configured_app already left app.main.app in the restored state.
    leaked = TestClient(app.main.app).get("/", headers=probe).headers.get(
        "access-control-allow-origin"
    )
    assert leaked != "*"
