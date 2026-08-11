from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import require_scope_capability
from shuttlecube.application.queries.dashboard import (
    EndingWithinDays,
    get_dashboard,
    get_pending_attendance,
)
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Dashboard"])


def json_values(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: json_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_values(item) for item in value]
    return value


@router.get("/dashboard")
def dashboard(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.report.read"))
    ],
    business_date: date | None = None,
    ending_within_days: EndingWithinDays = EndingWithinDays.DAYS_30,
) -> object:
    result = get_dashboard(
        db,
        scope,
        business_date or date.today(),
        ending_within_days=ending_within_days,
    )
    if "operations.report.financial.read" not in scope.capabilities:
        result.pop("month_finance", None)
    return json_values(result)


@router.get("/dashboard/pending-attendance")
def pending_attendance(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.case.read"))
    ],
    business_date: date | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "session_id": item.session.id,
            "class_id": item.fixed_class.id,
            "class_name": item.fixed_class.name,
            "sequence_number": item.session.sequence_number,
            "scheduled_start": item.session.scheduled_start,
            "scheduled_end": item.session.scheduled_end,
            "coach_name": item.coach_name,
            "active_enrollment_count": item.active_enrollment_count,
        }
        for item in get_pending_attendance(db, scope, business_date or date.today())
    ]
