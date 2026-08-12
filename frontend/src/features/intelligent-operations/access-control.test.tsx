import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
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

    expect(screen.getByRole("link", { name: "待处理事项" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "经营报告" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "运营设置" })).toBeNull();
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

  it("shows the operations settings entry for any settings manager", () => {
    renderOperations(
      <OperationsNavigation
        context={{ ...baseContext, capabilities: ["operations.policy.manage"] }}
      />,
    );

    expect(screen.getByRole("link", { name: "运营设置" })).toHaveAttribute(
      "href",
      "/operations/settings",
    );
  });

  it("shows model-disabled state without offering an unauthorized enable control", () => {
    renderOperations(<OperationsSettingsPanel context={baseContext} />);

    expect(screen.getByText("尚未配置 AI 服务")).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "开启 AI 服务" })).toBeNull();
    expect(screen.queryByText("运营成员与权限")).toBeNull();
  });

  it("does not expose settings for a membership-only capability in the single-role version", () => {
    const { container } = renderOperations(
      <OperationsNavigation
        context={{ ...baseContext, capabilities: ["operations.membership.manage"] }}
      />,
    );

    expect(within(container).queryByRole("link", { name: "运营设置" })).toBeNull();
  });

  it("requires risk confirmation before enabling approved execution", async () => {
    const { container, queryClient } = renderOperations(
      <OperationsSettingsPanel
        context={{ ...baseContext, capabilities: ["operations.policy.manage"] }}
      />,
    );
    act(() => {
      queryClient.setQueryData(["operations-runtime-setting"], {
        operations_enabled: true,
        write_tools_enabled: false,
        updated_at: "2026-08-11T00:00:00Z",
        version: 1,
      });
    });

    const executeButton = within(container).getByRole("button", {
      name: /发现并执行已审批操作/,
    });
    await waitFor(() => expect(executeButton).toBeEnabled());
    fireEvent.click(executeButton);

    expect(within(container).getByRole("dialog", { name: "确认允许执行已审批操作？" })).toBeInTheDocument();
    expect(within(container).getByText("每次高风险操作仍须人工单独审批。")).toBeInTheDocument();
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
