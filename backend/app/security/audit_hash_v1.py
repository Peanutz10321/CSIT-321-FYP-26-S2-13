"""
Frozen v1 canonicalisation and hashing for the audit chain.

THIS MODULE IS IMMUTABLE. Its output is baked into every audit row ever written
and into migration 0004's backfill. Changing the canonical form or the hash here
would change the digest of a fixed input, which:

  * makes every existing chain fail verification, and
  * makes a fresh run of migration 0004 disagree with a database migrated
    earlier.

So this is version 1 and it stays version 1. A future format MUST be added as a
separate ``audit_hash_v2`` module with its own version tag, never by editing the
functions below. ``tests/test_audit_hash_v1.py`` pins the exact canonical string
and SHA-256 digest for a fixed input; that test failing means this file was
changed in a way that breaks compatibility.

The canonical form is sorted-key JSON with no incidental whitespace, so the same
entry serialises identically on any platform and Python version. UUID-ish values
are normalised to one spelling and timestamps to fixed microsecond precision, so
a PostgreSQL ``UUID``/``datetime`` and a SQLite string hash the same.
"""

from __future__ import annotations

import hashlib
import json
import uuid as uuid_module
from datetime import datetime


# The version of this canonicalisation. Never change it; add a v2 module instead.
AUDIT_HASH_VERSION = 1

# previous_hash of the first entry. A fixed non-null sentinel keeps the column
# NOT NULL and makes the genesis entry explicit.
GENESIS_HASH = "0" * 64


def _uuid_text(value) -> str | None:
    """Normalise a UUID-ish value to one canonical string form.

    The same identifier can reach us as a ``UUID`` object (PostgreSQL) or as a
    string with or without hyphens (SQLite, raw SQL). All of them must hash
    identically, or verification would fail purely because of the driver.
    """
    if value is None:
        return None

    try:
        return str(uuid_module.UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        return str(value)


def _timestamp_text(value: datetime | None) -> str | None:
    """Fixed-precision timestamp text, so the hash never depends on formatting."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")

    return str(value)


def canonical_entry(
    *,
    sequence_number: int,
    previous_hash: str,
    actor_user_id,
    action: str,
    entity_type: str,
    entity_id=None,
    details: str | None = None,
    created_at: datetime | None = None,
) -> str:
    """Deterministic JSON for one entry — the exact bytes that get hashed.

    Sorted keys and separators without whitespace mean the same entry always
    serialises to the same string, on any platform and in any Python version.
    """
    payload = {
        "sequence_number": int(sequence_number),
        "previous_hash": previous_hash,
        "actor_user_id": _uuid_text(actor_user_id),
        "action": action,
        "entity_type": entity_type,
        "entity_id": _uuid_text(entity_id),
        "details": details,
        "created_at": _timestamp_text(created_at),
    }

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_entry_hash(**fields) -> str:
    """SHA-256 of an entry's canonical JSON, as lowercase hex."""
    return hashlib.sha256(canonical_entry(**fields).encode("utf-8")).hexdigest()
