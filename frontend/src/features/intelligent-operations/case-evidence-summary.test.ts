import { describe, expect, it } from "vitest";

import type { OperationCase } from "./api";
import { buildCaseEvidenceItems } from "./case-evidence";

function operationCase(caseType: string, facts: Record<string, unknown>): OperationCase {
  return {
    id: "case-1",
    case_type: caseType,
    subject_type: "class_session",
    subject_id: "internal-subject-id",
    occurrence_no: 1,
    severity: "medium",
    priority_score: "50",
    title: "待处理事项",
    business_summary: null,
    state: "open",
    first_detected_at: "2026-08-11T00:00:00Z",
    last_detected_at: "2026-08-11T00:00:00Z",
    next_check_at: null,
    due_at: null,
    queue_key: "training",
    required_capability: "operations.case.read",
    assigned_to: null,
    assigned_at: null,
    current_run_id: null,
    evidence: { facts },
    evidence_hash: "hash",
    resolved_at: null,
    dismissed_reason: null,
    version: 1,
  };
}

describe("case evidence summary", () => {
  it("shows business facts without internal record ids", () => {
    const items = buildCaseEvidenceItems(operationCase("attendance_overdue", {
      class_session_id: "596467ac-2978-4f1d-9ec1-a8c9bb076160",
      fixed_class_id: "a7d1aab3-b10e-43d4-8cbf-f5014be0e086",
      fixed_class_name: "周六提高班",
      sequence_number: 6,
      overdue_hours: 28,
      attendance_finalized: false,
    }));

    expect(items).toEqual(expect.arrayContaining([
      { label: "固定班", value: "周六提高班" },
      { label: "课程序号", value: "6" },
      { label: "考勤已完成", value: "否" },
    ]));
    expect(JSON.stringify(items)).not.toContain("596467ac");
    expect(JSON.stringify(items)).not.toContain("a7d1aab3");
    expect(items.some((item) => item.label.includes("记录"))).toBe(false);
  });

  it("turns coach and court ids into counts", () => {
    const items = buildCaseEvidenceItems(operationCase("class_replacement_pending", {
      coach_ids: ["coach-secret"],
      court_ids: ["court-secret-1", "court-secret-2"],
    }));

    expect(items).toEqual([
      { label: "教练数量", value: "1" },
      { label: "场地数量", value: "2" },
    ]);
  });
});
