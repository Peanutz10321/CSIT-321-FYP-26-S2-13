from datetime import datetime, date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.core.time import now_sgt
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.models.election import Election, ElectionStatus, BallotType
from app.models.candidate import Candidate
from app.models.ballot import Ballot
from app.models.candidate_result import CandidateResult
from app.schemas.election_schema import ElectionCreate, ElectionDraftCreate, ElectionResponse, ElectionUpdate, ExtendDeadlineRequest
from app.security.audit import log_event
from app.security.security import get_current_user, require_organizer
from app.security.keystore import create_and_store_keypair, load_private_key
from app.security.homomorphic import deserialize_public_key, homomorphic_tally

from sqlalchemy.exc import IntegrityError
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.schemas.election_voter_schema import (
    AddElectionVoterRequest,
    ElectionVoterResponse,
    ElectionVoterDetailResponse,
)


router = APIRouter(prefix="/elections", tags=["Elections"])


def _eligibility_details(change: str, voter_id: UUID) -> str:
    """
    Stable, minimal details string for an eligibility_changed audit event. Records
    only the administrative change type and the target voter's user UUID — never an
    email, name, external id, or any ballot/secret material.
    """
    return f"change={change};voter_id={voter_id}"


def _validate_ballot_configuration(
    ballot_type: BallotType,
    max_selections: int,
    candidate_count: int | None = None,
) -> None:
    """
    Enforce ballot configuration rules using the project's 400 convention.

    - max_selections must be at least 1 (never zero or negative);
    - a single-choice ballot must allow exactly one selection;
    - once the candidate list is final (create-active / activation), max_selections
      may not exceed the number of candidates.

    candidate_count is left None for drafts, whose candidate list is not yet final.
    """
    if max_selections < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_selections must be at least 1",
        )

    if ballot_type == BallotType.single and max_selections != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A single-choice ballot must have max_selections equal to 1",
        )

    if candidate_count is not None and max_selections > candidate_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_selections cannot exceed the number of candidates",
        )


@router.post("/draft", response_model=ElectionResponse, status_code=status.HTTP_201_CREATED)
def createElectionDraft(
    payload: ElectionDraftCreate,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    # Drafts stay relaxed (candidate list not final), so no candidate-count check.
    _validate_ballot_configuration(payload.ballot_type, payload.max_selections)

    election = Election(
        organizer_id=current_organizer.id,
        title=payload.title,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=ElectionStatus.draft,
        ballot_type=payload.ballot_type,
        max_selections=payload.max_selections,
    )

    db.add(election)
    db.flush()

    for index, candidate_data in enumerate(payload.candidates, start=1):
        candidate = Candidate(
            election_id=election.id,
            name=candidate_data.name,
            description=candidate_data.description,
            photo_url=candidate_data.photo_url,
            display_order=candidate_data.display_order or index,
        )
        db.add(candidate)

    db.commit()

    return (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )


@router.post("/", response_model=ElectionResponse, status_code=status.HTTP_201_CREATED)
def createElection(
    payload: ElectionCreate,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    if not payload.title or not payload.title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title is required",
        )

    if not payload.start_date or not payload.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date and end date are required",
        )

    if payload.end_date <= payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
        )

    if not payload.candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one candidate is required",
        )

    if not payload.eligible_voter_external_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one eligible voter is required",
        )

    # This path creates an active election with a final candidate list, so the
    # candidate-count rule applies here too.
    _validate_ballot_configuration(
        payload.ballot_type,
        payload.max_selections,
        candidate_count=len(payload.candidates),
    )

    election = Election(
        organizer_id=current_organizer.id,
        title=payload.title,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=ElectionStatus.active,
        ballot_type=payload.ballot_type,
        max_selections=payload.max_selections,
    )

    db.add(election)
    db.flush()  # gives election.id before commit

    create_and_store_keypair(db, election)
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="key_generated",
        entity_type="election",
        entity_id=election.id,
    )

    for index, candidate_data in enumerate(payload.candidates, start=1):
        candidate = Candidate(
            election_id=election.id,
            name=candidate_data.name,
            description=candidate_data.description,
            photo_url=candidate_data.photo_url,
            display_order=candidate_data.display_order or index,
        )
        db.add(candidate)

    for external_id in payload.eligible_voter_external_ids:
        voter = db.query(User).filter(User.external_id == external_id).first()
        if not voter:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voter '{external_id}' not found",
            )
        if voter.role != UserRole.voter:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{external_id}' is not a voter account",
            )
        if voter.status != UserStatus.active:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Voter '{external_id}' is not active",
            )
        db.add(ElectionVoter(
            election_id=election.id,
            voter_id=voter.id,
            eligibility_status=EligibilityStatus.eligible,
        ))
        # One audit event per voter actually added, in the same transaction — a later
        # rollback in this loop discards these along with the memberships.
        log_event(
            db,
            actor_user_id=current_organizer.id,
            action="eligibility_changed",
            entity_type="election",
            entity_id=election.id,
            details=_eligibility_details("added", voter.id),
        )

    db.commit()

    created_election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )

    return created_election

