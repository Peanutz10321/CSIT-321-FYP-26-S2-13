import enum
import uuid
from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class UserRole(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    system_admin = "system_admin"


class UserStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    pending = "pending"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    role = Column(Enum(UserRole, name="user_role"), nullable=False)
    status = Column(Enum(UserStatus, name="user_status"), nullable=False, default=UserStatus.active)

    institution_id = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=False, unique=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    elections = relationship("Election", back_populates="teacher")
    election_voter_records = relationship("ElectionVoter", back_populates="student")
    audit_logs = relationship("AuditLog", back_populates="actor")