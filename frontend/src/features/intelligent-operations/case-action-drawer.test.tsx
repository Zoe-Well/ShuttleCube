import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import type { OperationCase } from "./api";
import { CaseActionDrawer } from "./case-action-drawer";
import { renderOperations } from "./test-utils";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

const attendanceCase: OperationCase = {
  id: "case-1",
  case_type: "attendance_overdue",
  subject_type: "class_session",
  subject_id: "session-6",
  occurrence_no: 1,
  severity: "medium",
  priority_score: "50",
  title: "测试周五固定班逾期未考勤",
  business_summary: "第 6 节课程结束后仍未完成考勤。",
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
  evidence: {
    facts: {
      fixed_class_name: "测试周五固定班",
      sequence_number: 6,
      scheduled_end: "2026-08-10T11:00:00Z",
      overdue_hours: 28,
    },
    business_links: ["/classes/class-1"],
  },
  evidence_hash: "hash",
  resolved_at: null,
  dismissed_reason: null,
  version: 1,
};

describe("case action drawer", () => {
  beforeEach(() => vi.mocked(api).mockReset());
  afterEach(cleanup);

  it("opens the exact overdue session attendance inside the case", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/operations/cases/case-1/action-context") {
        return Promise.resolve({
          kind: "attendance",
          session: {
            id: "session-6",
            fixed_class_id: "class-1",
            fixed_class_name: "测试周五固定班",
            sequence_number: 6,
            scheduled_start: "2026-08-10T10:00:00Z",
            scheduled_end: "2026-08-10T11:00:00Z",
            status: "scheduled",
            attendance_finalized_at: null,
            version: 1,
          },
          enrollments: [{ id: "enrollment-1", student_id: "student-1", student_name: "王同学" }],
        });
      }
      return Promise.resolve({});
    });

    renderOperations(<CaseActionDrawer item={attendanceCase} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "处理本节课考勤" }));

    expect(await screen.findByText("测试周五固定班 · 第 6 节")).toBeInTheDocument();
    expect(screen.getByText("王同学")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "完成考勤并生成教练费用" })).toBeInTheDocument();
    expect(screen.getByText(/完成标准：保存本节课考勤后/)).toBeInTheDocument();
  });

  it("guides a zero-enrollment course to the not-held action", async () => {
    const zeroEnrollmentCase: OperationCase = {
      ...attendanceCase,
      title: "零学员课程尚未标记为未开课",
      evidence: {
        ...attendanceCase.evidence,
        facts: {
          ...attendanceCase.evidence.facts,
          active_enrollment_count: 0,
          recommended_action: "mark_not_held_no_enrollment",
        },
      },
    };
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/operations/cases/case-1/action-context") {
        return Promise.resolve({
          kind: "attendance",
          session: {
            id: "session-6",
            fixed_class_id: "class-1",
            fixed_class_name: "测试周五固定班",
            sequence_number: 6,
            scheduled_start: "2026-08-10T10:00:00Z",
            scheduled_end: "2026-08-10T11:00:00Z",
            status: "scheduled",
            attendance_finalized_at: null,
            version: 2,
          },
          enrollments: [],
        });
      }
      return Promise.resolve({});
    });

    renderOperations(<CaseActionDrawer item={zeroEnrollmentCase} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "处理零学员课程" }));

    expect(await screen.findByText("本节课没有报名学员")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "标记本节未开课（无学员）" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "完成考勤并生成教练费用" })).toBeNull();
    expect(screen.getAllByText(/释放排期并自动关闭事项/).length).toBeGreaterThan(0);
  });
});
