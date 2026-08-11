from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.detectors import DetectorRegistry
from shuttlecube.application.operations.scan_runs import enqueue_scan_run
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.scheduling.court import Venue


def schedule_due_scans(
    session_factory: Callable[[], Session],
    *,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    with session_factory() as db:
        venues = db.scalars(
            select(Venue).where(Venue.active_for_operations.is_(True))
        ).all()
        enabled_keys = sorted(
            item.detector_key for item in DetectorRegistry.default().enabled()
        )
        for venue in venues:
            policy = db.scalar(
                select(OperationsPolicy).where(
                    OperationsPolicy.organization_id == venue.organization_id,
                    OperationsPolicy.venue_id == venue.id,
                    OperationsPolicy.state == "active",
                    OperationsPolicy.policy_key == "default_operations",
                )
            )
            if policy is None:
                continue
            scope = RequestScope(
                organization_id=venue.organization_id,
                venue_id=venue.id,
                user_id="system",
                membership_id="system",
                capabilities=frozenset(),
            )
            quarter = current.replace(
                minute=(current.minute // 15) * 15,
                second=0,
                microsecond=0,
            )
            enqueue_scan_run(
                db,
                scope=scope,
                policy=policy,
                detector_keys=["attendance.overdue"],
                trigger_type="scheduled",
                trigger_key=f"attendance-15m:{quarter.isoformat()}",
                now=current,
            )
            business_date = current.astimezone(ZoneInfo(venue.timezone)).date()
            enqueue_scan_run(
                db,
                scope=scope,
                policy=policy,
                detector_keys=enabled_keys,
                trigger_type="startup",
                trigger_key=f"daily-catchup:{business_date.isoformat()}",
                now=current,
            )
        db.commit()
