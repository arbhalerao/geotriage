import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import String, Float, DateTime, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from core.db.base import Base


class StacItem(Base):
    __tablename__ = "stac_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_slug: Mapped[str] = mapped_column(String, nullable=False)
    stac_item_id: Mapped[str] = mapped_column(String, nullable=False)
    geometry: Mapped[str] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assets: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("collection_slug", "stac_item_id", name="uq_stac_items_collection_item"),
        Index("ix_stac_items_geometry", "geometry", postgresql_using="gist"),
        Index("ix_stac_items_collection_datetime", "collection_slug", "datetime"),
        Index("ix_stac_items_cloud_cover", "cloud_cover"),
    )
