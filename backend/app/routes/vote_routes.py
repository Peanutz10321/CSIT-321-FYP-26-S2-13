import uuid
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import now_sgt
from app.database import get_db
from app.models.user import User
from app.models.election import Election, ElectionStatus, BallotType
from app.models.candidate import Candidate
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.ballot import Ballot, BulletinStatus
from app.schemas.vote_schema import (
    VoteCreate,
    VoteResponse,
    VoteHistoryResponse,
    VoteVerificationResponse,
)
from app.security.audit import log_event
from app.security.ballot_commitment import (
    ballot_configuration_digest,
    commitment_matches,
    compute_ballot_commitment,
    compute_commitment_for_ballot,
)
from app.security.security import require_voter
from app.security.homomorphic import deserialize_public_key, encrypt_ballot
from app.services.election_lock import lock_election_for_vote


router = APIRouter(prefix="/votes", tags=["Votes"])


@router.post("/", response_model=VoteResponse, status_code=status.HTTP_201_CREATED)
def submitVote(
    payload: VoteCreate,
    db: Session = Depends(get_db),
    current_voter: User = Depends(require_voter),
):
    # Take the shared election lock FIRST, so status and deadline are read under
    # it and stay valid until this transaction commits. Without the lock a close
    # could tally between the status check and the insert below, leaving this
    # voter holding a valid receipt for a ballot that was never counted.
    #
    # A close holds the row exclusively, so this call blocks while one is running
    # and then re-reads the committed state — which is why the status check below
    # correctly rejects the vote once the election has been completed.
    election = lock_election_for_vote(db, payload.election_id)

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.status != ElectionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active elections can be voted in",
        )

    # start_date and end_date are stored as naive SGT (UTC+8).
    now = now_sgt()

    if now < election.start_date or now > election.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election is not currently within its voting period",
        )

    # Resolve the selection from the two supported request forms. candidate_ids is
    # None when omitted and [] for an explicit abstention — those are distinct.
    has_single = payload.candidate_id is not None
    has_multi = payload.candidate_ids is not None

    if has_single and has_multi:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either candidate_id or candidate_ids, not both",
        )

    if not has_single and not has_multi:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A candidate selection is required (use candidate_id, or candidate_ids for multi-select and abstention)",
        )

    selected_ids = list(payload.candidate_ids) if has_multi else [payload.candidate_id]

    # Never silently deduplicate — a repeated id is a client error.
    if len(selected_ids) != len(set(selected_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate candidate selections are not allowed",
        )

    all_candidates = (
        db.query(Candidate)
        .filter(Candidate.election_id == payload.election_id)
        .all()
    )
    candidate_by_id = {candidate.id: candidate for candidate in all_candidates}

    for selected_id in selected_ids:
        if selected_id not in candidate_by_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Candidate does not belong to this election",
            )

    # Enforce the ballot configuration. An empty selection is always a valid
    # abstention; otherwise a single ballot allows exactly one and a multi ballot
    # allows up to max_selections. Over-long selections are rejected, not truncated.
    if election.ballot_type == BallotType.single:
        if len(selected_ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A single-choice ballot allows at most one selection",
            )
    else:
        if len(selected_ids) > election.max_selections:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You may select at most {election.max_selections} candidate(s) for this ballot",
            )

    election_voter = (
        db.query(ElectionVoter)
        .filter(
            ElectionVoter.election_id == payload.election_id,
            ElectionVoter.voter_id == current_voter.id,
        )
        .first()
    )

    if not election_voter:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not eligible to vote in this election",
        )

    if election_voter.eligibility_status != EligibilityStatus.eligible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your voting eligibility has been revoked",
        )

    existing_ballot = (
        db.query(Ballot)
        .filter(Ballot.election_voter_id == election_voter.id)
        .first()
    )

    if existing_ballot or election_voter.voted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already voted in this election",
        )

    if not election.public_key_n:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Election encryption keys are not initialized",
        )

    candidate_ids = [str(c.id) for c in all_candidates]
    selected_ids_str = [str(sid) for sid in selected_ids]

    public_key = deserialize_public_key(election.public_key_n)
    # Multi-hot encrypted vector: E(1) per selection, E(0) for the rest, all-zero for
    # an abstention. No plaintext choice is stored anywhere on the ballot.
    encrypted_vote = encrypt_ballot(public_key, candidate_ids, selected_ids_str)

    receipt_code = f"RCPT-{uuid.uuid4().hex[:12].upper()}"

    # The id is generated here rather than at flush time because it is part of the
    # committed input. The commitment covers the complete ciphertext, so altering a
    # stored ballot invalidates it — the previous salted hash covered neither the
    # ciphertext nor anything reproducible, so it could not be verified at all.
    # No plaintext choice enters the commitment.
    ballot_id = uuid.uuid4()
    ballot_commitment = compute_ballot_commitment(
        ballot_id=ballot_id,
        election_id=payload.election_id,
        receipt_code=receipt_code,
        encrypted_vote=encrypted_vote,
        ballot_config_digest=ballot_configuration_digest(
            election.ballot_type.value,
            election.max_selections,
            candidate_ids,
        ),
        submitted_at=now,
    )

    ballot = Ballot(
        id=ballot_id,
        election_id=payload.election_id,
        election_voter_id=election_voter.id,
        encrypted_vote=encrypted_vote,
        ballot_commitment=ballot_commitment,
        receipt_code=receipt_code,
        submitted_at=now,
        bulletin_status=BulletinStatus.published,
    )

    election_voter.voted_at = now

    db.add(ballot)
    try:
        db.flush()  # assigns ballot.id; raises IntegrityError on double-vote
        # Audit the act of voting only — never the choice
        log_event(
            db,
            actor_user_id=current_voter.id,
            action="vote_cast",
            entity_type="ballot",
            entity_id=ballot.id,
            details=f"election={payload.election_id}",
        )
        db.commit()
    except IntegrityError:
        # Unique constraint on ballot.election_voter_id: a concurrent request
        # already inserted this voter's ballot between our check and commit.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already voted in this election",
        )
    db.refresh(ballot)

    # The selected names are derived from THIS request only, before the choice is
    # encrypted away. They are never persisted and never recoverable from the stored
    # ballot afterwards (see getVoteDetails). candidate_name stays populated for a
    # single selection to keep legacy clients working.
    selected_names = [candidate_by_id[sid].name for sid in selected_ids]
    single_name = selected_names[0] if len(selected_names) == 1 else None

    return VoteResponse(
        id=ballot.id,
        election_id=ballot.election_id,
        election_voter_id=ballot.election_voter_id,
        encrypted_vote=ballot.encrypted_vote,
        ballot_commitment=ballot.ballot_commitment,
        receipt_code=ballot.receipt_code,
        submitted_at=ballot.submitted_at,
        bulletin_status=ballot.bulletin_status.value,
        candidate_name=single_name,
        candidate_names=selected_names,
        abstained=(len(selected_ids) == 0),
    )


