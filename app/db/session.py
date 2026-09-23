from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Read/write engine: used by ingestion and by the app for its own bookkeeping
# tables (documents, document_chunks, query_log). Never used to execute
# LLM-generated SQL.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Read-only engine: the ONLY engine allowed to execute validated, generated SQL.
# Connects as a Postgres role with SELECT-only grants (see scripts/init_db_roles.sql),
# so even a validator bug can't result in a write.
readonly_engine = create_engine(
    settings.readonly_database_url,
    pool_pre_ping=True,
    execution_options={"postgresql_readonly": True},
)
ReadOnlySessionLocal = sessionmaker(bind=readonly_engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_readonly_db() -> Generator[Session, None, None]:
    db = ReadOnlySessionLocal()
    try:
        yield db
    finally:
        db.close()
