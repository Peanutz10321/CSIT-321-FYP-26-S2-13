import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.ballot import Ballot, BulletinStatus
from app.schemas.vote_schema import VoteCreate, VoteResponse, VoteHistoryResponse
from app.security.security import require_student


router = APIRouter(prefix="/votes", tags=["votes"])


@router.post("/", response_model=VoteResponse, status_code=status.HTTP_201_CREATED)
def create_vote(
    payload: VoteCreate,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
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

    now = datetime.utcnow()

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
            ElectionVoter.student_id == current_student.id,
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

    # Placeholder encryption for MVP flow.
    # Later, replace this with homomorphic encryption.
    encrypted_vote = f"encrypted_placeholder:{payload.candidate_id}"

    vote_hash = hashlib.sha256(
        f"{payload.election_id}:{current_student.id}:{payload.candidate_id}:{now.isoformat()}".encode()
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
    db.commit()
    db.refresh(ballot)

    return ballot


@router.get("/history", response_model=list[VoteHistoryResponse])
def view_vote_history(
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
):
    records = (
        db.query(Ballot, Election)
        .join(ElectionVoter, Ballot.election_voter_id == ElectionVoter.id)
        .join(Election, Ballot.election_id == Election.id)
        .filter(ElectionVoter.student_id == current_student.id)
        .order_by(Ballot.submitted_at.desc())
        .all()
    )

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
def view_vote_details(
    vote_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
):
    ballot = (
        db.query(Ballot)
        .join(ElectionVoter, Ballot.election_voter_id == ElectionVoter.id)
        .filter(
            Ballot.id == vote_id,
            ElectionVoter.student_id == current_student.id,
        )
        .first()
    )

    if not ballot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote not found",
        )

    return ballot