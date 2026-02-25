import os
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _build_postgres_url_from_parts() -> Optional[str]:
    """
    Build a PostgreSQL URL from individual env vars.

    We intentionally support both:
    - POSTGRES_URL (preferred if available)
    - POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_PORT (when URL isn't provided)

    Returns None if insufficient information is provided.
    """
    host = os.getenv("POSTGRES_URL")
    if host:
        # In this project, POSTGRES_URL is expected to be the hostname/address.
        # Do not assume it is a full DSN; we construct a DSN below.
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        db = os.getenv("POSTGRES_DB")
        port = os.getenv("POSTGRES_PORT")
        if user and password and db and port:
            return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
        return None

    return None


def _get_database_url() -> str:
    """
    Resolve the database URL from environment variables.

    Environment variables required (provided by the DB container integration):
    - POSTGRES_URL
    - POSTGRES_USER
    - POSTGRES_PASSWORD
    - POSTGRES_DB
    - POSTGRES_PORT
    """
    url = _build_postgres_url_from_parts()
    if url:
        return url

    # Fallback: allow full DSN via DATABASE_URL if present (common deployment pattern).
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        # Normalize to SQLAlchemy driver format if user gave a plain postgresql:// URL.
        if dsn.startswith("postgresql://"):
            return dsn.replace("postgresql://", "postgresql+psycopg2://", 1)
        return dsn

    raise RuntimeError(
        "Database configuration missing. Set POSTGRES_URL, POSTGRES_USER, "
        "POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT (or DATABASE_URL)."
    )


_ENGINE: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine() -> Engine:
    """Get a singleton SQLAlchemy engine."""
    global _ENGINE, _SessionLocal

    if _ENGINE is None:
        database_url = _get_database_url()
        _ENGINE = create_engine(
            database_url,
            pool_pre_ping=True,
            future=True,
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE, future=True)

    return _ENGINE


def get_sessionmaker() -> sessionmaker:
    """Get the configured sessionmaker (requires engine to be initialized)."""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and guarantees close()."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
