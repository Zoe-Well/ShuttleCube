from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from shuttlecube.infrastructure.database.base import Base, IdMixin, TimestampMixin


class IdempotencyRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_records"
    scope: Mapped[str] = mapped_column(String(100), index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    response: Mapped[dict[str, object]] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)


def find_idempotent(session: Session, scope: str, key: str) -> dict[str, object] | None:
    record = session.query(IdempotencyRecord).filter_by(scope=scope, key=key).one_or_none()
    return record.response if record else None


def save_idempotent(session: Session, scope: str, key: str, response: dict[str, object]) -> None:
    session.add(IdempotencyRecord(scope=scope, key=key, response=response))
