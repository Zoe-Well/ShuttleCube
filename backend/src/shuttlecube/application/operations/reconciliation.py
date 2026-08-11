from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope


class InvariantCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=120)
    expected: str = Field(max_length=1000)
    actual: str = Field(max_length=1000)
    passed: bool


class AffectedReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=80)
    version: int | None = Field(default=None, ge=1)


class RepairEntryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    route: str = Field(pattern=r"^/")


class ReconciliationImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affected_amount: str = "0.00"
    affected_lesson_units: int = 0
    affected_schedules: int = 0
    downstream_records: int = 0


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    rule_key: str
    rule_version: int = Field(ge=1)
    compatible_from_version: int = Field(ge=1)
    result: Literal["passed", "failed", "indeterminate"]
    severity: Literal["low", "medium", "high", "critical"]
    subject_type: str
    subject_id: str
    affected_refs: list[AffectedReference] = Field(default_factory=list)
    invariants: list[InvariantCheck] = Field(default_factory=list)
    impact: ReconciliationImpact = Field(default_factory=ReconciliationImpact)
    repair_entry_points: list[RepairEntryPoint] = Field(default_factory=list)
    automatic_repair_available: Literal[False] = False


RuleImplementation = Callable[[Session, RequestScope], list[ReconciliationResult]]


@dataclass(frozen=True)
class ReconciliationRule:
    rule_key: str
    version: int
    compatible_from_version: int
    implementation: RuleImplementation


def issue_id(scope: RequestScope, rule_key: str, subject_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{scope.organization_id}:{scope.venue_id}:{rule_key}:{subject_id}"))


def failed_result(
    *,
    scope: RequestScope,
    rule_key: str,
    rule_version: int,
    subject_type: str,
    subject_id: str,
    severity: Literal["low", "medium", "high", "critical"],
    invariants: list[InvariantCheck],
    affected_refs: list[AffectedReference],
    repair_entry_points: list[RepairEntryPoint],
    impact: ReconciliationImpact | None = None,
) -> ReconciliationResult:
    return ReconciliationResult(
        issue_id=issue_id(scope, rule_key, subject_id),
        rule_key=rule_key,
        rule_version=rule_version,
        compatible_from_version=1,
        result="failed",
        severity=severity,
        subject_type=subject_type,
        subject_id=subject_id,
        invariants=invariants,
        affected_refs=affected_refs,
        impact=impact or ReconciliationImpact(),
        repair_entry_points=repair_entry_points,
        automatic_repair_available=False,
    )


class ReconciliationRegistry:
    def __init__(self, rules: Iterable[ReconciliationRule]) -> None:
        items = list(rules)
        self._rules = {item.rule_key: item for item in items}
        if len(items) != len(self._rules):
            raise ValueError("duplicate reconciliation rule key")

    @classmethod
    def default(cls) -> ReconciliationRegistry:
        from shuttlecube.application.operations.reconciliation_finance import FINANCE_RULES
        from shuttlecube.application.operations.reconciliation_lesson_units import LESSON_RULES
        from shuttlecube.application.operations.reconciliation_payroll import PAYROLL_RULES
        from shuttlecube.application.operations.reconciliation_schedule import SCHEDULE_RULES

        return cls((*LESSON_RULES, *FINANCE_RULES, *PAYROLL_RULES, *SCHEDULE_RULES))

    def get(self, rule_key: str) -> ReconciliationRule:
        try:
            return self._rules[rule_key]
        except KeyError as exc:
            raise KeyError(f"unknown reconciliation rule: {rule_key}") from exc

    def rules(self) -> tuple[ReconciliationRule, ...]:
        return tuple(self._rules.values())

    def run(self, db: Session, scope: RequestScope) -> list[ReconciliationResult]:
        results: list[ReconciliationResult] = []
        for rule in self.rules():
            for result in rule.implementation(db, scope):
                if result.rule_key != rule.rule_key or result.rule_version != rule.version:
                    raise ValueError("reconciliation result does not match its rule definition")
                results.append(result)
        return sorted(
            results,
            key=lambda item: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}[item.severity],
                item.rule_key,
                item.issue_id,
            ),
        )


def reconciliation_payload(result: ReconciliationResult) -> dict[str, object]:
    return result.model_dump(mode="json")
