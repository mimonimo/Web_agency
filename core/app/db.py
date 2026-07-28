"""DB 세션/엔진. 상태 전이 로직은 여기에 절대 넣지 않는다 (BRIEF §15-1)."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+pysqlite:///{ROOT / 'repo' / 'agora.db'}",
)

# SQLite 상대경로는 실행 위치에 따라 달라진다. 리포 기준으로 고정한다.
if DATABASE_URL.startswith("sqlite") and ":///./" in DATABASE_URL:
    rel = DATABASE_URL.split(":///./", 1)[1]
    target = (ROOT / rel).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite+pysqlite:///{target}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI 의존성. 요청 하나당 세션 하나."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
