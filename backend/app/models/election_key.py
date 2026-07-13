import uuid

from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class ElectionKey(Base):
    """
    Fernet-encrypted Paillier private key, kept OUT of the elections table so
    plain DB read access to election rows never yields decryption capability.
    Decryptable only with KEYSTORE_MASTER_SECRET (held in the environment).
    """

    __tablename__ = "election_keys"

    election_id = Column(
        UUID(as_uuid=True),
        ForeignKey("elections.id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    encrypted_private_key = Column(Text, nullable=False)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
