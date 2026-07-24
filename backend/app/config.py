import ipaddress
import os
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = ".env.test" if os.getenv("APP_ENV") == "test" else ".env"

DEVELOPMENT = "development"
TEST = "test"
PRODUCTION = "production"
# The only accepted deployment environments. An unknown value (a typo like
# "prodution") must be rejected at startup, never silently treated as
# development — that would fail open, permitting wildcard/looser CORS in prod.
ALLOWED_ENVIRONMENTS = (DEVELOPMENT, TEST, PRODUCTION)

WILDCARD_ORIGIN = "*"
_ALLOWED_ORIGIN_SCHEMES = {"http", "https"}
# A DNS label: 1-63 chars of letters/digits/hyphen, no leading or trailing hyphen.
_HOSTNAME_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")


def parse_cors_origins(raw: str | None) -> list[str]:
    """Split the configured origin list into normalised entries.

    Comma-separated, whitespace-insensitive, order-preserving, de-duplicated.
    Trailing slashes are stripped because a browser's Origin header never has
    one, so 'https://app.example.edu/' would otherwise never match.

    An unset or empty value yields no origins rather than a wildcard: absent
    configuration must fail closed.
    """
    if not raw:
        return []

    origins: list[str] = []
    for entry in raw.split(","):
        origin = entry.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)

    return origins


def _is_valid_port(port: str) -> bool:
    """A port is 1-65535, digits only (no '+', no leading/trailing space)."""
    if not port.isdigit():
        return False
    return 1 <= int(port) <= 65535


def _is_valid_hostname(host: str) -> bool:
    """An IPv4/IPv6 literal, or a dotted DNS name with well-formed labels."""
    if not host or len(host) > 253:
        return False
    try:
        ipaddress.ip_address(host)  # IPv4 or IPv6 literal
        return True
    except ValueError:
        pass
    return all(_HOSTNAME_LABEL.match(label) for label in host.split("."))


def _origin_is_well_formed(origin: str) -> bool:
    """True only when `origin` is exactly scheme://host[:port].

    Rejects userinfo (credentials), invalid/empty/out-of-range ports, whitespace
    and control characters, malformed hostnames, and any path/query/params/
    fragment. The wildcard '*' is handled by the caller, not here.
    """
    if origin == WILDCARD_ORIGIN:
        return True

    # No whitespace or control characters anywhere (space is 0x20).
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in origin):
        return False

    try:
        parsed = urlparse(origin)
    except ValueError:
        return False

    if parsed.scheme not in _ALLOWED_ORIGIN_SCHEMES:
        return False

    # An origin carries no userinfo, path, query, params or fragment.
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.path or parsed.query or parsed.params or parsed.fragment:
        return False

    netloc = parsed.netloc

    # IPv6 literal: [::1] optionally followed by :port.
    if netloc.startswith("["):
        close = netloc.find("]")
        if close == -1:
            return False
        host = netloc[1:close]
        remainder = netloc[close + 1:]
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return False
        if remainder:
            return remainder.startswith(":") and _is_valid_port(remainder[1:])
        return True

    # host[:port]
    if ":" in netloc:
        host, _, port = netloc.rpartition(":")
        if not _is_valid_port(port):
            return False
    else:
        host = netloc

    return _is_valid_hostname(host)


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    # Pinned to HS256 (HMAC). The value is deliberately a Literal, not a free
    # string: an EC/RSA algorithm (ES*/RS*) would reach python-jose's ecdsa code
    # path, which the CI dependency audit suppresses PYSEC-2026-1325 for on the
    # basis that it is never reached. Anything but "HS256" is rejected at startup.
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    KEYSTORE_MASTER_SECRET: str
    # Keys the ballot commitment returned on every receipt. Deliberately separate
    # from JWT_SECRET and KEYSTORE_MASTER_SECRET so receipt signing can be rotated
    # without invalidating sessions or losing access to election private keys.
    # No default: a predictable value would let anyone forge a commitment.
    RECEIPT_SIGNING_SECRET: str
    TESTING: bool = False

    # Deployment environment. Only "production" changes behaviour: it forbids a
    # wildcard CORS origin, requires at least one origin, and requires HTTPS.
    ENVIRONMENT: str = "development"

    # Comma-separated browser origins permitted to call this API, e.g.
    # "https://vote.example.edu,https://staging.example.edu".
    # Empty means no cross-origin access, which is safe but blocks a browser
    # frontend — outside production that is the intended default.
    CORS_ALLOWED_ORIGINS: str = ""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == PRODUCTION

    @property
    def cors_allowed_origins(self) -> list[str]:
        return parse_cors_origins(self.CORS_ALLOWED_ORIGINS)

    @property
    def cors_allow_credentials(self) -> bool:
        """Credentials cannot be combined with a wildcard origin.

        The CORS specification forbids `Access-Control-Allow-Origin: *` on
        credentialed requests, and browsers reject the response. Sending both is
        not merely insecure, it silently breaks authenticated cross-origin calls.
        """
        return self.cors_allowed_origins != [WILDCARD_ORIGIN]

    @model_validator(mode="after")
    def validate_receipt_signing_secret(self):
        secret = self.RECEIPT_SIGNING_SECRET

        if len(secret.encode("utf-8")) < 32:
            raise ValueError("RECEIPT_SIGNING_SECRET must be at least 32 bytes")

        if secret in {self.JWT_SECRET, self.KEYSTORE_MASTER_SECRET}:
            raise ValueError(
                "RECEIPT_SIGNING_SECRET must be different from JWT_SECRET "
                "and KEYSTORE_MASTER_SECRET"
            )

        return self

    @model_validator(mode="after")
    def validate_environment(self):
        """Normalise ENVIRONMENT and reject anything outside the known set.

        Defined before validate_cors_allowed_origins so the normalised value is
        in place when the CORS rules read is_production. A typo like 'prodution'
        must fail loudly here rather than fall through to development behaviour
        and quietly permit a wildcard origin.
        """
        normalised = self.ENVIRONMENT.strip().lower()
        if normalised not in ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT must be one of {', '.join(ALLOWED_ENVIRONMENTS)}; "
                f"got {self.ENVIRONMENT!r}"
            )
        self.ENVIRONMENT = normalised
        return self

    @model_validator(mode="after")
    def validate_cors_allowed_origins(self):
        origins = self.cors_allowed_origins

        malformed = [origin for origin in origins if not _origin_is_well_formed(origin)]
        if malformed:
            raise ValueError(
                f"CORS_ALLOWED_ORIGINS contains malformed origins: "
                f"{', '.join(malformed)}. Each entry must be scheme://host[:port] "
                f"with no path, for example https://vote.example.edu"
            )

        if WILDCARD_ORIGIN in origins and len(origins) > 1:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS may be '*' or a list of specific origins, "
                "not both"
            )

        if self.is_production:
            if WILDCARD_ORIGIN in origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must not use the wildcard '*' when "
                    "ENVIRONMENT=production. List the exact frontend origins."
                )

            if not origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must list at least one origin when "
                    "ENVIRONMENT=production"
                )

            insecure_origins = [
                origin for origin in origins if urlparse(origin).scheme != "https"
            ]
            if insecure_origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must use https for every origin when "
                    "ENVIRONMENT=production; insecure origins: "
                    f"{', '.join(insecure_origins)}"
                )

        return self


settings = Settings()
