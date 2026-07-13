"""
Election private-key storage.

The Paillier private key must never sit in the elections table: anyone with
DB read access could decrypt every individual ballot, defeating the point of
homomorphic tallying. Keys are Fernet-encrypted under KEYSTORE_MASTER_SECRET
(environment-only) and stored in the separate election_keys table, fetched
exclusively at tally time.

Known, documented limitation: this is single-authority decryption — an
attacker holding BOTH the master secret and DB access can still decrypt.
A production system would use threshold decryption.
"""

from cryptography.fernet import Fernet
from phe.paillier import PaillierPrivateKey, PaillierPublicKey
from sqlalchemy.orm import Session

from app.config import settings
from app.models.election import Election
from app.models.election_key import ElectionKey
from app.security.homomorphic import (
    deserialize_private_key,
    deserialize_public_key,
    generate_keypair,
    serialize_private_key,
    serialize_public_key,
)


class ElectionKeyMissingError(Exception):
    """No stored private key for this election."""


def _fernet() -> Fernet:
    return Fernet(settings.KEYSTORE_MASTER_SECRET.encode())


def create_and_store_keypair(db: Session, election: Election) -> PaillierPublicKey:
    """
    Generate a Paillier keypair for an election. The public key goes on the
    election row; the private key is encrypted and stored in election_keys.
    Replaces any previous key for the election (re-activation regenerates).
    Caller must have flushed the election (election.id must exist) and commits.
    """
    public_key, private_key = generate_keypair()

    encrypted = _fernet().encrypt(serialize_private_key(private_key).encode()).decode()

    key_row = db.get(ElectionKey, election.id)
    if key_row is None:
        db.add(ElectionKey(election_id=election.id, encrypted_private_key=encrypted))
    else:
        key_row.encrypted_private_key = encrypted

    election.public_key_n = serialize_public_key(public_key)
    return public_key


def load_private_key(db: Session, election: Election) -> PaillierPrivateKey:
    """
    Decrypt and return the election's private key. Call at tally time only —
    never cache the result on the election object or in a response.
    """
    key_row = db.get(ElectionKey, election.id)
    if key_row is None:
        raise ElectionKeyMissingError(
            f"No private key stored for election {election.id}"
        )

    serialized = _fernet().decrypt(key_row.encrypted_private_key.encode()).decode()
    public_key = deserialize_public_key(election.public_key_n)
    return deserialize_private_key(serialized, public_key)
