import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shuttlecube.domain.operations.models import OperationRun


def claim_next_run(
    db: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
    lease_duration: timedelta = timedelta(seconds=60),
    after_venue_id: str | None = None,
) -> OperationRun | None:
    claimed_at = now or datetime.now(UTC)
    eligibility = (
        or_(
            OperationRun.state == "queued",
            (OperationRun.state == "retry_scheduled")
            & (OperationRun.next_attempt_at <= claimed_at),
            (OperationRun.state == "running")
            & (OperationRun.lease_expires_at < claimed_at),
        ),
        or_(
            OperationRun.lease_expires_at.is_(None),
            OperationRun.lease_expires_at < claimed_at,
        ),
    )

    def statement(*, continue_after_last: bool):
        predicates = list(eligibility)
        if continue_after_last and after_venue_id is not None:
            predicates.append(OperationRun.venue_id > after_venue_id)
        return (
            select(OperationRun)
            .where(*predicates)
            .order_by(OperationRun.venue_id, OperationRun.created_at, OperationRun.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    run = db.scalar(statement(continue_after_last=True))
    if run is None and after_venue_id is not None:
        run = db.scalar(statement(continue_after_last=False))
    if run is None:
        return None
    run.state = "running"
    run.lease_owner = worker_id
    run.lease_expires_at = claimed_at + lease_duration
    if run.started_at is None:
        run.started_at = claimed_at
    db.flush()
    return run


class OperationsRunner:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        execute_claimed: Callable[[str], None],
        *,
        worker_id: str,
        poll_seconds: float = 1.0,
        lease_duration: timedelta = timedelta(seconds=60),
        startup_hooks: Sequence[Callable[[], None]] = (),
        periodic_hooks: Sequence[Callable[[], None]] = (),
        periodic_hook_seconds: float = 60.0,
    ) -> None:
        self._session_factory = session_factory
        self._execute_claimed = execute_claimed
        self._worker_id = worker_id
        self._poll_seconds = poll_seconds
        self._lease_duration = lease_duration
        self._startup_hooks = tuple(startup_hooks)
        self._periodic_hooks = tuple(periodic_hooks)
        self._periodic_hook_seconds = periodic_hook_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_venue_id: str | None = None

    async def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="operations-runner")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        for hook in self._startup_hooks:
            await asyncio.to_thread(hook)
        next_periodic_hook = time.monotonic()
        while not self._stop.is_set():
            if self._periodic_hooks and time.monotonic() >= next_periodic_hook:
                for hook in self._periodic_hooks:
                    await asyncio.to_thread(hook)
                next_periodic_hook = time.monotonic() + self._periodic_hook_seconds
            run_id: str | None = None
            with self._session_factory() as db:
                claimed = claim_next_run(
                    db,
                    worker_id=self._worker_id,
                    lease_duration=self._lease_duration,
                    after_venue_id=self._last_venue_id,
                )
                if claimed is not None:
                    run_id = claimed.id
                    self._last_venue_id = claimed.venue_id
                    db.commit()
            if run_id is not None:
                await asyncio.to_thread(self._execute_claimed, run_id)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass
