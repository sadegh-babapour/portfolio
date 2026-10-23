from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.contact.models import Base


class ResumeEntry(Base):
    __tablename__ = "resume_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    position: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(160))
    organization: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(String(600))
    highlights: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
