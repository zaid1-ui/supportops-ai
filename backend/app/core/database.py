"""Database connection via SQLAlchemy (SQLite backend)."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import settings

# check_same_thread=False is required for SQLite under FastAPI's threadpool.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,  # SQL echo is noise; the events table is the real trace.
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def init_db() -> None:
    """Create all tables. Models are imported for side effects."""
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
