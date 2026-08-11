import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OperationsContext } from "./api";
import {
  DeterministicContent,
  OperationsCapabilityBoundary,
  OperationsNavigation,
} from "./access-control";
import { OperationsSettingsPanel } from "./operations-settings-panel";
import { renderOperations } from "./test-utils";

const baseContext: OperationsContext = {
  organization: { id: "organization-1", name: "Organization" },
  venue: { id: "venue-1", name: "Venue" },
  user_id: "user-1",
  membership_id: "membership-1",
  capabilities: ["operations.case.read", "operations.report.read"],
  operations_enabled: true,
  write_tools_enabled: false,
  model_enabled: false,
  policy_status: "active",
};

describe("intelligent operations access control", () => {
  it("hides operations navigation that the current capability bundle cannot use", () => {
    renderOperations(<OperationsNavigation context={baseContext} />);

    expect(screen.getByRole("link", { name: "运营案件" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "经营报告" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "权限与模型设置" })).toBeNull();
  });

  it("does not render protected content when the capability is absent", () => {
    renderOperations(
      <OperationsCapabilityBoundary
        context={baseContext}
        capability="operations.payroll.read"
      >
        <div>Private payroll</div>
      </OperationsCapabilityBoundary>,
    );

    expect(screen.queryByText("Private payroll")).toBeNull();
  });

  it("shows model-disabled state without offering an unauthorized enable control", () => {
    renderOperations(<OperationsSettingsPanel context={baseContext} />);

    expect(screen.getByText("模型功能未启用")).toBeInTheDocument();
    expect(screen.getByText("确定性扫描、案件和报告仍可使用")).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "启用模型" })).toBeNull();
  });

  it("renders deterministic results first when narrative is unavailable", () => {
    renderOperations(
      <DeterministicContent
        modelEnabled={false}
        narrativeState="unavailable"
        narrative={null}
      >
        <div>确定性指标：到款 5,000.00 元</div>
      </DeterministicContent>,
    );

    expect(screen.getByText("确定性指标：到款 5,000.00 元")).toBeInTheDocument();
    expect(screen.getByText("智能总结暂不可用")).toBeInTheDocument();
  });
});
