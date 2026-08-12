import { describe, expect, it } from "vitest";

import {
  approvalStateLabel,
  caseStateLabel,
  caseTypeLabel,
  eventTypeLabel,
  outcomeLabel,
  runStateLabel,
  severityLabel,
  workflowLabel,
} from "./terminology";

describe("intelligent operations terminology", () => {
  it("translates internal states into user-facing Chinese", () => {
    expect(severityLabel("critical")).toBe("紧急");
    expect(caseStateLabel("waiting_human")).toBe("等待人工处理");
    expect(runStateLabel("succeeded")).toBe("已完成");
    expect(approvalStateLabel("stale")).toBe("方案已失效");
    expect(outcomeLabel("promised_payment")).toBe("承诺付款");
  });

  it("translates case, workflow and timeline identifiers", () => {
    expect(caseTypeLabel("class_replacement_pending")).toBe("取消课程待补排");
    expect(workflowLabel("operations.report.v1")).toBe("经营报告生成");
    expect(eventTypeLabel("case_verified")).toBe("已核对处理结果");
  });

  it("does not expose unknown internal identifiers", () => {
    expect(runStateLabel("provider_internal_state")).toBe("状态未知");
    expect(caseTypeLabel("new_internal_case")).toBe("其他待处理事项");
  });
});