@router.get("/history", response_model=list[VoteHistoryResponse])
def getVoteHistory(
    search: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_voter: User = Depends(require_voter),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date period please try again",
        )

    query = (
        db.query(Ballot, Election)
        .join(ElectionVoter, Ballot.election_voter_id == ElectionVoter.id)
        .join(Election, Ballot.election_id == Election.id)
        .filter(ElectionVoter.voter_id == current_voter.id)
    )

    if search:
        query = query.filter(Election.title.ilike(f"%{search}%"))
    if start_date:
        query = query.filter(Ballot.submitted_at >= datetime(start_date.year, start_date.month, start_date.day))
    if end_date:
        query = query.filter(Ballot.submitted_at <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59))

    records = query.order_by(Ballot.submitted_at.desc()).all()

    return [
        VoteHistoryResponse(
            id=ballot.id,
            election_id=ballot.election_id,
            election_title=election.title,
            receipt_code=ballot.receipt_code,
            submitted_at=ballot.submitted_at,
            bulletin_status=ballot.bulletin_status.value,
        )
        for ballot, election in records
    ]


@router.get("/{vote_id}/verify", response_model=VoteVerificationResponse)
def verifyVote(
    vote_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_voter: User = Depends(require_voter),
):
    """
    Recompute a stored ballot's commitment and compare it with the stored value.

    Detects modification of the ciphertext, receipt code, submission time, ballot
    id, election, or ballot configuration made through database access alone.

    It does NOT prove the ballot was counted as cast. The backend holds the
    signing secret, so a compromised backend can produce a matching commitment
    for a substituted ballot. See app/security/ballot_commitment.py.
    """
    ballot = (
        db.query(Ballot)
        .join(ElectionVoter, Ballot.election_voter_id == ElectionVoter.id)
        .filter(
            Ballot.id == vote_id,
            ElectionVoter.voter_id == current_voter.id,
        )
        .first()
    )

    if not ballot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote not found",
        )

    election = db.get(Election, ballot.election_id)
    candidate_ids = [
        str(candidate_id)
        for (candidate_id,) in db.query(Candidate.id)
        .filter(Candidate.election_id == ballot.election_id)
        .all()
    ]

    expected = compute_commitment_for_ballot(ballot, election, candidate_ids)
    verified = commitment_matches(expected, ballot.ballot_commitment)

    return VoteVerificationResponse(
        ballot_id=ballot.id,
        election_id=ballot.election_id,
        receipt_code=ballot.receipt_code,
        verified=verified,
        detail=(
            "Ballot matches its commitment."
            if verified
            else "Ballot does not match its commitment. It was modified after "
                 "submission, or it predates the commitment scheme."
        ),
    )


@router.get("/{vote_id}", response_model=VoteResponse)
def getVoteDetails(
    vote_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_voter: User = Depends(require_voter),
):
    ballot = (
        db.query(Ballot)
        .join(ElectionVoter, Ballot.election_voter_id == ElectionVoter.id)
        .filter(
            Ballot.id == vote_id,
            ElectionVoter.voter_id == current_voter.id,
        )
        .first()
    )

    if not ballot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote not found",
        )

    # candidate_name stays None by design: the ballot is Paillier-encrypted and
    # the server cannot recover an individual choice after submission. The
    # plaintext choice only appears in the immediate submitVote response.
    return VoteResponse(
        id=ballot.id,
        election_id=ballot.election_id,
        election_voter_id=ballot.election_voter_id,
        encrypted_vote=ballot.encrypted_vote,
        ballot_commitment=ballot.ballot_commitment,
        receipt_code=ballot.receipt_code,
        submitted_at=ballot.submitted_at,
        bulletin_status=ballot.bulletin_status.value,
        candidate_name=None,
    )