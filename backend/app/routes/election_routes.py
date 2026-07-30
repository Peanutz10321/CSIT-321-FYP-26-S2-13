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
from app.security.audit import audit_details, log_event
from app.security.security import get_current_user, require_organizer
from app.security.keystore import create_and_store_keypair, load_private_key
from app.security.homomorphic import deserialize_public_key, homomorphic_tally
from app.services.election_lock import lock_election_for_close

from sqlalchemy.exc import IntegrityError
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.schemas.election_voter_schema import (
    AddElectionVoterRequest,
    ElectionVoterResponse,
    ElectionVoterDetailResponse,
)


router = APIRouter(prefix="/elections", tags=["Elections"])


def _eligibility_details(change: str, voter_id: UUID) -> str:
    """Details for an eligibility_changed event.

    Records only the administrative change type and the target voter's user UUID —
    never an email, name, external id, or any ballot/secret material. Structured
    JSON so the value cannot be made ambiguous by punctuation.
    """
    return audit_details(change=change, voter_id=str(voter_id))


def _title_change_details(old_title: str | None, new_title: str | None) -> str:
    """Details for an election_title_changed event.

    An election title is an organizer-authored, intended-public label for the
    election, so recording both sides of a rename is what makes the event
    reviewable. It is organizer-controlled free text, not a field the system
    guarantees to be non-personal — the assumption is that a title is meant to be
    seen, the same way it is shown to every eligible voter. JSON-encoded because a
    title can contain the ``;`` and ``=`` a delimited string would treat as
    separators.
    """
    return audit_details(old_title=old_title, new_title=new_title)


def _resolve_eligible_voters(db: Session, external_ids: list[str]) -> list[User]:
    """Resolve submitted external ids to the users they name, or raise.

    Purely a lookup: it writes nothing. Every caller runs it *before* touching the
    database, so a bad id can never leave a half-applied eligibility list behind.
    """
    seen: set[str] = set()
    voters: list[User] = []

    for external_id in external_ids:
        if external_id in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate eligible voter '{external_id}'",
            )
        seen.add(external_id)

        voter = db.query(User).filter(User.external_id == external_id).first()
        if not voter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voter '{external_id}' not found",
            )
        if voter.role != UserRole.voter:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{external_id}' is not a voter account",
            )
        if voter.status != UserStatus.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Voter '{external_id}' is not active",
            )

        voters.append(voter)

    return voters


