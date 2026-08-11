from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.operations.idempotency import canonical_hash
from shuttlecube.domain.operations.models import OperationRun, OperationsReportSnapshot


def create_report_snapshot(
    db: Session,
    *,
    scope: RequestScope,
    run: OperationRun,
    period_type: str,
    period_start: date,
    period_end: date,
    effective_end: datetime,
    business_timezone: str,
    period_state: str,
    generated_at: datetime,
    generated_by: str,
    comparison_start: date | None,
    comparison_end: date | None,
    comparison_status: str,
    policy_version: int,
    metric_version: int,
    anomaly_rule_version: int,
    metrics: list[dict[str, object]],
    breakdowns: dict[str, object],
    anomalies: list[dict[str, object]],
    source_refs: list[dict[str, object]],
    caveats: list[dict[str, object]],
    include_narrative: bool,
) -> OperationsReportSnapshot:
    existing = db.scalar(
        select(OperationsReportSnapshot).where(
            OperationsReportSnapshot.organization_id == scope.organization_id,
            OperationsReportSnapshot.venue_id == scope.venue_id,
            OperationsReportSnapshot.run_id == run.id,
        )
    )
    if existing is not None:
        return existing
    deterministic_payload = {
        "period_type": period_type,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "effective_end": effective_end.isoformat(),
        "business_timezone": business_timezone,
        "comparison_start": comparison_start.isoformat() if comparison_start else None,
        "comparison_end": comparison_end.isoformat() if comparison_end else None,
        "comparison_status": comparison_status,
        "policy_version": policy_version,
        "metric_version": metric_version,
        "anomaly_rule_version": anomaly_rule_version,
        "metrics": metrics,
        "breakdowns": breakdowns,
        "anomalies": anomalies,
        "source_refs": source_refs,
        "caveats": caveats,
    }
    snapshot = OperationsReportSnapshot(
        organization_id=scope.organization_id,
        venue_id=scope.venue_id,
        run_id=run.id,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        effective_end=effective_end,
        business_timezone=business_timezone,
        period_state=period_state,
        generated_at=generated_at,
        generated_by=generated_by,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        comparison_status=comparison_status,
        policy_key=run.policy_key,
        policy_version=policy_version,
        metric_version=metric_version,
        anomaly_rule_version=anomaly_rule_version,
        metrics=metrics,
        breakdowns=breakdowns,
        anomalies=anomalies,
        source_refs=source_refs,
        evidence_hash=canonical_hash(deterministic_payload),
        narrative_state="queued" if include_narrative else "not_requested",
        caveats=caveats,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def get_report_snapshot(
    db: Session,
    *,
    scope: RequestScope,
    snapshot_id: str,
) -> OperationsReportSnapshot:
    snapshot = db.scalar(
        select(OperationsReportSnapshot).where(
            OperationsReportSnapshot.id == snapshot_id,
            OperationsReportSnapshot.organization_id == scope.organization_id,
            OperationsReportSnapshot.venue_id == scope.venue_id,
        )
    )
    if snapshot is None:
        raise BusinessError(404, "scope_not_found", "经营报告不存在")
    return snapshot


def report_snapshot_payload(snapshot: OperationsReportSnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "run_id": snapshot.run_id,
        "period_type": snapshot.period_type,
        "period_start": snapshot.period_start,
        "period_end": snapshot.period_end,
        "effective_end": snapshot.effective_end,
        "period_state": snapshot.period_state,
        "generated_at": snapshot.generated_at,
        "generated_by": snapshot.generated_by,
        "business_timezone": snapshot.business_timezone,
        "comparison_start": snapshot.comparison_start,
        "comparison_end": snapshot.comparison_end,
        "comparison_status": snapshot.comparison_status,
        "policy_version": snapshot.policy_version,
        "metric_version": str(snapshot.metric_version),
        "anomaly_rule_version": str(snapshot.anomaly_rule_version),
        "court_capacity_method": "commercial_usage_over_business_hours_minus_court_blocks",
        "metrics": snapshot.metrics,
        "breakdowns": snapshot.breakdowns,
        "anomalies": snapshot.anomalies,
        "source_refs": snapshot.source_refs,
        "evidence_hash": snapshot.evidence_hash,
        "narrative_state": snapshot.narrative_state,
        "narrative": {
            "state": snapshot.narrative_state,
            "summary": snapshot.summary,
            "anomaly_explanations": snapshot.anomaly_explanations or [],
            "recommendations": snapshot.recommendations or [],
            "caveats": snapshot.caveats or [],
            "run_id": snapshot.narrative_run_id,
            "model_profile": snapshot.model_profile,
            "prompt_version": snapshot.prompt_version,
        },
    }

