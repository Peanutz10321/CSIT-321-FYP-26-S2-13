from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.schemas.election_schema import ElectionCreate, ElectionResponse, ElectionUpdate, ExtendDeadlineRequest
from app.security.security import get_current_user, require_teacher

from sqlalchemy.exc import IntegrityError
from app.models.election import Election, ElectionStatus
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.schemas.election_voter_schema import (
    AddElectionVoterRequest,
    ElectionVoterResponse,
    ElectionVoterDetailResponse,
)


router = APIRouter(prefix="/elections", tags=["Elections"])


@router.post("/", response_model=ElectionResponse, status_code=status.HTTP_201_CREATED)
def create_election(
    payload: ElectionCreate,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
):
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

    election = Election(
        teacher_id=current_teacher.id,
        title=payload.title,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=ElectionStatus.draft,
    )

    db.add(election)
    db.flush()  # gives election.id before commit

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

    created_election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )

    return created_election

@router.get("/active", response_model=list[ElectionResponse])
def view_active_election_list(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.status == ElectionStatus.active)
    )

    if search:
        query = query.filter(Election.title.ilike(f"%{search}%"))

    return query.order_by(Election.start_date.desc()).all()

@router.get("/history", response_model=list[ElectionResponse])
def view_election_history(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.status.in_([ElectionStatus.completed, ElectionStatus.cancelled, ElectionStatus.archived]))
    )

    if search:
        query = query.filter(Election.title.ilike(f"%{search}%"))

    return query.order_by(Election.end_date.desc()).all()

@router.get("/{election_id}", response_model=ElectionResponse)
def view_election_details(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    return election

@router.put("/{election_id}", response_model=ElectionResponse)
def update_draft_election(
    election_id: UUID,
    payload: ElectionUpdate,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
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

    if election.teacher_id != current_teacher.id:
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

    db.commit()

    updated_election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )

    return updated_election

@router.patch("/{election_id}/extend-deadline", response_model=ElectionResponse)
def extend_active_election_deadline(
    election_id: UUID,
    payload: ExtendDeadlineRequest,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
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

    if election.teacher_id != current_teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only extend elections that you created",
        )

    if election.status != ElectionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active elections can have their deadline extended",
        )

    if payload.new_end_date <= election.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New end date must be later than the current end date",
        )

    election.end_date = payload.new_end_date

    db.commit()
    db.refresh(election)

    return election

@router.post(
    "/{election_id}/voters",
    response_model=ElectionVoterResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_eligible_voter(
    election_id: UUID,
    payload: AddElectionVoterRequest,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
):
    election = db.query(Election).filter(Election.id == election_id).first()

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.teacher_id != current_teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only add voters to elections that you created",
        )

    if election.status != ElectionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voters can only be added while the election is in draft status",
        )

    student = (
        db.query(User)
        .filter(User.institution_id == payload.institution_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    if student.role != UserRole.student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only student accounts can be added as voters",
        )

    if student.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active students can be added as voters",
        )

    existing_voter = (
        db.query(ElectionVoter)
        .filter(
            ElectionVoter.election_id == election.id,
            ElectionVoter.student_id == student.id,
        )
        .first()
    )

    if existing_voter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is already added as an eligible voter for this election",
        )

    election_voter = ElectionVoter(
        election_id=election.id,
        student_id=student.id,
        eligibility_status=EligibilityStatus.eligible,
    )

    db.add(election_voter)

    try:
        db.commit()
        db.refresh(election_voter)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is already added as an eligible voter for this election",
        )

    return election_voter

@router.get(
    "/{election_id}/voters",
    response_model=list[ElectionVoterDetailResponse],
)
def view_eligible_voters(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
):
    election = db.query(Election).filter(Election.id == election_id).first()

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.teacher_id != current_teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view voters for elections that you created",
        )

    voter_records = (
        db.query(ElectionVoter, User)
        .join(User, ElectionVoter.student_id == User.id)
        .filter(ElectionVoter.election_id == election.id)
        .order_by(User.full_name.asc())
        .all()
    )

    return [
        ElectionVoterDetailResponse(
            id=voter.id,
            election_id=voter.election_id,
            student_id=voter.student_id,
            student_institution_id=student.institution_id,
            student_full_name=student.full_name,
            student_email=student.email,
            eligibility_status=voter.eligibility_status.value,
            voted_at=voter.voted_at,
            created_at=voter.created_at,
        )
        for voter, student in voter_records
    ]

@router.patch("/{election_id}/complete", response_model=ElectionResponse)
def complete_election(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
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

    if election.teacher_id != current_teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only complete elections that you created",
        )

    if election.status != ElectionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active elections can be completed",
        )

    election.status = ElectionStatus.completed

    db.commit()
    db.refresh(election)

    return election

@router.patch("/{election_id}/activate", response_model=ElectionResponse)
def activate_election(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_teacher: User = Depends(require_teacher),
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

    if election.teacher_id != current_teacher.id:
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

    election.status = ElectionStatus.active
    db.commit()

    updated_election = (
        db.query(Election)
        .options(joinedload(Election.candidates))
        .filter(Election.id == election.id)
        .first()
    )

    return updated_election