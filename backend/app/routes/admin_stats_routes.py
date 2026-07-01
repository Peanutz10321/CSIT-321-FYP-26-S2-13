from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ballot import Ballot, BulletinStatus
from app.models.election import Election, ElectionStatus
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.user import User, UserRole
from app.security.security import require_system_admin


router = APIRouter(prefix="/admin/stats", tags=["Admin Stats"])


class AdminStatsResponse(BaseModel):
    total_voters: int
    total_organizers: int
    total_admins: int
    active_elections: int
    total_votes_cast: int
    total_eligible_voters: int
    participation_rate: float


@router.get("", response_model=AdminStatsResponse)
def getAdminStats(
    db: Session = Depends(get_db),
    _: User = Depends(require_system_admin),
):
    total_voters = db.query(User).filter(User.role == UserRole.voter).count()
    total_organizers = db.query(User).filter(User.role == UserRole.organizer).count()
    total_admins = db.query(User).filter(User.role == UserRole.system_admin).count()

    active_elections = (
        db.query(Election).filter(Election.status == ElectionStatus.active).count()
    )

    total_votes_cast = (
        db.query(Ballot).filter(Ballot.bulletin_status == BulletinStatus.published).count()
    )

    total_eligible_voters = (
        db.query(ElectionVoter)
        .filter(ElectionVoter.eligibility_status == EligibilityStatus.eligible)
        .count()
    )

    participation_rate = (
        round((total_votes_cast / total_eligible_voters) * 100, 1)
        if total_eligible_voters > 0
        else 0.0
    )

    return AdminStatsResponse(
        total_voters=total_voters,
        total_organizers=total_organizers,
        total_admins=total_admins,
        active_elections=active_elections,
        total_votes_cast=total_votes_cast,
        total_eligible_voters=total_eligible_voters,
        participation_rate=participation_rate,
    )