def _sync_eligible_voters(
    db: Session,
    election: Election,
    voters: list[User],
    actor_user_id: UUID,
) -> None:
    """Make the election's eligibility list exactly ``voters``.

    Adds the missing memberships and removes the ones no longer submitted, each
    with its own eligibility_changed event in the same transaction as the change —
    the same style the single-voter route uses. Removal is only ever reached on a
    draft, which cannot hold ballots, so no cast vote can be orphaned.
    """
    existing = (
        db.query(ElectionVoter)
        .filter(ElectionVoter.election_id == election.id)
        .all()
    )
    existing_voter_ids = {row.voter_id for row in existing}
    submitted_voter_ids = {voter.id for voter in voters}

    for voter in voters:
        if voter.id in existing_voter_ids:
            continue

        db.add(ElectionVoter(
            election_id=election.id,
            voter_id=voter.id,
            eligibility_status=EligibilityStatus.eligible,
        ))
        log_event(
            db,
            actor_user_id=actor_user_id,
            action="eligibility_changed",
            entity_type="election",
            entity_id=election.id,
            details=_eligibility_details("added", voter.id),
        )

    for row in existing:
        if row.voter_id in submitted_voter_ids:
            continue

        db.delete(row)
        log_event(
            db,
            actor_user_id=actor_user_id,
            action="eligibility_changed",
            entity_type="election",
            entity_id=election.id,
            details=_eligibility_details("removed", row.voter_id),
        )


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

    # Resolved before the first write so an unknown id fails the request without
    # leaving a half-built draft behind. A draft may still have no voters at all.
    eligible_voters = _resolve_eligible_voters(db, payload.eligible_voter_external_ids)

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

    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="election_created",
        entity_type="election",
        entity_id=election.id,
        details=audit_details(status="draft"),
    )

    _sync_eligible_voters(db, election, eligible_voters, current_organizer.id)

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

    # Resolved before the election row exists, so a bad id cannot leave a keypair or
    # a partially populated voter list behind.
    eligible_voters = _resolve_eligible_voters(db, payload.eligible_voter_external_ids)

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

    # Logged before the key and eligibility events so the chain reads in the
    # order the work actually happened. A rollback later in this handler discards
    # all three together.
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="election_created",
        entity_type="election",
        entity_id=election.id,
        details=audit_details(status="active"),
    )

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

    # One membership and one audit event per voter, in the same transaction as the
    # election itself. The list is new, so this only ever adds.
    _sync_eligible_voters(db, election, eligible_voters, current_organizer.id)

    # Direct creation finishes with an active election, exactly as the draft
    # activation route does, so it records the same activation event. Placed after
    # every activation prerequisite (key generation and eligibility) has succeeded
    # but before the single shared commit, so a failure anywhere in this handler
    # discards this along with the business records. key_generated is emitted once,
    # above — not duplicated here.
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="election_activated",
        entity_type="election",
        entity_id=election.id,
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
        if not election:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Election not found or you did not create this election",
            )
        
        if election.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Election not found or you did not create this election",
            )

    elif current_user.role == UserRole.voter:
        if not election:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Election not found or you are not eligible to view this election",
            )
        
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
                detail="Election not found or you are not eligible to view this election",
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

    # Validate the resulting stored range, not only pairs supplied together. Draft
    # updates commonly omit start_date, so a submitted deadline must still be
    # compared with the election's existing start date. An explicit null deadline
    # remains valid for an incomplete draft.
    effective_start_date = (
        payload.start_date if payload.start_date is not None else election.start_date
    )
    effective_end_date = (
        payload.end_date
        if "end_date" in payload.model_fields_set
        else election.end_date
    )
    if (
        effective_end_date is not None
        and effective_end_date <= effective_start_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
        )

    # Resolved before the first assignment below, so a rejected voter id leaves the
    # draft exactly as it was rather than half-updated. None means the request is not
    # about eligibility at all and the stored list is left untouched.
    eligible_voters = (
        _resolve_eligible_voters(db, payload.eligible_voter_external_ids)
        if payload.eligible_voter_external_ids is not None
        else None
    )

    # Captured before any assignment so the title event can report both sides.
    old_title = election.title
    # Only fields whose value actually differs from what is stored. A request that
    # merely *mentions* a field at its current value is a no-op and records nothing.
    changed_fields = []

    if payload.title is not None and payload.title != election.title:
        election.title = payload.title
        changed_fields.append("title")

    if payload.description is not None and payload.description != election.description:
        election.description = payload.description
        changed_fields.append("description")

    if payload.start_date is not None and payload.start_date != election.start_date:
        election.start_date = payload.start_date
        changed_fields.append("start_date")

    # end_date is the one field where None is a real value rather than "not
    # supplied": an organizer who empties the deadline box sends end_date: null and
    # expects the stored deadline to go away. model_fields_set is what separates
    # that from a request that never mentions the field, which must leave it alone.
    # Clearing is safe on a draft because activation refuses an election without a
    # deadline, so the incomplete state can never be published.
    if "end_date" in payload.model_fields_set and payload.end_date != election.end_date:
        election.end_date = payload.end_date
        changed_fields.append("end_date")

    # Replace the candidate list only when the resulting set actually differs, so
    # re-submitting the same candidates is not recorded as a change.
    # An empty list is allowed here, matching draft creation: a draft may hold an
    # incomplete configuration, and an organizer clearing the candidate box to retype
    # it should not be blocked mid-edit. Activation is what refuses a candidate-less
    # election.
    if payload.candidates is not None:
        existing = (
            db.query(Candidate)
            .filter(Candidate.election_id == election.id)
            .order_by(Candidate.display_order)
            .all()
        )
        existing_shape = [
            (c.name, c.description, c.photo_url, c.display_order) for c in existing
        ]
        incoming_shape = [
            (c.name, c.description, c.photo_url, c.display_order or index)
            for index, c in enumerate(payload.candidates, start=1)
        ]

        if incoming_shape != existing_shape:
            changed_fields.append("candidates")
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

    if payload.ballot_type is not None and payload.ballot_type != election.ballot_type:
        election.ballot_type = payload.ballot_type
        changed_fields.append("ballot_type")

    if payload.max_selections is not None and payload.max_selections != election.max_selections:
        election.max_selections = payload.max_selections
        changed_fields.append("max_selections")

    # No genuine change means no event — an audit trail full of empty "updated"
    # rows hides the real ones.
    if changed_fields:
        log_event(
            db,
            actor_user_id=current_organizer.id,
            action="election_updated",
            entity_type="election",
            entity_id=election.id,
            # Field names only — never the submitted values, which would put
            # candidate names into the audit trail.
            details=audit_details(status="draft", fields=changed_fields),
        )

    # A separate event because a rename is worth finding on its own, and it is
    # the one field where both old and new values are safe to keep.
    if "title" in changed_fields:
        log_event(
            db,
            actor_user_id=current_organizer.id,
            action="election_title_changed",
            entity_type="election",
            entity_id=election.id,
            details=_title_change_details(old_title, election.title),
        )

    # Eligibility keeps its own eligibility_changed events rather than joining
    # changed_fields, so the membership trail reads the same however it was edited.
    if eligible_voters is not None:
        _sync_eligible_voters(db, election, eligible_voters, current_organizer.id)

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

    # Logged before the row goes away. audit_logs.entity_id carries no foreign
    # key, so the event outlives the election it describes — which is the point.
    log_event(
        db,
        actor_user_id=current_organizer.id,
        action="election_deleted",
        entity_type="election",
        entity_id=election.id,
        details=audit_details(status="draft"),
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

    old_end_date = election.end_date
    old_title = election.title

    election.end_date = payload.new_end_date

    if payload.title is not None:
        election.title = payload.title

    if election.end_date != old_end_date:
        log_event(
            db,
            actor_user_id=current_organizer.id,
            action="election_deadline_extended",
            entity_type="election",
            entity_id=election.id,
            details=audit_details(
                old_end_date=old_end_date.isoformat() if old_end_date else None,
                new_end_date=election.end_date.isoformat(),
            ),
        )

    # This endpoint can rename an active election, so the same title event is
    # emitted here rather than only on the draft-update path.
    if payload.title is not None and payload.title != old_title:
        log_event(
            db,
            actor_user_id=current_organizer.id,
            action="election_title_changed",
            entity_type="election",
            entity_id=election.id,
            details=_title_change_details(old_title, election.title),
        )

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

def _locked_election(db: Session, election_id: UUID) -> Election | None:
    """
    Take the election row exclusively for this transaction.

    The lock itself lives in app/services/election_lock.py because the vote path
    takes a shared lock on the same row; keeping both modes in one module is what
    makes the vote/finalization protocol reviewable in a single place.
    """
    return lock_election_for_close(db, election_id)


def _tally_and_complete(
    db: Session,
    election: Election,
    actor_user_id: UUID,
    close_reason: str | None = None,
    *,
    commit: bool = True,
) -> None:
    """
    Core close/tally workflow — the single place the tally is ever run.

    The caller must already hold the election row lock and have verified the
    election is active. Runs the homomorphic tally exactly once, upserts
    candidate_results, flips the status to completed, and records the
    election_closed + results_published audit events.

    Two callers reach it: auto_finalize_if_expired, which serves an expired
    election's first results request and uses the default to commit the completed
    tally here; and the demo seed, which owns its transaction and passes
    ``commit=False`` so reset, population, tally, and verification commit
    atomically. There is no HTTP endpoint that closes an election directly.

    close_reason is recorded on the audit events so a deadline-driven close is
    distinguishable from a seeded one; it never carries ballot data.
    """
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

    details = audit_details(reason=close_reason) if close_reason else None

    log_event(
        db,
        actor_user_id=actor_user_id,
        action="election_closed",
        entity_type="election",
        entity_id=election.id,
        details=details,
    )
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="results_published",
        entity_type="election",
        entity_id=election.id,
        details=details,
    )

    if commit:
        db.commit()
    else:
        db.flush()


def auto_finalize_if_expired(db: Session, election_id: UUID) -> None:
    """
    Deadline-driven finalize, and the only way an election is ever completed.

    There is no manual close endpoint: if an election is still active but its
    end_date has passed, the next request for its results closes it through the
    locked close/tally workflow below.
    
    This is a no-op for anything else — drafts, already-completed elections,
    elections still inside their voting period, and (defensively) an election that
    was force-set active without a keypair, which would otherwise fail a read with a
    tally error. Callers can therefore invoke it unconditionally.

    The close is attributed to the election's own organizer with reason=deadline, so
    the audit trail shows it was automatic rather than organizer-initiated — a voter
    merely reading results never appears as the closer. The row is taken with
    SELECT ... FOR UPDATE and re-read under the lock, so two concurrent readers
    cannot both tally.
    """
    election = _locked_election(db, election_id)

    if not election:
        return

    if election.status != ElectionStatus.active:
        return

    if election.end_date is None or election.end_date >= now_sgt():
        return

    if not election.public_key_n:
        return

    _tally_and_complete(db, election, election.organizer_id, close_reason="deadline")


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

    if election.end_date <= election.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
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
