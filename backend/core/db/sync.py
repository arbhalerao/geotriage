from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings

# swap the driver properly rather than string-replacing the URL,
# which silently did nothing for a plain "postgresql://" and left the async driver in place
_sync_url = make_url(settings.DATABASE_URL).set(drivername="postgresql+psycopg2")

engine = create_engine(_sync_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def get_session() -> Session:
    with SessionLocal() as session:
        yield session
