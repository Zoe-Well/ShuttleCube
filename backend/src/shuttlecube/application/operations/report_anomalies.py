from decimal import Decimal, InvalidOperation

from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.domain.operations.schemas import OperationsPolicyConfig, ReportAnomaly

ANOMALY_RULE_VERSION = 2


def _values(facts: dict[str, object]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    metrics = facts.get("metrics")
    if not isinstance(metrics, list):
        return result
    for item in metrics:
        if not isinstance(item, dict):
            continue
        try:
            result[str(item["metric_key"])] = Decimal(str(item["value"]))
        except (KeyError, InvalidOperation):
            continue
    return result


def _data_statuses(facts: dict[str, object]) -> dict[str, str]:
    metrics = facts.get("metrics")
    if not isinstance(metrics, list):
        return {}
    return {
        str(item.get("metric_key")): str(item.get("data_status", "complete"))
        for item in metrics
        if isinstance(item, dict)
    }


def _anomaly(
    rule_key: str,
    *,
    severity: str,
    metric_refs: list[str],
    threshold: dict[str, object],
    comparison: dict[str, object],
    evidence: dict[str, object],
    sufficient: bool = True,
) -> ReportAnomaly:
    body = {
        "rule_key": rule_key,
        "metric_refs": metric_refs,
        "threshold": threshold,
        "comparison": comparison,
        "evidence": evidence,
    }
    return ReportAnomaly.model_validate(
        {
            "anomaly_id": f"anomaly:{rule_key}:{canonical_hash(body)[:16]}",
            "rule_key": rule_key,
            "severity": severity,
            "metric_refs": metric_refs,
            "threshold": threshold,
            "comparison": comparison,
            "evidence": evidence,
            "data_sufficiency": "sufficient" if sufficient else "insufficient",
        }
    )


def evaluate_report_anomalies(
    *,
    current: dict[str, object],
    comparison: dict[str, object] | None,
    policy_config: dict[str, object],
) -> list[dict[str, object]]:
    policy = OperationsPolicyConfig.model_validate(policy_config).reports
    values = _values(current)
    statuses = _data_statuses(current)
    previous = _values(comparison or {})
    anomalies: list[ReportAnomaly] = []

    income = values.get("cash_income", Decimal("0"))
    previous_income = previous.get("cash_income")
    if previous_income is not None and previous_income > 0:
        decline = (previous_income - income) / previous_income
        if decline >= policy.income_decline:
            anomalies.append(
                _anomaly(
                    "income_decline",
                    severity="high" if decline >= policy.income_decline * 2 else "medium",
                    metric_refs=["metric:cash_income"],
                    threshold={"decline_ratio": str(policy.income_decline)},
                    comparison={"previous": str(previous_income), "current": str(income)},
                    evidence={"actual_decline_ratio": str(decline.quantize(Decimal('0.0001')))},
                )
            )

    refunds = values.get("cash_refunds", Decimal("0"))
    refund_ratio = refunds / income if income > 0 else None
    if refund_ratio is not None and refund_ratio >= policy.refund_ratio:
        anomalies.append(
            _anomaly(
                "refund_ratio_high",
                severity="high" if refund_ratio >= policy.refund_ratio * 2 else "medium",
                metric_refs=["metric:cash_refunds", "metric:cash_income"],
                threshold={"refund_ratio": str(policy.refund_ratio)},
                comparison={},
                evidence={"actual_ratio": str(refund_ratio.quantize(Decimal('0.0001')))},
            )
        )
    elif income <= 0 and refunds > 0:
        anomalies.append(
            _anomaly(
                "refund_without_period_income",
                severity="medium",
                metric_refs=["metric:cash_refunds", "metric:cash_income"],
                threshold={"refund_ratio": str(policy.refund_ratio)},
                comparison={},
                evidence={"actual_refund": str(refunds), "ratio": "not_calculable"},
            )
        )

    profit = values.get("cash_profit", Decimal("0"))
    if profit < 0:
        anomalies.append(
            _anomaly(
                "cash_profit_negative",
                severity="high",
                metric_refs=["metric:cash_profit"],
                threshold={"minimum": "0"},
                comparison={},
                evidence={"actual": str(profit)},
            )
        )

    expense = values.get("operating_expense", Decimal("0"))
    previous_expense = previous.get("operating_expense")
    if previous_expense is not None and previous_expense > 0:
        growth = (expense - previous_expense) / previous_expense
        if growth >= policy.expense_growth:
            anomalies.append(
                _anomaly(
                    "expense_growth",
                    severity="medium",
                    metric_refs=["metric:operating_expense"],
                    threshold={"growth_ratio": str(policy.expense_growth)},
                    comparison={"previous": str(previous_expense), "current": str(expense)},
                    evidence={"actual_growth_ratio": str(growth.quantize(Decimal('0.0001')))},
                )
            )

    outstanding = values.get("outstanding_as_of", Decimal("0"))
    if outstanding >= policy.outstanding:
        anomalies.append(
            _anomaly(
                "outstanding_high",
                severity="high",
                metric_refs=["metric:outstanding_as_of"],
                threshold={"amount": str(policy.outstanding)},
                comparison={},
                evidence={"actual": str(outstanding)},
            )
        )

    cancellation_rate = values.get("business_cancellation_rate")
    business_total = sum(
        values.get(key, Decimal("0"))
        for key in (
            "class_sessions_completed",
            "class_sessions_cancelled",
            "private_lessons_completed",
            "private_lessons_cancelled",
            "venue_bookings_completed",
            "venue_bookings_cancelled",
            "temporary_events_completed",
            "temporary_events_cancelled",
        )
    )
    if (
        cancellation_rate is not None
        and statuses.get("business_cancellation_rate") != "insufficient"
        and cancellation_rate >= policy.cancellation_rate
    ):
        anomalies.append(
            _anomaly(
                "business_cancellation_rate_high",
                severity="medium",
                metric_refs=["metric:business_cancellation_rate"],
                threshold={"ratio": str(policy.cancellation_rate)},
                comparison={},
                evidence={"actual_ratio": str(cancellation_rate.quantize(Decimal('0.0001')))},
                sufficient=business_total >= policy.min_sample_size,
            )
        )

    overdue_attendance = values.get("attendance_overdue_sessions", Decimal("0"))
    if overdue_attendance > 0:
        anomalies.append(
            _anomaly(
                "attendance_overdue",
                severity="high",
                metric_refs=["metric:attendance_overdue_sessions"],
                threshold={"count": "0"},
                comparison={},
                evidence={"actual": str(overdue_attendance)},
            )
        )

    utilization = values.get("court_raw_utilization", Decimal("0"))
    if (
        statuses.get("court_raw_utilization") not in {"insufficient", "partial"}
        and utilization <= policy.low_utilization
    ):
        anomalies.append(
            _anomaly(
                "court_utilization_low",
                severity="low",
                metric_refs=["metric:court_raw_utilization"],
                threshold={"ratio": str(policy.low_utilization)},
                comparison={},
                evidence={"actual_ratio": str(utilization)},
            )
        )

    coach_pending = values.get("coach_fee_current_pending_as_of", Decimal("0"))
    if coach_pending >= policy.coach_pending:
        anomalies.append(
            _anomaly(
                "coach_fee_pending_high",
                severity="medium",
                metric_refs=["metric:coach_fee_current_pending_as_of"],
                threshold={"amount": str(policy.coach_pending)},
                comparison={},
                evidence={"actual": str(coach_pending)},
            )
        )
    return [item.model_dump(mode="json") for item in anomalies]
