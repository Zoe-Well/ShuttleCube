from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.infrastructure.database.base import Base

if TYPE_CHECKING:
    from shuttlecube.api.dependencies import RequestScope

ROLE_BUNDLE_VERSION = 1

_COMMON_READ = {
    "operations.case.read",
    "operations.report.read",
}
_ROLE_BUNDLES: dict[str, frozenset[str]] = {
    "owner": frozenset(
        _COMMON_READ
        | {
            "operations.case.manage",
            "operations.case.assign",
            "operations.receivable.followup.read",
            "operations.receivable.followup.write",
            "operations.report.financial.read",
            "operations.payroll.read",
            "operations.finance.manage",
            "operations.payroll.manage",
            "operations.membership.manage",
            "operations.policy.manage",
            "operations.model.manage",
            "operations.trace.read",
            "operations.approval.decide",
            "operations.schedule.execute",
        }
    ),
    "operations_manager": frozenset(
        _COMMON_READ
        | {
            "operations.case.manage",
            "operations.case.assign",
            "operations.receivable.followup.read",
            "operations.receivable.followup.write",
            "operations.approval.decide",
            "operations.schedule.execute",
        }
    ),
    "operator": frozenset(
        _COMMON_READ
        | {
            "operations.case.manage",
            "operations.receivable.followup.read",
            "operations.receivable.followup.write",
        }
    ),
    "finance_viewer": frozenset(
        _COMMON_READ
        | {
            "operations.report.financial.read",
            "operations.payroll.read",
        }
    ),
}


class AccessDenied(PermissionError):
    pass


def capabilities_for_role(role_key: str) -> frozenset[str]:
    try:
        return _ROLE_BUNDLES[role_key]
    except KeyError as exc:
        raise AccessDenied(f"Unknown role bundle: {role_key}") from exc


def require_capability(scope: RequestScope, capability: str) -> None:
    if capability not in scope.capabilities:
        raise AccessDenied(f"Missing capability: {capability}")


def require_scope_capability(capability: str) -> Callable[..., Any]:
    from shuttlecube.api.dependencies import request_scope

    def dependency(
        scope: RequestScope = Depends(request_scope),  # noqa: B008
    ) -> RequestScope:
        try:
            require_capability(scope, capability)
        except AccessDenied as exc:
            raise BusinessError(403, "capability_denied", "当前账号没有执行此操作的权限") from exc
        return scope

    return dependency


def scoped_object_or_404[ModelT: Base](
    db: Session,
    model: type[ModelT],
    object_id: str,
    scope: RequestScope,
) -> ModelT:
    predicates = [model.id == object_id]  # type: ignore[attr-defined]
    if hasattr(model, "organization_id"):
        predicates.append(model.organization_id == scope.organization_id)  # type: ignore[attr-defined]
    if hasattr(model, "venue_id"):
        predicates.append(model.venue_id == scope.venue_id)  # type: ignore[attr-defined]
    item = db.scalar(select(model).where(*predicates))
    if item is None:
        raise BusinessError(404, "scope_not_found", "记录不存在")
    return item


def project_receivable_case(
    payload: dict[str, object],
    *,
    scope: RequestScope,
    authorized_receivable_id: str,
) -> dict[str, object]:
    require_capability(scope, "operations.receivable.followup.read")
    if payload.get("id") != authorized_receivable_id:
        raise AccessDenied("Receivable is not the subject of the authorized case")
    allowed = {
        "id",
        "source_type",
        "source_id",
        "outstanding_amount",
        "student_name",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def project_followup_context(
    payload: dict[str, object],
    *,
    scope: RequestScope,
    case_type: str,
) -> dict[str, object]:
    """Apply the same case-level audience boundary to REST, Tool and model input."""
    if case_type == "receivable_followup":
        require_capability(scope, "operations.receivable.followup.read")
    else:
        require_capability(scope, "operations.case.read")
    forbidden = {
        "venue_total_outstanding",
        "venue_income",
        "venue_expense",
        "venue_profit",
        "payroll_total",
        "coach_salary",
        "phone",
        "wechat",
    }

    def project(value: object) -> object:
        if isinstance(value, dict):
            return {
                str(key): project(item)
                for key, item in value.items()
                if str(key).lower() not in forbidden
            }
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    result = project(deepcopy(payload))
    assert isinstance(result, dict)
    return result


def project_report_payload(
    payload: dict[str, object],
    *,
    scope: RequestScope,
) -> dict[str, object]:
    require_capability(scope, "operations.report.read")
    result = deepcopy(payload)
    can_finance = "operations.report.financial.read" in scope.capabilities
    can_payroll = "operations.payroll.read" in scope.capabilities

    def metric_allowed(metric: dict[str, object]) -> bool:
        key = str(metric.get("metric_key", ""))
        if key.startswith(
            ("cash_", "income", "refund", "expense", "operating_expense", "profit", "outstanding")
        ):
            return can_finance
        if key.startswith(("coach_fee", "payroll")):
            return can_payroll
        return True

    metrics = result.get("metrics")
    if isinstance(metrics, list):
        result["metrics"] = [item for item in metrics if isinstance(item, dict) and metric_allowed(item)]
    breakdowns = result.get("breakdowns")
    if isinstance(breakdowns, dict):
        result["breakdowns"] = {
            key: (
                [item for item in value if isinstance(item, dict) and metric_allowed(item)]
                if key == "comparison_metrics" and isinstance(value, list)
                else value
            )
            for key, value in breakdowns.items()
            if (
                key not in {"finance", "income_by_source", "fixed_class_finance"}
                or can_finance
            )
            and (key != "payroll" or can_payroll)
        }
    visible_metric_refs = {
        str(item.get("metric_ref"))
        for item in result.get("metrics", [])
        if isinstance(item, dict)
    }
    anomalies = result.get("anomalies")
    if isinstance(anomalies, list):
        result["anomalies"] = [
            item
            for item in anomalies
            if isinstance(item, dict)
            and all(ref in visible_metric_refs for ref in item.get("metric_refs", []))
        ]
    source_refs = result.get("source_refs")
    if isinstance(source_refs, list):
        financial_kinds = {"payment", "refund", "expense", "receivable"}
        payroll_kinds = {"coach_fee", "payroll_settlement"}
        result["source_refs"] = [
            ref
            for ref in source_refs
            if isinstance(ref, dict)
            and (ref.get("kind") not in financial_kinds or can_finance)
            and (ref.get("kind") not in payroll_kinds or can_payroll)
        ]
    if not (can_finance and can_payroll):
        narrative = result.get("narrative")
        if isinstance(narrative, dict):
            result["narrative"] = {
                **narrative,
                "summary": None,
                "anomaly_explanations": [],
                "recommendations": [],
                "state": "unavailable" if narrative.get("state") == "available" else narrative.get("state"),
                "projection_reason": "narrative_hidden_by_report_audience",
            }
    return result
