"""Durable data in Postgres.

Redis keeps live, short-lived state (streams, locks, rate limits, the
in-progress interview context). Everything that must survive a Redis loss
lives here.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Stored lowercase; unique across the platform
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # admin | recruiter
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created()


class JobRole(Base):
    __tablename__ = "job_roles"

    # Role ids are chosen by recruiters and global (scoring/rankings key on them)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    # NULL for roles created before organizations existed (platform admins only)
    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    candidate_name: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    role_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    interview_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    dsa_problem_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # The candidate must use the locked desktop app, not a browser
    require_secure_app: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set exactly once (single use); unique so two sessions can't claim one invite
    used_session_id: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Withdrawn by the organization before it was used; the link stops working
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Candidate background, from the organization (not asked at the interview):
    # the interviewer asks about it and checks claims against it
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    other_links: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LinkedIn blocks automated reading; its "Save to PDF" export is read instead
    linkedin_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class Interview(Base):
    """One interview session: who it belongs to and its durable outcome."""

    __tablename__ = "interviews"

    session_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    # NULL for sessions without an owner (e.g. scalability demo): platform admins only
    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    invite_id: Mapped[str | None] = mapped_column(
        ForeignKey("invites.id", ondelete="SET NULL"), nullable=True
    )
    candidate_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    interview_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dsa_problem_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    created_at: Mapped[datetime] = _created()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Recording (private object storage; served through short-lived signed URLs)
    recording_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    egress_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Outcome, written by the brain worker when the interview concludes
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    analytics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    skill_tree: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    dsa_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    integrity: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    transcript: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    report_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Hiring decision by the organization: advance | hold | reject
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsentRecord(Base):
    """What a candidate agreed to, and when (filled in by the Phase 6 consent screen)."""

    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interviews.session_id", ondelete="CASCADE"), nullable=False, index=True
    )
    notice_version: Mapped[str] = mapped_column(String(40), nullable=False)
    accepted_at: Mapped[datetime] = _created()
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class AuditEvent(Base):
    """Who did what, for security reviews and data-access questions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = _created()
    org_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user|candidate|system
    actor_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (Index("ix_audit_log_org_at", "org_id", "at"),)
