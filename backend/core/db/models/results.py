import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Boolean,
    Float,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Enum as SAEnum,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from core.db.base import Base
from core.db.models.enums import WorkflowItemStatus, ModelRunStatus, Severity


class WorkflowItem(Base):
    __tablename__ = "workflow_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    stac_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stac_items.id"), nullable=False)
    status: Mapped[WorkflowItemStatus] = mapped_column(
        SAEnum(WorkflowItemStatus, native_enum=False, length=20),
        nullable=False,
        default=WorkflowItemStatus.queued,
    )
    overall_severity: Mapped[Severity | None] = mapped_column(SAEnum(Severity, native_enum=False, length=10), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("workflow_id", "stac_item_id", name="uq_workflow_items_workflow_stac"),
        Index("ix_workflow_items_workflow_status", "workflow_id", "status"),
        Index("ix_workflow_items_workflow_severity", "workflow_id", "overall_severity"),
        Index("ix_workflow_items_stac_item_id", "stac_item_id"),
    )


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_items.id", ondelete="CASCADE"), nullable=False)
    workflow_model_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_model_configs.id"), nullable=False)
    model_slug: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ModelRunStatus] = mapped_column(
        SAEnum(ModelRunStatus, native_enum=False, length=20),
        nullable=False,
        default=ModelRunStatus.queued,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("workflow_item_id", "workflow_model_config_id", name="uq_model_runs_item_config"),
        Index("ix_model_runs_workflow_item_id", "workflow_item_id"),
        Index("ix_model_runs_status", "status"),
        Index("ix_model_runs_workflow_model_config_id", "workflow_model_config_id"),
    )


class ModelScore(Base):
    __tablename__ = "model_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False)
    score_name: Mapped[str] = mapped_column(String, nullable=False)
    score_value: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity, native_enum=False, length=10), nullable=False)
    __table_args__ = (
        UniqueConstraint("model_run_id", "score_name", name="uq_model_scores_run_name"),
        Index("ix_model_scores_run_primary", "model_run_id", "is_primary"),
        Index("ix_model_scores_run_severity", "model_run_id", "severity"),
    )
