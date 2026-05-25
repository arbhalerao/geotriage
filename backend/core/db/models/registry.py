import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base


class _Registered:
    """
    the descriptor is stored rather than recomputed:
    the platform can't fan out to every registered image on each API request,
    and a workflow built against a model needs a stable record of what it claimed at the time
    """

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # from the descriptor
    image: Mapped[str] = mapped_column(String, nullable=False)
    descriptor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    admission: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # the checks it passed
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegisteredModel(_Registered, Base):
    __tablename__ = "registered_models"

    __table_args__ = (Index("ix_registered_models_enabled", "is_enabled"),)


class RegisteredProvider(_Registered, Base):
    __tablename__ = "registered_providers"

    __table_args__ = (Index("ix_registered_providers_enabled", "is_enabled"),)


class ProviderCollection(Base):
    """
    which provider owns a collection slug

    workflows store collection slugs as bare strings, so the slug has to name exactly one
    archive globally
    two providers declaring `sentinel-2-l2a` would otherwise both be registerable, and
    lookups would silently resolve to whichever happened to sort first — scoring real
    scenes from the wrong archive and producing plausible numbers

    the primary key is the namespace, so Postgres refuses the second claimant even if two
    registrations race
    """

    __tablename__ = "provider_collections"

    collection_slug: Mapped[str] = mapped_column(String, primary_key=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_providers.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (Index("ix_provider_collections_provider", "provider_id"),)
