import uuid

from sqlalchemy import String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from core.db.base import Base


class ThresholdConfig(Base):
    __tablename__ = "threshold_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_model_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_model_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    score_name: Mapped[str] = mapped_column(String, nullable=False)
    green_min: Mapped[float] = mapped_column(Float, nullable=False)
    green_max: Mapped[float] = mapped_column(Float, nullable=False)
    yellow_min: Mapped[float] = mapped_column(Float, nullable=False)
    yellow_max: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("workflow_model_config_id", "score_name", name="uq_threshold_configs_config_score"),)
