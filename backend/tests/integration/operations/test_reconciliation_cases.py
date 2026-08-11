from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.cases import upsert_detected_case
from shuttlecube.application.operations.detectors import (
    DetectorRegistry,
    detect_reconciliation_failures,
)
from shuttlecube.application.operations.reconciliation import ReconciliationRegistry
from shuttlecube.application.operations.tools import ToolRegistry
from shuttlecube.application.operations.verifiers import verify_reconciliation_failure
from shuttlecube.domain.classes.enrollment_models import LessonUnitLedger
from shuttlecube.domain.finance.models import Payment, Receivable
from shuttlecube.domain.identity.organization_models import Organization
from shuttlecube.domain.operations.policy_models import OperationsPolicy
from shuttlecube.domain.scheduling.court import Venue


def _policy_config() -> dict[str, object]:
    return {
        "receivable_followup": {"aging_days": 7, "escalation_days": 30, "max_attempts": 4},
        "renewal": {
            "fixed_class_days": 30,
            "private_package_expiry_days": 30,
            "private_package_remaining_units": 3,
            "cadence_days": 7,
        },
        "attendance": {"grace_hours": 24},
        "replacement": {"window_days": 14, "slot_minutes": 60, "resource_mode": "original_only"},
        "reports": {
            "min_sample_size": 5,
            "income_decline": "0.20",
            "refund_ratio": "0.10",
            "expense_growth": "0.20",
            "outstanding": "1000.00",
            "cancellation_rate": "0.10",
            "low_utilization": "0.30",
            "coach_pending": "1000.00",
        },
        "runtime": {"case_sla_days": 3, "approval_expiry_minutes": 60, "retry_limit": 2},
    }


def test_reconciliation_is_read_only_and_closes_only_after_real_fact_repair(db: Session) -> None:
    now = datetime.now(UTC)
    organization = Organization(name="Reconciliation Org")
    venue = Venue(organization_id=organization.id, name="Reconciliation Venue")
    policy = OperationsPolicy(
        organization_id=organization.id,
        venue_id=venue.id,
        policy_key="default_operations",
        policy_version=1,
        schema_version=1,
        config=_policy_config(),
        config_hash="reconciliation-policy-hash",
        state="active",
        effective_from=now - timedelta(days=1),
        created_by="owner",
    )
    first = LessonUnitLedger(
        organization_id=organization.id,
        venue_id=venue.id,
        owner_type="enrollment",
        owner_id="enrollment-1",
        change_type="purchase",
        delta=5,
        balance_before=0,
        balance_after=5,
        source_type="enrollment",
        source_id="enrollment-1",
        status="effective",
        operated_by="owner",
        operated_at=now - timedelta(minutes=2),
        idempotency_key="ledger-first",
    )
    broken = LessonUnitLedger(
        organization_id=organization.id,
        venue_id=venue.id,
        owner_type="enrollment",
        owner_id="enrollment-1",
        change_type="attendance",
        delta=-1,
        balance_before=4,
        balance_after=3,
        source_type="class_session",
        source_id="session-1",
        status="effective",
        operated_by="owner",
        operated_at=now - timedelta(minutes=1),
        idempotency_key="ledger-second",
    )
    receivable = Receivable(
        organization_id=organization.id,
        venue_id=venue.id,
        source_type="enrollment",
        source_id="enrollment-1",
        suggested_amount=Decimal("100.00"),
        actual_amount=Decimal("100.00"),
        status="open",
    )
    payment = Payment(
        organization_id=organization.id,
        venue_id=venue.id,
        receivable_id=receivable.id,
        paid_at=now,
        amount=Decimal("120.00"),
        method="cash",
        operated_by="owner",
        status="effective",
        idempotency_key="payment-over-bound",
    )
    db.add_all([organization, venue, policy, first, broken, receivable, payment])
    db.commit()
    scope = RequestScope(
        organization_id=organization.id,
        venue_id=venue.id,
        user_id="owner",
        membership_id="membership",
        capabilities=frozenset({"operations.case.read", "operations.case.manage"}),
    )

    results = ReconciliationRegistry.default().run(db, scope)
    assert {item.rule_key for item in results} >= {"ledger.chain", "receivable.summary"}
    assert "ledger_adjust" not in ToolRegistry.default().keys()
    assert "receivable_sync" not in ToolRegistry.default().keys()

    evidence_items = detect_reconciliation_failures(db, scope, policy, now)
    ledger_evidence = next(
        item
        for item in evidence_items
        if item.facts["reconciliation"]["rule_key"] == "ledger.chain"
    )
    case, _ = upsert_detected_case(
        db,
        scope=scope,
        definition=DetectorRegistry.default().get("reconciliation.failed"),
        evidence=ledger_evidence,
        case_sla_days=3,
        detected_at=now,
    )
    assert case.state == "open"

    broken.balance_before = 5
    broken.balance_after = 4
    payment.amount = Decimal("100.00")
    receivable.status = "settled"
    db.commit()

    repaired_results = ReconciliationRegistry.default().run(db, scope)
    assert not any(item.rule_key in {"ledger.chain", "receivable.summary"} for item in repaired_results)
    verification = verify_reconciliation_failure(db, scope, case)
    assert verification.outcome == "resolved"
    assert case.state == "resolved"
