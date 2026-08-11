from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope, require_csrf
from shuttlecube.api.errors import ConcurrentChange
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.commands.expenses import create_expense, void_expense
from shuttlecube.application.commands.other_incomes import create_other_income, void_other_income
from shuttlecube.application.commands.payments import record_payment, void_payment
from shuttlecube.application.commands.receivables import adjust_receivable
from shuttlecube.application.commands.refunds import record_refund, void_refund
from shuttlecube.application.operations.access import (
    require_scope_capability,
    scoped_object_or_404,
)
from shuttlecube.application.queries.business_display import source_business_name
from shuttlecube.application.queries.receivables import (
    ReceivableSummary,
    list_receivable_summaries,
    receivable_summary,
)
from shuttlecube.domain.finance.models import Expense, OtherIncome, Payment, Receivable, Refund
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Finance"])


class PaymentWrite(BaseModel):
    paid_at: datetime
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=40)
    payer_name: str | None = None
    received_by: str | None = None
    notes: str | None = None


class RefundWrite(BaseModel):
    payment_id: str | None = None
    refunded_at: datetime
    suggested_amount: Decimal | None = None
    actual_amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1)
    lesson_units_to_remove: int = Field(default=0, ge=0)


class ExpenseWrite(BaseModel):
    category: str
    spent_at: datetime
    amount: Decimal = Field(gt=0)
    payee: str = Field(min_length=1)
    payment_method: str = Field(min_length=1)
    source_type: str | None = None
    source_id: str | None = None
    notes: str | None = None


class OtherIncomeWrite(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    received_at: datetime
    amount: Decimal = Field(gt=0)
    payer: str = Field(min_length=1, max_length=160)
    payment_method: str = Field(min_length=1, max_length=40)
    notes: str | None = None


class VoidWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReceivableAdjustWrite(VoidWrite):
    actual_amount: Decimal = Field(ge=0)
    version: int


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def summary_dict(db: Session, item: Receivable) -> dict[str, object]:
    return api_summary(db, receivable_summary(db, item))


def api_summary(db: Session, summary: ReceivableSummary) -> dict[str, object]:
    values = summary.to_dict()
    result = {
        key: float(value) if isinstance(value, Decimal) else value for key, value in values.items()
    }
    # Keep the public finance API compatible with the existing receivable shape.
    # ``receivable_id`` is the internal query DTO field used to make joins explicit.
    result["id"] = result.pop("receivable_id")
    result["business_name"] = source_business_name(db, summary.source_type, summary.source_id)
    return result


@router.get("/receivables")
def get_receivables(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.report.financial.read"))
    ],
    source_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    return [
        api_summary(db, item)
        for item in list_receivable_summaries(
            db, scope=scope, source_type=source_type, status=status
        )
    ]


@router.get("/receivables/{receivable_id}")
def get_receivable(
    receivable_id: str,
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.report.financial.read"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Receivable, receivable_id, scope)
    result = summary_dict(db, item)
    result["payments"] = [
        {
            "id": row.id,
            "paid_at": row.paid_at,
            "amount": row.amount,
            "method": row.method,
            "payer_name": row.payer_name,
            "received_by": row.received_by,
            "status": row.status,
            "notes": row.notes,
            "void_reason": row.void_reason,
        }
        for row in db.scalars(
            select(Payment).where(
                Payment.organization_id == scope.organization_id,
                Payment.venue_id == scope.venue_id,
                Payment.receivable_id == item.id,
            )
        ).all()
    ]
    result["refunds"] = [
        {
            "id": row.id,
            "refunded_at": row.refunded_at,
            "payment_id": row.payment_id,
            "suggested_amount": row.suggested_amount,
            "actual_amount": row.actual_amount,
            "reason": row.reason,
            "status": row.status,
            "void_reason": row.void_reason,
        }
        for row in db.scalars(
            select(Refund).where(
                Refund.organization_id == scope.organization_id,
                Refund.venue_id == scope.venue_id,
                Refund.receivable_id == item.id,
            )
        ).all()
    ]
    result["lesson_balance"] = (
        balance(db, item.source_id)
        if item.source_type in {"enrollment", "private_package"}
        else None
    )
    return result


@router.patch("/receivables/{receivable_id}")
def patch_receivable(
    receivable_id: str,
    payload: ReceivableAdjustWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Receivable, receivable_id, scope)
    if item.version != payload.version:
        raise ConcurrentChange()
    adjust_receivable(
        db,
        item,
        actual_amount=payload.actual_amount,
        reason=payload.reason,
        actor_id=user.id,
        request_id=request_id(request),
    )
    return summary_dict(db, item)


@router.post("/receivables/{receivable_id}/payments", status_code=201)
def post_payment(
    receivable_id: str,
    payload: PaymentWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Receivable, receivable_id, scope)
    record_payment(
        db,
        item,
        **payload.model_dump(),
        actor_id=user.id,
        idempotency_key=idempotency_key,
        request_id=request_id(request),
    )
    return summary_dict(db, item)


@router.post("/receivables/{receivable_id}/refunds", status_code=201)
def post_refund(
    receivable_id: str,
    payload: RefundWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Receivable, receivable_id, scope)
    refund = record_refund(
        db,
        item,
        **payload.model_dump(),
        actor_id=user.id,
        idempotency_key=idempotency_key,
        request_id=request_id(request),
    )
    return {"refund_id": refund.id, "receivable": summary_dict(db, item)}


@router.post("/payments/{payment_id}/void")
def post_void_payment(
    payment_id: str,
    payload: VoidWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Payment, payment_id, scope)
    void_payment(db, item, reason=payload.reason, actor_id=user.id, request_id=request_id(request))
    return {"id": item.id, "status": item.status}


@router.post("/refunds/{refund_id}/void")
def post_void_refund(
    refund_id: str,
    payload: VoidWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Refund, refund_id, scope)
    void_refund(db, item, reason=payload.reason, actor_id=user.id, request_id=request_id(request))
    return {"id": item.id, "status": item.status}


@router.get("/expenses")
def get_expenses(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.report.financial.read"))
    ],
) -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "category": item.category,
            "spent_at": item.spent_at,
            "amount": item.amount,
            "payee": item.payee,
            "payment_method": item.payment_method,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "status": item.status,
            "notes": item.notes,
            "void_reason": item.void_reason,
        }
        for item in db.scalars(
            select(Expense)
            .where(
                Expense.organization_id == scope.organization_id,
                Expense.venue_id == scope.venue_id,
            )
            .order_by(Expense.spent_at.desc())
        ).all()
    ]


