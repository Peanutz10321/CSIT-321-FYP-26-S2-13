"""
Known-answer tests pinning the frozen v1 audit hash.

These lock the exact canonical string and SHA-256 digest for fixed inputs. If
either changes, ``app/security/audit_hash_v1.py`` was edited in a way that breaks
every existing chain and disagrees with migration 0004's backfill.

If a new canonical form is genuinely needed, add an ``audit_hash_v2`` module and
a v2 known-answer test — do NOT update the constants below.
"""

from datetime import datetime

from app.security import audit_hash_v1
from app.security.audit import canonical_entry, compute_entry_hash


# A fully-specified entry. Every field is non-null so the pin covers all of them.
FIXED_ENTRY = dict(
    sequence_number=7,
    previous_hash="a" * 64,
    actor_user_id="11111111-1111-1111-1111-111111111111",
    action="election_created",
    entity_type="election",
    entity_id="22222222-2222-2222-2222-222222222222",
    details='{"status":"draft"}',
    created_at=datetime(2026, 7, 24, 9, 30, 15, 123456),
)

FIXED_ENTRY_CANONICAL = (
    '{"action":"election_created",'
    '"actor_user_id":"11111111-1111-1111-1111-111111111111",'
    '"created_at":"2026-07-24T09:30:15.123456",'
    '"details":"{\\"status\\":\\"draft\\"}",'
    '"entity_id":"22222222-2222-2222-2222-222222222222",'
    '"entity_type":"election",'
    '"previous_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    '"sequence_number":7}'
)

FIXED_ENTRY_DIGEST = "45c946cc452e0880ff40121911d7a718bbe74b9150e0f949c0fdb46ef80a07c7"

# An all-null entry (the genesis-style shape), pinned separately.
NULL_ENTRY = dict(
    sequence_number=1,
    previous_hash=audit_hash_v1.GENESIS_HASH,
    actor_user_id=None,
    action="x",
    entity_type="y",
    entity_id=None,
    details=None,
    created_at=None,
)

NULL_ENTRY_DIGEST = "38c510671b5245aef052ef0f327d494b738186ac8eb8ef33f3fe1bb96e7ede91"


def test_version_is_one():
    assert audit_hash_v1.AUDIT_HASH_VERSION == 1


def test_genesis_hash_is_sixty_four_zeroes():
    assert audit_hash_v1.GENESIS_HASH == "0" * 64
    assert len(audit_hash_v1.GENESIS_HASH) == 64


def test_canonical_string_is_pinned():
    assert canonical_entry(**FIXED_ENTRY) == FIXED_ENTRY_CANONICAL


def test_digest_is_pinned():
    assert compute_entry_hash(**FIXED_ENTRY) == FIXED_ENTRY_DIGEST


def test_null_entry_digest_is_pinned():
    assert compute_entry_hash(**NULL_ENTRY) == NULL_ENTRY_DIGEST


def test_audit_module_reexports_the_same_implementation():
    """Callers importing from app.security.audit must get the frozen v1 code."""
    assert compute_entry_hash is audit_hash_v1.compute_entry_hash
    assert canonical_entry is audit_hash_v1.canonical_entry


def test_uuid_object_and_string_hash_identically():
    import uuid

    as_string = compute_entry_hash(**FIXED_ENTRY)
    as_object = compute_entry_hash(
        **{**FIXED_ENTRY, "actor_user_id": uuid.UUID(FIXED_ENTRY["actor_user_id"])}
    )
    assert as_string == as_object == FIXED_ENTRY_DIGEST
