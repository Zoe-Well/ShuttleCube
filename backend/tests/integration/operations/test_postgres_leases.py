from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy.orm import Session, sessionmaker

from shuttlecube.application.operations.runner import claim_next_run
from shuttlecube.domain.operations.models import OperationRun


@pytest.mark.postgres
def test_postgres_skip_locked_allows_only_one_worker_to_claim_a_run(
    postgres_db: Session,
) -> None:
    now = datetime(2026, 8, 9, 8, tzinfo=UTC)
    run = OperationRun(
        organization_id="organization-1",
        venue_id="venue-1",
        run_type="scan",
        trigger_type="scheduled",
        workflow_key="scheduled_scan",
        workflow_version=1,
        policy_key="default_operations",
        policy_version=1,
        toolset_version=1,
        input_refs=[],
        input_hash="input-1",
        checkpoint={},
        max_steps=2,
        max_model_calls=0,
        max_tool_calls=0,
        max_write_calls=0,
        deadline_at=now + timedelta(minutes=5),
    )
    postgres_db.add(run)
    postgres_db.commit()
    maker = sessionmaker(bind=postgres_db.get_bind(), expire_on_commit=False)
    barrier = Barrier(2)

    def claim(worker_id: str) -> str | None:
        with maker() as session:
            barrier.wait()
            claimed = claim_next_run(
                session,
                worker_id=worker_id,
                now=now,
                lease_duration=timedelta(seconds=30),
            )
            session.commit()
            return claimed.id if claimed else None

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed_ids = list(executor.map(claim, ("worker-a", "worker-b")))

    assert claimed_ids.count(run.id) == 1
    assert claimed_ids.count(None) == 1