@router.post("/expenses", status_code=201)
def post_expense(
    payload: ExpenseWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = create_expense(
        db,
        **payload.model_dump(),
        actor_id=user.id,
        idempotency_key=idempotency_key,
        request_id=request_id(request),
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    return {"id": item.id, "status": item.status}


@router.post("/expenses/{expense_id}/void")
def post_void_expense(
    expense_id: str,
    payload: VoidWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, Expense, expense_id, scope)
    void_expense(db, item, reason=payload.reason, actor_id=user.id, request_id=request_id(request))
    return {"id": item.id, "status": item.status}


@router.get("/other-incomes")
def get_other_incomes(
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.report.financial.read"))
    ],
) -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "category": item.category,
            "received_at": item.received_at,
            "amount": item.amount,
            "payer": item.payer,
            "payment_method": item.payment_method,
            "status": item.status,
            "notes": item.notes,
        }
        for item in db.scalars(
            select(OtherIncome)
            .where(
                OtherIncome.organization_id == scope.organization_id,
                OtherIncome.venue_id == scope.venue_id,
            )
            .order_by(OtherIncome.received_at.desc())
        ).all()
    ]


@router.post("/other-incomes", status_code=201)
def post_other_income(
    payload: OtherIncomeWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = create_other_income(
        db,
        **payload.model_dump(),
        actor_id=user.id,
        idempotency_key=idempotency_key,
        request_id=request_id(request),
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    return {"id": item.id, "status": item.status}


@router.post("/other-incomes/{income_id}/void")
def post_void_other_income(
    income_id: str,
    payload: VoidWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    scope: Annotated[
        RequestScope, Depends(require_scope_capability("operations.finance.manage"))
    ],
) -> dict[str, object]:
    item = scoped_object_or_404(db, OtherIncome, income_id, scope)
    void_other_income(
        db,
        item,
        reason=payload.reason,
        actor_id=user.id,
        request_id=request_id(request),
    )
    return {"id": item.id, "status": item.status}
