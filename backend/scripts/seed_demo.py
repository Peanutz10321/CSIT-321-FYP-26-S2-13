"""
Seed a demo database.

Destructive: with --reset this truncates every application table. See the guard
conditions in scripts/demo_seed_guard.py and the runbook in MIGRATIONS.md.

The completed demo election is produced by the real close/tally workflow, not by
inserting a finished-looking election, so the published results are genuine
homomorphic tally output and are verified before the script reports success.
"""

import argparse
import os
import sys
import uuid
from datetime import timedelta

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.database import engine, SessionLocal

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
from app.models.candidate_result import CandidateResult
from app.models.user import User, UserRole, UserStatus
from app.models.election import Election, ElectionStatus
from app.models.candidate import Candidate
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.ballot import Ballot, BulletinStatus
from app.security.audit import CHAIN_ID, GENESIS_HASH, audit_details, log_event
from app.security.password import hash_password
from app.security.homomorphic import (
    deserialize_public_key,
    encrypt_vote,
)
from app.security.ballot_commitment import (
    ballot_configuration_digest,
    compute_ballot_commitment,
)
from app.security.keystore import create_and_store_keypair

# The single shared close/tally workflow, also used by the close endpoints and the
# deadline auto-finalize. Importing it means the demo results come from exactly the
# production path rather than a seed-only reimplementation.
# (Relocating it into app/services/ is left to PR 4, which owns that module.)
from app.routes.election_routes import _tally_and_complete

from scripts.demo_seed_guard import (
    require_demo_password,
    require_reset_confirmation,
    require_safe_demo_database,
)


# The tally the completed demo election must produce. Asserted against the stored
# candidate_results after the real tally runs, so the printed summary can never
# disagree with the database.
EXPECTED_COMPLETED_TALLY = {
    "Daniel Wong": 2,
    "Emily Chen": 1,
    "Farhan Aziz": 1,
}


def require_schema_at_head(db) -> None:
    """Refuse to seed a database whose schema Alembic has not built.

    The application no longer calls create_all() at startup (see MIGRATIONS.md),
    and neither does this script: creating tables here would leave the database
    with no alembic_version row, so a later `alembic upgrade head` would try to
    create tables that already exist and fail.
    """
    inspector = inspect(db.get_bind())
    tables = set(inspector.get_table_names())

    if "alembic_version" not in tables:
        raise RuntimeError(
            "This database is not managed by Alembic. Run 'alembic upgrade head' "
            "before seeding (see MIGRATIONS.md)."
        )

    migration_context = MigrationContext.configure(db.connection())
    current_heads = set(migration_context.get_current_heads())
    script_directory = ScriptDirectory(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic")
    )
    expected_heads = set(script_directory.get_heads())

    if current_heads != expected_heads:
        current = ", ".join(sorted(current_heads)) or "none"
        expected = ", ".join(sorted(expected_heads)) or "none"
        raise RuntimeError(
            "Database is not at Alembic head "
            f"(current: {current}; expected: {expected}). "
            "Run 'alembic upgrade head' before seeding."
        )

    missing = {
        "users",
        "elections",
        "ballots",
        "candidate_results",
        "audit_logs",
        "audit_chain_head",
    } - tables
    if missing:
        raise RuntimeError(
            f"Schema is incomplete (missing: {', '.join(sorted(missing))}). "
            f"Run 'alembic upgrade head' before seeding."
        )


def reset_tables(db):
    """Empty every application table, including the audit chain.

    Only ever reached after the guards in main() have confirmed an explicit
    --reset, DEMO_SEED_ALLOWED=true, and an allowlisted host and database.
    """
    db.execute(text("""
        TRUNCATE TABLE
            candidate_results,
            ballots,
            election_voters,
            candidates,
            election_keys,
            elections,
            audit_logs,
            audit_chain_head,
            users
        RESTART IDENTITY CASCADE;
    """))

    # The chain head has to go back to genesis with the entries it described.
    # Truncating audit_logs while leaving the old head behind would make the
    # next event claim sequence N+1 with nothing before it — which
    # verify_audit_chain would correctly report as a broken chain on a database
    # that had merely been reseeded.
    db.execute(
        text(
            "INSERT INTO audit_chain_head "
            "(id, sequence_number, head_hash, updated_at) "
            "VALUES (:id, 0, :head_hash, :updated_at)"
        ),
        {"id": CHAIN_ID, "head_hash": GENESIS_HASH, "updated_at": now_sgt()},
    )


