import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Integer,
    ForeignKey,
    CheckConstraint,
    Index,
    UniqueConstraint,
    Enum as SAEnum,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from core.db.base import Base
from core.db.models.enums import WorkflowStatus, TimeMode, CompatibilityLevel


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aoi_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("aois.id"), nullable=False)
    aoi_filter_mode: Mapped[str] = mapped_column(String, nullable=False, server_default="intersects")
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    time_mode: Mapped[TimeMode] = mapped_column(SAEnum(TimeMode, native_enum=False, length=20), nullable=False, default=TimeMode.historical)
    time_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    poll_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        SAEnum(WorkflowStatus, native_enum=False, length=30),
        nullable=False,
        default=WorkflowStatus.draft,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("time_end > time_start", name="ck_workflows_time_range"),
        Index("ix_workflows_aoi_id", "aoi_id"),
        Index("ix_workflows_status", "status"),
    )


class WorkflowCollection(Base):
    __tablename__ = "workflow_collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    collection_slug: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("workflow_id", "collection_slug", name="uq_workflow_collections_workflow_collection"),)


class WorkflowModelConfig(Base):
    __tablename__ = "workflow_model_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    model_slug: Mapped[str] = mapped_column(String, nullable=False)
    user_label: Mapped[str | None] = mapped_column(String, nullable=True)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("workflow_id", "model_slug", name="uq_workflow_model_configs_workflow_model"),)


class WorkflowModelCollectionConfig(Base):
    __tablename__ = "workflow_model_collection_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    workflow_model_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_model_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_slug: Mapped[str] = mapped_column(String, nullable=False)
    compatibility_level: Mapped[CompatibilityLevel] = mapped_column(SAEnum(CompatibilityLevel, native_enum=False, length=20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("workflow_model_config_id", "collection_slug", name="uq_wf_model_collection_config"),
        Index("ix_wf_model_collection_configs_workflow_enabled", "workflow_id", "is_enabled"),
    )
