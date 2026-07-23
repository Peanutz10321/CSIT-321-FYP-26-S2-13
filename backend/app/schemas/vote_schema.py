from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VoteCreate(BaseModel):
    election_id: UUID
    # Two supported request forms (exactly one must be supplied):
    #   legacy single:     {"candidate_id": "..."}
    #   multi / abstain:    {"candidate_ids": ["...", ...]}   ([] == explicit abstention)
    # candidate_ids stays None when omitted so the route can tell an omitted field
    # from an explicitly-empty abstention list.
    candidate_id: UUID | None = None
    candidate_ids: list[UUID] | None = None


class VoteResponse(BaseModel):
    id: UUID
    election_id: UUID
    election_voter_id: UUID
    encrypted_vote: str
    # HMAC commitment over this ballot's canonical input, including its complete
    # ciphertext. Returned in the immediate receipt and stored with the ballot.
    ballot_commitment: str
    receipt_code: str
    submitted_at: datetime
    bulletin_status: str
    # Choice echo — derived from the current request and returned only in the
    # immediate submit response (never reconstructed from the stored ballot):
    #   candidate_name  : the single selection's name (legacy field; None otherwise)
    #   candidate_names : all selected names ([] for an abstention)
    #   abstained       : True for an explicit abstention (None when unknown/stored)
    candidate_name: str | None = None
    candidate_names: list[str] = []
    abstained: bool | None = None

    class Config:
        from_attributes = True


class VoteHistoryResponse(BaseModel):
    id: UUID
    election_id: UUID
    election_title: str
    receipt_code: str
    submitted_at: datetime
    bulletin_status: str


class VoteVerificationResponse(BaseModel):
    """Result of recomputing a stored ballot's commitment.

    `verified` false means a committed field changed after the ballot was cast,
    or the ballot predates the commitment scheme. It does NOT prove the vote was
    counted as cast: the backend holds the signing secret, so this detects
    tampering only by a party that lacks that key.
    """

    ballot_id: UUID
    election_id: UUID
    receipt_code: str
    verified: bool
    detail: str