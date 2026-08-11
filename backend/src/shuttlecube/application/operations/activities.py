from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.operations.access import AccessDenied, require_capability
from shuttlecube.application.operations.evidence import (
    receivable_followup_context,
    renewal_followup_context,
)
from shuttlecube.application.operations.state_machine import transition_case
from shuttlecube.domain.operations.models import CaseActivity, OperationCase


class FollowupActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_type: Literal[
        "contact_attempt", "contact_result", "promise", "note", "status_decision"
    ]
    channel: Literal["phone", "wechat", "in_person", "other", "none"]
    contact_subject_type: Literal["student", "guardian"] | None = None
    contact_subject_id: str | None = Field(default=None, max_length=36)
    outcome_code: Literal[
        "reached",
        "no_answer",
        "promised_payment",
        "paid_elsewhere",
        "renewed",
        "no_intent",
        "follow_later",
        "disputed",
        "invalid_contact",
        "other",
    ]
    summary: str = Field(min_length=1, max_length=2000)
    happened_at: datetime
    next_check_at: datetime | None = None
    expected_case_version: int = Field(ge=1)
    expected_occurrence_no: int = Field(ge=1)
    confirmed_by_user: Literal[True]

    @model_validator(mode="after")
    def validate_combination(self) -> FollowupActivityInput:
        if (self.contact_subject_type is None) != (self.contact_subject_id is None):
            raise ValueError("contact subject type and id must be provided together")
        if self.channel == "none" and self.activity_type not in {"note", "status_decision"}:
            raise ValueError("contact activities require a channel")
        if self.outcome_code in {"follow_later", "promised_payment"} and self.next_check_at is None:
            raise ValueError("this outcome requires next_check_at")
        happened = self.happened_at if self.happened_at.tzinfo else self.happened_at.replace(tzinfo=UTC)
        if self.next_check_at is not None:
            next_check = (
                self.next_check_at
                if self.next_check_at.tzinfo
                else self.next_check_at.replace(tzinfo=UTC)
            )
            if next_check <= happened:
                raise ValueError("next_check_at must be after happened_at")
        return self


def _authorized_contact(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
) -> dict[str, object]:
    if case.case_type == "receivable_followup":
        context = receivable_followup_context(db, scope=scope, case=case)
    elif case.case_type in {"fixed_class_renewal", "private_package_renewal"}:
        context = renewal_followup_context(db, scope=scope, case=case)
    else:
        raise BusinessError(422, "activity_not_supported", "该案件不支持续费或欠费跟进")
    contact = context.get("contact")
    return contact if isinstance(contact, dict) else {"available": False}


def record_followup_activity(
    db: Session,
    *,
    scope: RequestScope,
    case: OperationCase,
    payload: FollowupActivityInput,
    request_id: str,
    source: Literal["human", "tool"] = "human",
    run_id: str | None = None,
) -> CaseActivity:
    try:
        require_capability(scope, "operations.receivable.followup.write")
    except AccessDenied as exc:
        raise BusinessError(403, "capability_denied", "没有记录运营跟进的权限") from exc
    if case.organization_id != scope.organization_id or case.venue_id != scope.venue_id:
        raise BusinessError(404, "scope_not_found", "运营案件不存在")
    if case.version != payload.expected_case_version:
        raise BusinessError(409, "concurrent_change", "案件已被其他人员更新")
    if case.occurrence_no != payload.expected_occurrence_no:
        raise BusinessError(409, "case_occurrence_stale", "案件已进入新的发生轮次")
    if case.state in {"resolved", "dismissed"}:
        raise BusinessError(409, "case_closed", "已关闭案件不能追加跟进")

    contact = _authorized_contact(db, scope=scope, case=case)
    if payload.contact_subject_id is not None and (
        contact.get("available") is not True
        or contact.get("subject_type") != payload.contact_subject_type
        or contact.get("subject_id") != payload.contact_subject_id
    ):
        raise BusinessError(422, "invalid_contact_subject", "联系人不属于当前案件")
    if payload.channel != "none" and contact.get("available") is not True:
        raise BusinessError(422, "contact_unavailable", "当前案件没有可用联系人")

    item = CaseActivity(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        case_id=case.id,
        case_occurrence_no=case.occurrence_no,
        activity_type=payload.activity_type,
        channel=payload.channel,
        contact_subject_type=payload.contact_subject_type,
        contact_subject_id=payload.contact_subject_id,
        outcome_code=payload.outcome_code,
        summary=payload.summary.strip(),
        happened_at=payload.happened_at,
        next_check_at=payload.next_check_at,
        operated_by=scope.user_id,
        source=source,
        run_id=run_id,
    )
    db.add(item)
    if payload.next_check_at is not None:
        case.next_check_at = payload.next_check_at
    if case.state != "monitoring":
        transition_case(case, "monitoring")
    db.flush()
    record_audit(
        db,
        actor_id=scope.user_id,
        action="operation_case.followup_recorded",
        entity_type="case_activity",
        entity_id=item.id,
        request_id=request_id,
        before=None,
        after={
            "case_id": case.id,
            "occurrence_no": case.occurrence_no,
            "outcome_code": item.outcome_code,
            "next_check_at": item.next_check_at.isoformat() if item.next_check_at else None,
        },
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
    )
    db.flush()
    return item


def activity_payload(item: CaseActivity) -> dict[str, object]:
    return {
        "id": item.id,
        "case_id": item.case_id,
        "case_occurrence_no": item.case_occurrence_no,
        "activity_type": item.activity_type,
        "channel": item.channel,
        "contact_subject_type": item.contact_subject_type,
        "contact_subject_id": item.contact_subject_id,
        "outcome_code": item.outcome_code,
        "summary": item.summary,
        "happened_at": item.happened_at,
        "next_check_at": item.next_check_at,
        "operated_by": item.operated_by,
        "source": item.source,
        "created_at": item.created_at,
    }