def create_user(db, role, external_id, username, full_name, email, password,
                status=UserStatus.active):
    user = User(
        role=role,
        status=status,
        external_id=external_id,
        username=username,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
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

    if not election.start_date or not election.end_date:
        raise RuntimeError("Seeded ballots require an election start and end date")

    if election.end_date <= election.start_date:
        raise RuntimeError("Seeded ballots require a valid election date range")

    # Deriving the historical vote time from the election prevents demo ballots
    # from drifting before the start or after the deadline as dates change.
    submitted_time = (
        election.start_date
        + (election.end_date - election.start_date) / 2
    )

    voter_record.voted_at = submitted_time

    # Same commitment function the vote route uses, so seeded ballots verify
    # exactly like production ones instead of carrying a seed-only hash.
    ballot_id = uuid.uuid4()
    ballot = Ballot(
        id=ballot_id,
        election_id=election.id,
        election_voter_id=voter_record.id,
        encrypted_vote=encrypted_vote,
        ballot_commitment=compute_ballot_commitment(
            ballot_id=ballot_id,
            election_id=election.id,
            receipt_code=receipt_code,
            encrypted_vote=encrypted_vote,
            ballot_config_digest=ballot_configuration_digest(
                election.ballot_type.value,
                election.max_selections,
                candidate_ids,
            ),
            submitted_at=submitted_time,
        ),
        receipt_code=receipt_code,
        submitted_at=submitted_time,
        bulletin_status=BulletinStatus.published,
    )

    db.add(ballot)
    db.flush()
    return ballot


def verify_completed_tally(db, election, candidates) -> dict:
    """Read back the stored results and confirm they match the expected tally.

    This is what makes the printed summary trustworthy: the numbers reported at
    the end are read from candidate_results after the homomorphic tally ran, not
    asserted up front.
    """
    names_by_id = {candidate.id: candidate.name for candidate in candidates}

    rows = (
        db.query(CandidateResult)
        .filter(CandidateResult.election_id == election.id)
        .all()
    )

    if not rows:
        raise RuntimeError(
            "The completed demo election produced no candidate_results rows; "
            "the tally did not run."
        )

    actual = {names_by_id[row.candidate_id]: row.total_votes for row in rows}

    if actual != EXPECTED_COMPLETED_TALLY:
        raise RuntimeError(
            f"Seeded tally mismatch. Expected {EXPECTED_COMPLETED_TALLY}, "
            f"stored results were {actual}."
        )

    if election.status != ElectionStatus.completed:
        raise RuntimeError(
            f"Completed demo election is in status '{election.status.value}', "
            f"expected 'completed'."
        )

    return actual


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Truncate every application table before seeding. Destructive.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Fail closed before opening a session: wrong target, unarmed guard, or a
    # missing password must all stop the run before anything is written.
    require_safe_demo_database(
        str(engine.url),
        seed_allowed=os.getenv("DEMO_SEED_ALLOWED"),
        allowed_hosts=os.getenv("DEMO_SEED_ALLOWED_HOSTS"),
        allowed_databases=os.getenv("DEMO_SEED_ALLOWED_DATABASES"),
    )
    require_reset_confirmation(args.reset)
    demo_password = require_demo_password(os.getenv("DEMO_SEED_PASSWORD"))

    db = SessionLocal()

    try:
        require_schema_at_head(db)
        reset_tables(db)

        admin = create_user(
            db,
            UserRole.system_admin,
            "ADM-001",
            "admin_demo",
            "Demo System Admin",
            "admin@demo.com",
            demo_password,
        )

        if args.reset:
            # Deliberately logged here rather than at the truncation itself.
            # reset_tables empties users, audit_logs and audit_chain_head, so an
            # event written earlier would be erased by the very reset it records,
            # and audit_logs.actor_user_id is NOT NULL with a foreign key to
            # users. The admin above is the first row that can own it, which
            # makes this entry 1 of the rebuilt chain.
            log_event(
                db,
                actor_user_id=admin.id,
                action="demo_reset_executed",
                entity_type="database",
                details=audit_details(scope="all_application_tables"),
            )

        organizer = create_user(
            db,
            UserRole.organizer,
            "ORG-001",
            "organizer_demo",
            "Demo Organizer",
            "organizer@demo.com",
            demo_password,
        )

        voter1 = create_user(
            db,
            UserRole.voter,
            "VOTER-001",
            "voter1_demo",
            "Voter One",
            "voter1@demo.com",
            demo_password,
        )

        voter2 = create_user(
            db,
            UserRole.voter,
            "VOTER-002",
            "voter2_demo",
            "Voter Two",
            "voter2@demo.com",
            demo_password,
        )

        voter3 = create_user(
            db,
            UserRole.voter,
            "VOTER-003",
            "voter3_demo",
            "Voter Three",
            "voter3@demo.com",
            demo_password,
        )

        voter4 = create_user(
            db,
            UserRole.voter,
            "VOTER-004",
            "voter4_demo",
            "Voter Four",
            "voter4@demo.com",
            demo_password,
        )

        suspended_voter = create_user(
            db,
            UserRole.voter,
            "VOTER-005",
            "suspended_demo",
            "Suspended Voter",
            "suspended@demo.com",
            demo_password,
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

        # Completed election for results demo.
        #
        # Created ACTIVE on purpose: the ballots are cast against a live election
        # and the election is then closed through the real close/tally workflow
        # below. Inserting it as already-completed would leave a finished-looking
        # election with no candidate_results and no tally ever performed.
        completed_election = Election(
            organizer_id=organizer.id,
            title="Completed Organization Voting Event 2026",
            description="Completed demo election showing homomorphic tallying.",
            status=ElectionStatus.active,
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

        # Two votes for Daniel Wong, one each for Emily Chen and Farhan Aziz.
        # These are the inputs; the totals are whatever the tally computes.
        add_encrypted_ballot(db, completed_election, completed_voters[0], completed_candidates, completed_candidates[0])
        add_encrypted_ballot(db, completed_election, completed_voters[1], completed_candidates, completed_candidates[0])
        add_encrypted_ballot(db, completed_election, completed_voters[2], completed_candidates, completed_candidates[1])
        add_encrypted_ballot(db, completed_election, completed_voters[3], completed_candidates, completed_candidates[2])

        # Close through the production workflow: runs the homomorphic tally once,
        # writes candidate_results, flips the status to completed, and records the
        # election_closed and results_published audit events. The seed owns the
        # transaction, so the helper flushes without committing.
        _tally_and_complete(
            db,
            completed_election,
            organizer.id,
            close_reason="demo_seed",
            commit=False,
        )

        db.refresh(completed_election)
        stored_tally = verify_completed_tally(db, completed_election, completed_candidates)
        db.commit()

        print("Demo database seeded successfully.")
        print("")
        print("Login accounts (password is the value of DEMO_SEED_PASSWORD):")
        print("Admin:           admin@demo.com")
        print("Organizer:       organizer@demo.com")
        print("Voter:           voter1@demo.com")
        print("Voter:           voter2@demo.com")
        print("Suspended voter: suspended@demo.com")
        print("")
        print("Active voting event:")
        print("Community Leadership Voting Event 2026")
        print("")
        print("Completed voting event, tallied and verified from candidate_results:")
        for name, total in sorted(stored_tally.items(), key=lambda item: -item[1]):
            print(f"  {name} = {total}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        # Guard failures are operator errors, not crashes: report them plainly
        # without a traceback.
        print(f"seed_demo: {error}", file=sys.stderr)
        sys.exit(1)
