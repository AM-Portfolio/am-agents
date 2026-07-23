from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Literal

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

StoreMode = Literal["json", "dual", "db"]

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def store_mode() -> StoreMode:
    mode = (settings.spt_store or "db").strip().lower()
    if mode not in {"json", "dual", "db"}:
        return "db"
    return mode  # type: ignore[return-value]


def database_url() -> str:
    if settings.spt_database_url:
        return settings.spt_database_url
    path = Path(settings.data_dir) / "spt.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve().as_posix()}"


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine
    url = database_url()
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_pre_ping"] = True
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _sqlite_pragma(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables (Alembic-compatible Base). Safe to call repeatedly."""
    from app.db.models import Base

    engine = get_engine()
    Base.metadata.create_all(bind=engine, checkfirst=True)


def dispose_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def db_health() -> dict:
    mode = store_mode()
    if mode == "json":
        return {"store": mode, "db": "skipped", "ok": True}
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "store": mode,
            "db": "ok",
            "ok": True,
            "url_scheme": database_url().split(":", 1)[0],
        }
    except Exception as exc:
        return {"store": mode, "db": "error", "ok": False, "error": str(exc)}