@router.get("/active", response_model=list[ElectionResponse])
def getActiveElections(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    query = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.status == ElectionStatus.active)
        .filter(Election.end_date >= now_sgt())
    )

    if current_user.role == UserRole.organizer:
        query = query.filter(Election.organizer_id == current_user.id)

    elif current_user.role == UserRole.voter:
        query = (
            query.join(ElectionVoter, ElectionVoter.election_id == Election.id)
            .filter(ElectionVoter.voter_id == current_user.id)
            .filter(ElectionVoter.eligibility_status == EligibilityStatus.eligible)
        )

    if search:
        query = query.filter(Election.title.ilike(f"%{search}%"))

    return query.order_by(Election.start_date.desc()).all()

@router.get("/history", response_model=list[ElectionResponse])
def getElectionHistory(
    search: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date period please try again",
        )

    query = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(
            or_(
                Election.status == ElectionStatus.completed,
                and_(
                    Election.status == ElectionStatus.active,
                    Election.end_date < now_sgt(),
                ),
            )
        )
    )

    if current_user.role == UserRole.organizer:
        query = query.filter(Election.organizer_id == current_user.id)

    elif current_user.role == UserRole.voter:
        query = (
            query.join(ElectionVoter, ElectionVoter.election_id == Election.id)
            .filter(ElectionVoter.voter_id == current_user.id)
        )

    if search:
        query = query.filter(Election.title.ilike(f"%{search}%"))
    if start_date:
        query = query.filter(Election.end_date >= datetime(start_date.year, start_date.month, start_date.day))
    if end_date:
        query = query.filter(Election.end_date <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59))

    return query.order_by(Election.created_at.desc()).all()

@router.get("/drafts", response_model=list[ElectionResponse])
def getElectionDrafts(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    query = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.status == ElectionStatus.draft)
        .filter(Election.organizer_id == current_organizer.id)
    )

    if search:
        query = query.filter(Election.title.ilike(f"%{search}%"))

    return query.order_by(Election.created_at.desc()).all()

@router.get("/{election_id}", response_model=ElectionResponse)
def getElectionDetails(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    election = (
        db.query(Election)
        .options(joinedload(Election.candidates), joinedload(Election.organizer))
        .filter(Election.id == election_id)
        .first()
    )

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if current_user.role == UserRole.organizer:
        if election.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view elections that you created",
            )

    elif current_user.role == UserRole.voter:
        voter_record = (
            db.query(ElectionVoter)
            .filter(
                ElectionVoter.election_id == election.id,
                ElectionVoter.voter_id == current_user.id,
            )
            .first()
        )

        if not voter_record:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not eligible to view this election",
            )

    return election

@router.put("/{election_id}", response_model=ElectionResponse)
def updateElection(
    election_id: UUID,
    payload: ElectionUpdate,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election_id)
        .first()
    )

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update elections that you created",
        )

    if election.status != ElectionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft elections can be fully updated",
        )

    if payload.start_date and payload.end_date and payload.end_date <= payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
        )

    if payload.title is not None:
        election.title = payload.title

    if payload.description is not None:
        election.description = payload.description

    if payload.start_date is not None:
        election.start_date = payload.start_date

    if payload.end_date is not None:
        election.end_date = payload.end_date

    # Optional: replace candidate list if candidates are provided
    if payload.candidates is not None:
        if len(payload.candidates) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one candidate is required",
            )

        db.query(Candidate).filter(Candidate.election_id == election.id).delete()

        for index, candidate_data in enumerate(payload.candidates, start=1):
            candidate = Candidate(
                election_id=election.id,
                name=candidate_data.name,
                description=candidate_data.description,
                photo_url=candidate_data.photo_url,
                display_order=candidate_data.display_order or index,
            )
            db.add(candidate)

    # Validate the resulting ballot configuration (merging any provided fields with
    # what is already stored). Still a draft, so the candidate-count rule is deferred
    # to activation.
    effective_ballot_type = (
        payload.ballot_type if payload.ballot_type is not None else election.ballot_type
    )
    effective_max_selections = (
        payload.max_selections if payload.max_selections is not None else election.max_selections
    )
    _validate_ballot_configuration(effective_ballot_type, effective_max_selections)

    if payload.ballot_type is not None:
        election.ballot_type = payload.ballot_type

    if payload.max_selections is not None:
        election.max_selections = payload.max_selections

    db.commit()

    updated_election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )

    return updated_election

