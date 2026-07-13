import hashlib
import uuid
from datetime import timedelta

from sqlalchemy import text

from app.database import Base, engine, SessionLocal

# Import models so SQLAlchemy registers all tables
import app.models.user
import app.models.election
import app.models.election_key
import app.models.candidate
import app.models.election_voter
import app.models.ballot
import app.models.candidate_result
import app.models.audit_log

from app.core.time import now_sgt
from app.models.user import User, UserRole, UserStatus
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.ballot import Ballot, BulletinStatus
from app.security.password import hash_password
from app.security.homomorphic import (
    deserialize_public_key,
    encrypt_vote,
)
from app.security.keystore import create_and_store_keypair


DEMO_PASSWORD = "Demo12345!"


def reset_tables(db):
    db.execute(text("""
        TRUNCATE TABLE
            candidate_results,
            ballots,
            election_voters,
            candidates,
            election_keys,
            elections,
            audit_logs,
            users
        RESTART IDENTITY CASCADE;
    """))
    db.commit()


def create_user(db, role, external_id, username, full_name, email, status=UserStatus.active):
    user = User(
        role=role,
        status=status,
        external_id=external_id,
        username=username,
        full_name=full_name,
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
    )
    db.add(user)
    db.flush()
    return user


def create_candidates(db, election, names):
    candidates = []
    for index, name in enumerate(names, start=1):
        candidate = Candidate(
            election_id=election.id,
            name=name,
            description=f"{name} demo candidate profile.",
            display_order=index,
        )
        db.add(candidate)
        candidates.append(candidate)

    db.flush()
    return candidates


def add_eligible_voters(db, election, voters):
    records = []
    for voter in voters:
        record = ElectionVoter(
            election_id=election.id,
            voter_id=voter.id,
            eligibility_status=EligibilityStatus.eligible,
        )
        db.add(record)
        records.append(record)

    db.flush()
    return records


def add_encrypted_ballot(db, election, voter_record, candidates, selected_candidate):
    public_key = deserialize_public_key(election.public_key_n)
    candidate_ids = [str(candidate.id) for candidate in candidates]

    encrypted_vote = encrypt_vote(
        public_key,
        candidate_ids,
        str(selected_candidate.id),
    )

    receipt_code = f"RCPT-{uuid.uuid4().hex[:12].upper()}"

    # Better than your current route logic because this does NOT hash candidate_id directly.
    vote_hash = hashlib.sha256(
        f"{election.id}:{voter_record.id}:{receipt_code}:{encrypted_vote}".encode()
    ).hexdigest()

    submitted_time = now_sgt() - timedelta(days=3)

    voter_record.voted_at = submitted_time

    ballot = Ballot(
        election_id=election.id,
        election_voter_id=voter_record.id,
        encrypted_vote=encrypted_vote,
        vote_hash=vote_hash,
        receipt_code=receipt_code,
        submitted_at=submitted_time,
        bulletin_status=BulletinStatus.published,
    )

    db.add(ballot)
    db.flush()
    return ballot


def main():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        reset_tables(db)

        admin = create_user(
            db,
            UserRole.system_admin,
            "ADM-001",
            "admin_demo",
            "Demo System Admin",
            "admin@demo.com",
        )

        organizer = create_user(
            db,
            UserRole.organizer,
            "ORG-001",
            "organizer_demo",
            "Demo Organizer",
            "organizer@demo.com",
        )

        voter1 = create_user(
            db,
            UserRole.voter,
            "VOTER-001",
            "voter1_demo",
            "Voter One",
            "voter1@demo.com",
        )

        voter2 = create_user(
            db,
            UserRole.voter,
            "VOTER-002",
            "voter2_demo",
            "Voter Two",
            "voter2@demo.com",
        )

        voter3 = create_user(
            db,
            UserRole.voter,
            "VOTER-003",
            "voter3_demo",
            "Voter Three",
            "voter3@demo.com",
        )

        voter4 = create_user(
            db,
            UserRole.voter,
            "VOTER-004",
            "voter4_demo",
            "Voter Four",
            "voter4@demo.com",
        )

        suspended_voter = create_user(
            db,
            UserRole.voter,
            "VOTER-005",
            "suspended_demo",
            "Suspended Voter",
            "suspended@demo.com",
            status=UserStatus.suspended,
        )

        now = now_sgt()

        # Active election for live demo
        active_election = Election(
            organizer_id=organizer.id,
            title="Community Leadership Voting Event 2026",
            description="Live demo voting event for eligible voter participation.",
            status=ElectionStatus.active,
            start_date=now - timedelta(hours=1),
            end_date=now + timedelta(days=7),
        )
        db.add(active_election)
        db.flush()
        create_and_store_keypair(db, active_election)

        create_candidates(
            db,
            active_election,
            ["Alice Tan", "Brandon Lee", "Chloe Lim"],
        )

        add_eligible_voters(
            db,
            active_election,
            [voter1, voter2, voter3, voter4],
        )

        # Completed election for results demo
        completed_election = Election(
            organizer_id=organizer.id,
            title="Completed Organization Voting Event 2026",
            description="Completed demo election showing homomorphic tallying.",
            status=ElectionStatus.completed,
            start_date=now - timedelta(days=10),
            end_date=now - timedelta(days=5),
        )
        db.add(completed_election)
        db.flush()
        create_and_store_keypair(db, completed_election)

        completed_candidates = create_candidates(
            db,
            completed_election,
            ["Daniel Wong", "Emily Chen", "Farhan Aziz"],
        )

        completed_voters = add_eligible_voters(
            db,
            completed_election,
            [voter1, voter2, voter3, voter4],
        )

        # Final result should become:
        # Daniel Wong = 2
        # Emily Chen = 1
        # Farhan Aziz = 1
        add_encrypted_ballot(db, completed_election, completed_voters[0], completed_candidates, completed_candidates[0])
        add_encrypted_ballot(db, completed_election, completed_voters[1], completed_candidates, completed_candidates[0])
        add_encrypted_ballot(db, completed_election, completed_voters[2], completed_candidates, completed_candidates[1])
        add_encrypted_ballot(db, completed_election, completed_voters[3], completed_candidates, completed_candidates[2])

        db.commit()

        print("Demo database seeded successfully.")
        print("")
        print("Login accounts:")
        print(f"Admin:     admin@demo.com / {DEMO_PASSWORD}")
        print(f"Organizer: organizer@demo.com / {DEMO_PASSWORD}")
        print(f"Voter:     voter1@demo.com / {DEMO_PASSWORD}")
        print(f"Voter:     voter2@demo.com / {DEMO_PASSWORD}")
        print(f"Suspended voter: suspended@demo.com / {DEMO_PASSWORD}")
        print("")
        print("Active voting event:")
        print("Community Leadership Voting Event 2026")
        print("")
        print("Completed voting event expected result:")
        print("Daniel Wong = 2, Emily Chen = 1, Farhan Aziz = 1")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
