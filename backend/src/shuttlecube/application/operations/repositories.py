from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError, ConcurrentChange
from shuttlecube.domain.operations.models import (
    OperationCase,
    OperationEvent,
    OperationRun,
    OperationToolCall,
)


class OperationsRepository:
    def __init__(self, db: Session, scope: RequestScope) -> None:
        self.db = db
        self.scope = scope

    def get_case(self, case_id: str) -> OperationCase:
        item = self.db.scalar(
            select(OperationCase).where(
                OperationCase.id == case_id,
                OperationCase.organization_id == self.scope.organization_id,
                OperationCase.venue_id == self.scope.venue_id,
            )
        )
        if item is None:
            raise BusinessError(404, "scope_not_found", "运营案件不存在")
        return item

    def get_run(self, run_id: str) -> OperationRun:
        item = self.db.scalar(
            select(OperationRun).where(
                OperationRun.id == run_id,
                OperationRun.organization_id == self.scope.organization_id,
                OperationRun.venue_id == self.scope.venue_id,
            )
        )
        if item is None:
            raise BusinessError(404, "scope_not_found", "运行记录不存在")
        return item

    def assert_version(self, item: OperationCase | OperationRun, expected_version: int) -> None:
        if item.version != expected_version:
            raise ConcurrentChange()

    def append_event(
        self,
        run: OperationRun,
        *,
        event_type: str,
        actor_type: str,
        trace_id: str,
        payload_redacted: dict[str, object],
        payload_hash: str,
        actor_id: str | None = None,
        request_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> OperationEvent:
        last_sequence = self.db.scalar(
            select(func.max(OperationEvent.sequence)).where(OperationEvent.run_id == run.id)
        )
        event = OperationEvent(
            organization_id=self.scope.organization_id,
            venue_id=self.scope.venue_id,
            case_id=run.case_id,
            run_id=run.id,
            sequence=int(last_sequence or 0) + 1,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            trace_id=trace_id,
            request_id=request_id,
            payload_redacted=payload_redacted,
            payload_hash=payload_hash,
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def find_tool_result(
        self,
        *,
        tool_key: str,
        idempotency_key: str,
    ) -> OperationToolCall | None:
        return self.db.scalar(
            select(OperationToolCall).where(
                OperationToolCall.organization_id == self.scope.organization_id,
                OperationToolCall.venue_id == self.scope.venue_id,
                OperationToolCall.tool_key == tool_key,
                OperationToolCall.idempotency_key == idempotency_key,
            )
        )
