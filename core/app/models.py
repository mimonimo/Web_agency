"""BRIEF §6 데이터 모델.

여기 정한 컬럼명이 이후 모든 Phase 의 계약이다. 바꾸려면 BRIEF 부터 고쳐야 한다.
모든 쓰기 요청은 AuditLog 에 남는다 — 예외 없다 (BRIEF §6 마지막 줄, 인수 #25).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# ── 역할 11개. 이 문자열이 노드 ID 이자 A2A 에이전트 이름이자 ────────────
#    agents/<role>/AGENT.md 경로다. 어디서든 같은 문자열을 쓴다 (BRIEF §1.3).
ROLES: tuple[str, ...] = (
    "pm",
    "planner",
    "sales",
    "sysadmin",
    "designer",
    "frontend",
    "backend",
    "dba",
    "security",
    "qa",
    "customer",
)

# 한글 표기는 UI 에서만 매핑한다 (BRIEF §1.3).
ROLE_DISPLAY: dict[str, str] = {
    "pm": "관리",
    "planner": "기획",
    "sales": "영업",
    "sysadmin": "인프라",
    "designer": "디자인",
    "frontend": "프론트엔드",
    "backend": "백엔드",
    "dba": "DB",
    "security": "보안",
    "qa": "QA",
    "customer": "고객",
}


# ── 상태 열거형 (BRIEF §3.2 / §3.3) ────────────────────────────────────
class CycleStatus(str, enum.Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"      # 게이트 도달 — 사람 대기
    FAILED = "FAILED"
    DONE = "DONE"


class StepStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    REJECTED = "REJECTED"          # 게이트 반려 → 지정된 step 으로 되감기
    FAILED = "FAILED"              # 재시도 가능
    SKIPPED = "SKIPPED"            # 강사가 건너뜀
    WAITING_HUMAN = "WAITING_HUMAN"  # 커스터마이징 게이트 등


class NodeStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class SpecStatus(str, enum.Enum):
    DRAFT = "draft"
    CUSTOMIZED = "customized"


class OrderKind(str, enum.Enum):
    NEW = "new"
    CHANGE = "change"
    DEFECT = "defect"
    SECURITY = "security"


class OrderSource(str, enum.Enum):
    ORDER_SITE = "order_site"
    INQUIRY = "inquiry"
    MANUAL = "manual"


class MessageKind(str, enum.Enum):
    REQUEST = "request"
    RESPONSE = "response"
    REJECT = "reject"
    MIRROR = "mirror"


class CycleMode(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# ── 테이블 ─────────────────────────────────────────────────────────────
class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    a2a_url: Mapped[str] = mapped_column(String(256))
    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus, native_enum=False), default=NodeStatus.DOWN
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dgx_host: Mapped[str | None] = mapped_column(String(64))
    card: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = _ts()


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[OrderSource] = mapped_column(Enum(OrderSource, native_enum=False))
    kind: Mapped[OrderKind] = mapped_column(Enum(OrderKind, native_enum=False))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    requester: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = _ts()

    cycles: Mapped[list["Cycle"]] = relationship(back_populates="order")


class Cycle(Base):
    __tablename__ = "cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    pipeline: Mapped[str] = mapped_column(String(64))
    status: Mapped[CycleStatus] = mapped_column(
        Enum(CycleStatus, native_enum=False), default=CycleStatus.READY
    )
    current_step: Mapped[str | None] = mapped_column(String(16))
    mode: Mapped[CycleMode] = mapped_column(
        Enum(CycleMode, native_enum=False), default=CycleMode.AUTO
    )
    # 같은 Order 로 Cycle 을 여러 번 돌린다 — 이게 수업의 핵심 장치다 (BRIEF §3.1)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()

    order: Mapped["Order"] = relationship(back_populates="cycles")
    steps: Mapped[list["Step"]] = relationship(back_populates="cycle")


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"), index=True)
    step_key: Mapped[str] = mapped_column(String(16))   # S1, S2, ...
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, native_enum=False), default=StepStatus.PENDING
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    input_ref: Mapped[str | None] = mapped_column(String(512))
    output_ref: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)   # 에러 메시지는 한국어 (BRIEF §15-4)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cycle: Mapped["Cycle"] = relationship(back_populates="steps")


class AgentSpec(Base):
    """AGENT.md 한 개의 생명주기 (BRIEF §4).

    [없음] → S2 기획이 생성 → draft → 학생이 커밋 → customized → 사이클 시작 → active
    """

    __tablename__ = "agent_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[SpecStatus] = mapped_column(
        Enum(SpecStatus, native_enum=False), default=SpecStatus.DRAFT
    )
    path: Mapped[str] = mapped_column(String(512))
    hash: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 학생이 무엇을 추가했는지가 오늘의 평가 데이터다 (BRIEF §4.2)
    diff_ref: Mapped[str | None] = mapped_column(String(512))


class Message(Base):
    """A2A 미러링. 미러링하지 않은 메시지는 감사 로그에도 안 남는다 (BRIEF §5.3)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("cycles.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("steps.id"))
    from_role: Mapped[str] = mapped_column(String(32))
    to_role: Mapped[str] = mapped_column(String(32))
    kind: Mapped[MessageKind] = mapped_column(Enum(MessageKind, native_enum=False))
    summary: Mapped[str | None] = mapped_column(String(500))
    payload_ref: Mapped[str | None] = mapped_column(String(512))
    ts: Mapped[datetime] = _ts()


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"), index=True)
    from_role: Mapped[str] = mapped_column(String(32))
    to_role: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    dod: Mapped[str | None] = mapped_column(Text)          # Definition of Done
    status: Mapped[str] = mapped_column(String(32), default="todo")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    reason: Mapped[str | None] = mapped_column(Text)       # 반려 사유
    due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("steps.id"))
    role: Mapped[str | None] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(512))
    size: Mapped[int | None] = mapped_column(BigInteger)
    ts: Mapped[datetime] = _ts()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(256))
    payload: Mapped[dict | None] = mapped_column(JSON)
    ts: Mapped[datetime] = _ts()
