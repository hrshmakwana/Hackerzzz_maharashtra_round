"""SQLModel engine/session and seed-on-start."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_URL = "sqlite:///data/blackbox.db"
_engines: dict[str, Engine] = {}


def resolve_url(url: Optional[str] = None) -> str:
    """Relative sqlite paths are resolved against the repo root, not the cwd."""
    url = url or os.getenv("DATABASE_URL") or DEFAULT_URL
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/") and ":memory:" not in url:
        path = ROOT / url[len(prefix):]
        path.parent.mkdir(parents=True, exist_ok=True)
        url = prefix + str(path)
    return url


def get_engine(url: Optional[str] = None) -> Engine:
    url = resolve_url(url)
    if url not in _engines:
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _record):  # noqa: ANN001
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        _engines[url] = engine
    return _engines[url]


def init_db(engine: Optional[Engine] = None) -> Engine:
    from . import models  # noqa: F401 - registers the tables

    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    return engine


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def run_count(engine: Optional[Engine] = None) -> int:
    from sqlalchemy import func

    from .models import Run

    with Session(engine or get_engine()) as s:
        return s.exec(select(func.count()).select_from(Run)).one()


def seed_if_empty(n: Optional[int] = None, engine: Optional[Engine] = None) -> int:
    """Fill an empty database with ``SEED_RUNS_ON_START`` simulated runs."""
    engine = init_db(engine)
    if run_count(engine) > 0:
        return 0
    n = int(os.getenv("SEED_RUNS_ON_START", "1500")) if n is None else n
    if n <= 0:
        return 0
    from agent_sim.generate import seed_database

    return seed_database(n, engine)
