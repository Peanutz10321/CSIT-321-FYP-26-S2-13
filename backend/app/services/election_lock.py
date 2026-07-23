"""
Election row locking — the shared protocol between voting and closing.

Both the vote path and the close path take a lock on the *same* election row, so
a ballot can never be committed against an election that is concurrently being
tallied. The two lock modes differ deliberately:

* Voting takes a SHARED lock (``FOR SHARE``). Concurrent voters do not block each
  other, which matters because Paillier encryption happens inside the vote
  transaction and would otherwise serialise every voter in the election.
* Closing takes an EXCLUSIVE lock (``FOR UPDATE``). It conflicts with the shared
  locks, so a close waits for in-flight votes to commit and blocks new ones.

The resulting guarantee: a vote either commits before the close acquires its
exclusive lock — in which case its ballot is in the tallied set — or it waits,
then re-reads the row and finds the election completed, and is rejected. A
successful receipt therefore always corresponds to a ballot in the tally.

PostgreSQL queues lock requests, so a waiting exclusive request is not starved by
shared requests that arrive after it.

SQLite: SQLAlchemy omits the locking clause entirely. SQLite serialises writers
at the database level, so the status re-read under the same transaction still
gives the correct result; the concurrency guarantees above are only meaningfully
exercised on PostgreSQL, which is why the race tests require it.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.election import Election


def _locked(db: Session, election_id: UUID, *, read: bool) -> Election | None:
    """Re-read the election row under a lock held until the transaction ends.

    populate_existing() forces the locked read to overwrite any copy already in
    the session, so a caller that read the row earlier still sees the committed
    state rather than a stale in-session copy.
    """
    return (
        db.query(Election)
        .filter(Election.id == election_id)
        .populate_existing()
        .with_for_update(read=read)
        .first()
    )


def lock_election_for_vote(db: Session, election_id: UUID) -> Election | None:
    """Shared lock. Blocks a concurrent close, not other voters."""
    return _locked(db, election_id, read=True)


def lock_election_for_close(db: Session, election_id: UUID) -> Election | None:
    """Exclusive lock. Blocks voters and any other close."""
    return _locked(db, election_id, read=False)
