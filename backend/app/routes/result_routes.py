from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.models.candidate_result import CandidateResult
from app.models.election_voter import ElectionVoter
from app.schemas.result_schema import ElectionResultResponse, CandidateResultResponse
from app.security.security import get_current_user


router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/elections/{election_id}", response_model=ElectionResultResponse)
def getElectionResults(
    election_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Read-only view of an election's published results.

    Results are computed and persisted exactly once when the organizer closes the
    election (POST /elections/{id}/close). This endpoint only ever reads the cached
    candidate_results — it never decrypts ballots, loads the private key, runs a
    tally, writes, commits, or transitions the election status.
    """
    election = db.query(Election).filter(Election.id == election_id).first()

    if not election:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        )

    if current_user.role == UserRole.organizer and election.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view results for elections that you created",
        )

    if current_user.role == UserRole.voter:
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

    # Results are only published for completed elections. Nothing here transitions
    # status — an active election past its end date stays "in progress" until the
    # organizer explicitly closes it via POST /elections/{id}/close.
    if election.status != ElectionStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Results are not yet available. The election is still in progress.",
        )

    candidates = db.query(Candidate).filter(Candidate.election_id == election.id).all()

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Election has no candidates",
        )

    # Read the cached results produced at close time. No decryption happens here.
    result_rows = (
        db.query(CandidateResult)
        .filter(CandidateResult.election_id == election.id)
        .all()
    )
    totals = {str(row.candidate_id): row.total_votes for row in result_rows}
    published_at = next(
        (row.published_at for row in result_rows if row.published_at is not None),
        None,
    )

    result_items = sorted(
        [
            CandidateResultResponse(
                candidate_id=candidate.id,
                candidate_name=candidate.name,
                total_votes=totals.get(str(candidate.id), 0),
                published_at=published_at,
            )
            for candidate in candidates
        ],
        key=lambda item: item.total_votes,
        reverse=True,
    )

    total_votes = sum(item.total_votes for item in result_items)

    winner = None
    tied_candidates: list[str] = []
    if result_items and total_votes > 0:
        top_votes = result_items[0].total_votes
        leaders = [item.candidate_name for item in result_items if item.total_votes == top_votes]
        if len(leaders) > 1:
            tied_candidates = leaders
        else:
            winner = leaders[0]

    return ElectionResultResponse(
        election_id=election.id,
        election_title=election.title,
        status=election.status.value,
        total_votes=total_votes,
        winner=winner,
        tied_candidates=tied_candidates,
        results=result_items,
    )
