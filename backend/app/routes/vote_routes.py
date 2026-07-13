import hashlib
import secrets
import uuid
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import now_sgt
from app.database import get_db
from app.models.user import User
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.ballot import Ballot, BulletinStatus
from app.schemas.vote_schema import VoteCreate, VoteResponse, VoteHistoryResponse
from app.security.audit import log_event
from app.security.security import require_voter
from app.security.homomorphic import deserialize_public_key, encrypt_vote


router = APIRouter(prefix="/votes", tags=["Votes"])


@router.post("/", response_model=VoteResponse, status_code=status.HTTP_201_CREATED)
def submitVote(
    payload: VoteCreate,
    db: Session = Depends(get_db),
    current_voter: User = Depends(require_voter),
):
    election = db.query(Election).filter(Election.id == payload.election_id).first()

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

    candidate = (
        db.query(Candidate)
        .filter(
            Candidate.id == payload.candidate_id,
            Candidate.election_id == payload.election_id,
        )
        .first()
    )

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate does not belong to this election",
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

    all_candidates = (
        db.query(Candidate)
        .filter(Candidate.election_id == payload.election_id)
        .all()
    )
    candidate_ids = [str(c.id) for c in all_candidates]

    public_key = deserialize_public_key(election.public_key_n)
    encrypted_vote = encrypt_vote(public_key, candidate_ids, str(payload.candidate_id))

    # The hash is an integrity/receipt token. It must never include the
    # candidate choice: the input space is tiny, so a DB reader could
    # brute-force sha256(election:voter:candidate:time) and unmask the vote.
    salt = secrets.token_hex(16)
    vote_hash = hashlib.sha256(
        f"{salt}:{payload.election_id}:{election_voter.id}".encode()
    ).hexdigest()

    receipt_code = f"RCPT-{uuid.uuid4().hex[:12].upper()}"

    ballot = Ballot(
        election_id=payload.election_id,
        election_voter_id=election_voter.id,
        encrypted_vote=encrypted_vote,
        vote_hash=vote_hash,
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

    # candidate_name is only known here, before the choice is encrypted away.
    # It is never recoverable from the stored ballot (see getVoteDetails).
    return VoteResponse(
        id=ballot.id,
        election_id=ballot.election_id,
        election_voter_id=ballot.election_voter_id,
        encrypted_vote=ballot.encrypted_vote,
        vote_hash=ballot.vote_hash,
        receipt_code=ballot.receipt_code,
        submitted_at=ballot.submitted_at,
        bulletin_status=ballot.bulletin_status.value,
        candidate_name=candidate.name,
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
        vote_hash=ballot.vote_hash,
        receipt_code=ballot.receipt_code,
        submitted_at=ballot.submitted_at,
        bulletin_status=ballot.bulletin_status.value,
        candidate_name=None,
    )