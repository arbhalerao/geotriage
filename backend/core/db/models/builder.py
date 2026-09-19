import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base
from core.db.models.enums import BuilderRunStatus


class BuilderRun(Base):

    __tablename__ = "builder_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[BuilderRunStatus] = mapped_column(SAEnum(BuilderRunStatus, native_enum=False, length=10), nullable=False, default=BuilderRunStatus.queued)
    conversation: Mapped[list] = mapped_column(JSONB, nullable=False)
    # what the agent is doing, oldest first, e.g. "Looking up Dhaka"
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