@router.delete("/{election_id}", status_code=status.HTTP_204_NO_CONTENT)
def deleteElection(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    election = (
        db.query(Election)
        .filter(Election.id == election_id)
        .first()
    )

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete elections that you created",
        )

    if election.status != ElectionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft elections can be deleted",
        )

    db.delete(election)
    db.commit()


@router.patch("/{election_id}/extend-deadline", response_model=ElectionResponse)
def extendElectionDeadline(
    election_id: UUID,
    payload: ExtendDeadlineRequest,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election_id)
        .first()
    )

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only extend elections that you created",
        )

    if election.status != ElectionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active elections can have their deadline extended",
        )

    if payload.new_end_date < election.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New end date cannot be earlier than the current end date",
        )

    election.end_date = payload.new_end_date

    if payload.title is not None:
        election.title = payload.title

    db.commit()
    db.refresh(election)

    return election

@router.post(
    "/{election_id}/voters",
    response_model=ElectionVoterResponse,
    status_code=status.HTTP_201_CREATED,
)
def addEligibleVoter(
    election_id: UUID,
    payload: AddElectionVoterRequest,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    election = db.query(Election).filter(Election.id == election_id).first()

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only add voters to elections that you created",
        )

    if election.status != ElectionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voters can only be added while the election is in draft status",
        )

    voter = (
        db.query(User)
        .filter(User.external_id == payload.external_id)
        .first()
    )

    if not voter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voter not found",
        )

    if voter.role != UserRole.voter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only voter accounts can be added as voters",
        )

    if voter.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active voters can be added as voters",
        )

    existing_voter = (
        db.query(ElectionVoter)
        .filter(
            ElectionVoter.election_id == election.id,
            ElectionVoter.voter_id == voter.id,
        )
        .first()
    )

    if existing_voter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voter is already added as an eligible voter for this election",
        )

    election_voter = ElectionVoter(
        election_id=election.id,
        voter_id=voter.id,
        eligibility_status=EligibilityStatus.eligible,
    )

    db.add(election_voter)

    # Audit the membership change in the same transaction as the change itself, so a
    # rollback (e.g. the IntegrityError below) discards both.
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="eligibility_changed",
        entity_type="election",
        entity_id=election.id,
        details=_eligibility_details("added", voter.id),
    )

    try:
        db.commit()
        db.refresh(election_voter)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voter is already added as an eligible voter for this election",
        )

    return election_voter

@router.get(
    "/{election_id}/voters",
    response_model=list[ElectionVoterDetailResponse],
)
def getEligibleVoters(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    election = db.query(Election).filter(Election.id == election_id).first()

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view voters for elections that you created",
        )

    voter_records = (
        db.query(ElectionVoter, User)
        .join(User, ElectionVoter.voter_id == User.id)
        .filter(ElectionVoter.election_id == election.id)
        .order_by(User.username.asc())
        .all()
    )

    return [
        ElectionVoterDetailResponse(
            id=election_voter.id,
            election_id=election_voter.election_id,
            voter_id=election_voter.voter_id,
            voter_external_id=voter.external_id,
            voter_username=voter.username,
            voter_email=voter.email,
            eligibility_status=election_voter.eligibility_status.value,
            voted_at=election_voter.voted_at,
            created_at=election_voter.created_at,
        )
        for election_voter, voter in voter_records
    ]

