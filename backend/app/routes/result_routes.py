from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.models.ballot import Ballot
from app.models.candidate_result import CandidateResult
from app.schemas.result_schema import ElectionResultResponse, CandidateResultResponse
from app.security.security import get_current_user


router = APIRouter(prefix="/results", tags=["Results"])


def _extract_candidate_id_from_placeholder(encrypted_vote: str) -> str | None:
    """
    Temporary MVP helper.
    Current placeholder format: encrypted_placeholder:{candidate_id}
    Later this should be replaced by homomorphic tally/decryption logic.
    """
    prefix = "encrypted_placeholder:"
    if not encrypted_vote.startswith(prefix):
        return None

    return encrypted_vote.replace(prefix, "", 1)


@router.get("/elections/{election_id}", response_model=ElectionResultResponse)
def view_election_results(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    election = db.query(Election).filter(Election.id == election_id).first()

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if election.status != ElectionStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Results are only available for completed elections",
        )

    # Basic access rule:
    # - teacher who created the election can view
    # - students can view completed results
    # - system admin can view
    if current_user.role == UserRole.teacher and election.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view results for elections that you created",
        )

    candidates = db.query(Candidate).filter(Candidate.election_id == election.id).all()

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election has no candidates",
        )

    candidate_lookup = {str(candidate.id): candidate for candidate in candidates}
    tally = {str(candidate.id): 0 for candidate in candidates}

    ballots = db.query(Ballot).filter(Ballot.election_id == election.id).all()

    for ballot in ballots:
        candidate_id = _extract_candidate_id_from_placeholder(ballot.encrypted_vote)

        if candidate_id in tally:
            tally[candidate_id] += 1

    published_at = datetime.utcnow()

    # Upsert candidate_results rows
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
            result_row = CandidateResult(
                election_id=election.id,
                candidate_id=candidate_id,
                total_votes=total_votes,
                published_at=published_at,
            )
            db.add(result_row)

    db.commit()

    result_items = [
        CandidateResultResponse(
            candidate_id=candidate.id,
            candidate_name=candidate.name,
            total_votes=tally[str(candidate.id)],
            published_at=published_at,
        )
        for candidate in candidates
    ]

    return ElectionResultResponse(
        election_id=election.id,
        election_title=election.title,
        status=election.status.value,
        results=result_items,
    )