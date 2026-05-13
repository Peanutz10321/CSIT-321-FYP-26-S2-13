import json

from phe import paillier
from phe.paillier import EncryptedNumber, PaillierPublicKey, PaillierPrivateKey

KEY_SIZE = 2048


def generate_keypair() -> tuple[PaillierPublicKey, PaillierPrivateKey]:
    return paillier.generate_paillier_keypair(n_length=KEY_SIZE)


def serialize_public_key(pk: PaillierPublicKey) -> str:
    return str(pk.n)


def deserialize_public_key(n_str: str) -> PaillierPublicKey:
    return PaillierPublicKey(int(n_str))


def serialize_private_key(sk: PaillierPrivateKey) -> str:
    return json.dumps({"p": str(sk.p), "q": str(sk.q)})


def deserialize_private_key(sk_json: str, pk: PaillierPublicKey) -> PaillierPrivateKey:
    data = json.loads(sk_json)
    return PaillierPrivateKey(pk, int(data["p"]), int(data["q"]))


def _enc_to_dict(enc: EncryptedNumber) -> dict:
    return {"c": str(enc.ciphertext(be_secure=False)), "e": enc.exponent}


def _dict_to_enc(data: dict, pk: PaillierPublicKey) -> EncryptedNumber:
    return EncryptedNumber(pk, int(data["c"]), data["e"])


def encrypt_vote(pk: PaillierPublicKey, candidate_ids: list[str], voted_id: str) -> str:
    """
    Encrypts a one-hot vote vector using Paillier.
    The chosen candidate gets E(1); all others get E(0).
    Returns a JSON string: {candidate_id: {c, e}}.
    """
    result = {
        cid: _enc_to_dict(pk.encrypt(1 if cid == voted_id else 0))
        for cid in candidate_ids
    }
    return json.dumps(result)


def homomorphic_tally(
    pk: PaillierPublicKey,
    sk: PaillierPrivateKey,
    encrypted_votes: list[str],
    candidate_ids: list[str],
) -> dict[str, int]:
    """
    Homomorphically sums all encrypted ballots, then decrypts per-candidate totals.
    Individual votes are never decrypted — only the aggregate is.
    Returns {candidate_id_str: vote_count}.
    """
    totals: dict[str, EncryptedNumber] = {}

    for vote_json in encrypted_votes:
        vote_data = json.loads(vote_json)
        for cid in candidate_ids:
            if cid not in vote_data:
                continue
            enc = _dict_to_enc(vote_data[cid], pk)
            totals[cid] = totals[cid] + enc if cid in totals else enc

    return {
        cid: sk.decrypt(totals[cid]) if cid in totals else 0
        for cid in candidate_ids
    }
