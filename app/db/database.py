"""Database engine and session management."""
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
)


def init_db() -> None:
    """Create tables if they do not exist (MVP convenience)."""
    from app.db import models  # noqa: F401  (ensure models are registered)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
