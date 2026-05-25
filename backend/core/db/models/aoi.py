import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import String, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from core.db.base import Base


class Aoi(Base):
    __tablename__ = "aois"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # generic rather than POLYGON: the API accepts a MultiPolygon AOI,
    # which is what a user drawing two disjoint areas produces
    geometry: Mapped[str] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_aois_geometry", "geometry", postgresql_using="gist"),)