def _finalize_election_close(db: Session, election_id: UUID, current_organizer: User) -> Election:
    """
    Shared close/tally workflow behind both POST /{id}/close and the legacy
    PATCH /{id}/complete, so no public path can mark an election completed without
    also producing its cached results.

    Runs the homomorphic tally exactly once, upserts candidate_results, flips the
    status to completed, and records the election_closed + results_published audit
    events — all in a single atomic commit. Returns the completed election.

    Concurrency: the election row is taken with SELECT ... FOR UPDATE, so on
    PostgreSQL a second concurrent request blocks on the lock, and once the first
    transaction commits it re-reads the now-completed row and exits at the status
    guard below — before any second tally. SQLAlchemy omits FOR UPDATE on SQLite
    (which already serializes writers), so the same guard keeps SQLite correct.
    """
    election = (
        db.query(Election)
        .filter(Election.id == election_id)
        .with_for_update()
        .first()
    )

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only close elections that you created",
        )

    # Re-validated on the locked row: a request that was blocked on the lock now
    # sees completed and stops here, so the tally never runs twice.
    if election.status != ElectionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active elections can be closed",
        )

    candidates = (
        db.query(Candidate)
        .filter(Candidate.election_id == election.id)
        .all()
    )

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election has no candidates",
        )

    candidate_ids = [str(candidate.id) for candidate in candidates]
    ballots = db.query(Ballot).filter(Ballot.election_id == election.id).all()

    # The private key is fetched from the encrypted keystore at tally time only and
    # never stored on the election object or returned in the response. HTTPExceptions
    # are re-raised untouched; only a genuine tally/DB failure rolls back and surfaces
    # a generic 500 so nothing about the key or the individual ballots leaks.
    try:
        public_key = deserialize_public_key(election.public_key_n)
        private_key = load_private_key(db, election)
        tally = homomorphic_tally(
            public_key,
            private_key,
            [ballot.encrypted_vote for ballot in ballots],
            candidate_ids,
        )
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to tally the election results",
        )

    published_at = now_sgt()

    for candidate_id_str, total_votes in tally.items():
        candidate_id = UUID(candidate_id_str)

        result_row = (
            db.query(CandidateResult)
            .filter(
                CandidateResult.election_id == election.id,
                CandidateResult.candidate_id == candidate_id,
            )
            .first()
        )

        if result_row:
            result_row.total_votes = total_votes
            result_row.published_at = published_at
        else:
            db.add(CandidateResult(
                election_id=election.id,
                candidate_id=candidate_id,
                total_votes=total_votes,
                published_at=published_at,
            ))

    election.status = ElectionStatus.completed

    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="election_closed",
        entity_type="election",
        entity_id=election.id,
    )
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="results_published",
        entity_type="election",
        entity_id=election.id,
    )

    db.commit()

    return (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )


@router.patch("/{election_id}/complete", response_model=ElectionResponse)
def completeElection(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    """
    Legacy completion endpoint. Kept for API compatibility but routed through the
    same close/tally service as POST /{id}/close, so it can never leave an election
    marked completed without cached candidate_results.
    """
    return _finalize_election_close(db, election_id, current_organizer)

@router.patch("/{election_id}/activate", response_model=ElectionResponse)
def activateElection(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election_id)
        .first()
    )

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.organizer_id != current_organizer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only activate elections that you created",
        )

    if election.status != ElectionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft elections can be activated",
        )

    if not election.candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election must have at least one candidate before activation",
        )

    # Candidate list is now final: enforce the full ballot configuration.
    _validate_ballot_configuration(
        election.ballot_type,
        election.max_selections,
        candidate_count=len(election.candidates),
    )

    if not election.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election must have a deadline before activation",
        )

    eligible_voter_count = (
        db.query(ElectionVoter)
        .filter(
            ElectionVoter.election_id == election.id,
            ElectionVoter.eligibility_status == EligibilityStatus.eligible,
        )
        .count()
    )

    if eligible_voter_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election must have at least one eligible voter before activation",
        )

    create_and_store_keypair(db, election)
    election.status = ElectionStatus.active
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="key_generated",
        entity_type="election",
        entity_id=election.id,
    )
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="election_activated",
        entity_type="election",
        entity_id=election.id,
    )
    db.commit()

    updated_election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )

    return updated_election


@router.post("/{election_id}/close", response_model=ElectionResponse)
def closeElection(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_organizer: User = Depends(require_organizer),
):
    """
    Explicitly close an active election: run the homomorphic tally exactly once,
    persist the per-candidate results, mark the election completed, and record the
    audit trail — all in a single atomic commit. Results are produced here and are
    only ever read (never recomputed) by GET /results afterwards.
    """
    return _finalize_election_close(db, election_id, current_organizer)