from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, JSON, MetaData, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


PORTFOLIO_SCHEMA = "portfolio"


class Base(DeclarativeBase):
    metadata = MetaData(schema=PORTFOLIO_SCHEMA)


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), index=True)
    subject: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    verification_digest: Mapped[str] = mapped_column(String(64), unique=True)
    verification_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ContactAttempt(Base):
    __tablename__ = "contact_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(String(64))
    email_hash: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_contact_attempt_ip_created", "ip_hash", "created_at"),
        Index("ix_contact_attempt_email_created", "email_hash", "created_at"),
    )


class ContactAuditEvent(Base):
    __tablename__ = "contact_audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("portfolio.contact_messages.id", ondelete="SET NULL"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
