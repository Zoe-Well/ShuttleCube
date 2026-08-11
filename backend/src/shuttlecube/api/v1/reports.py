from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.v1.dashboard import json_values
from shuttlecube.application.operations.access import require_scope_capability
from shuttlecube.application.queries.operations_report import get_operations_report
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Dashboard"])


@router.get("/reports/operations")
def operations_report(
    from_: Annotated[date, Query(alias="from")],
    to: date,
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.report.financial.read"))
    ],
) -> object:
    return json_values(get_operations_report(db, scope, from_, to))
