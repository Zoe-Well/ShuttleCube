import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OperationsContext, OperationsPolicy } from "./api";
import { PolicySettingsPanel } from "./policy-settings-panel";
import { renderOperations } from "./test-utils";

const context: OperationsContext = {
  organization: { id: "organization-1", name: "Organization" },
  venue: { id: "venue-1", name: "Venue" },
  user_id: "user-1",
  membership_id: "membership-1",
  capabilities: ["operations.policy.manage"],
  operations_enabled: true,
  write_tools_enabled: false,
  model_enabled: false,
  policy_status: "active",
};

const policy: OperationsPolicy = {
  id: "policy-1",
  name: "日常运营规则",
  policy_key: "default_operations",
  policy_version: 2,
  schema_version: "1",
  state: "draft",
  config_hash: "hash",
  config: {
    receivable_followup: { aging_days: 7, escalation_days: 30, max_attempts: 5 },
    renewal: { fixed_class_days: 30, private_package_expiry_days: 30, private_package_remaining_units: 2, cadence_days: 7 },
    attendance: { grace_hours: 12 },
    replacement: { window_days: 14, slot_minutes: 30, resource_mode: "original_only" },
    reports: { min_sample_size: 5, income_decline: "0.20", refund_ratio: "0.10", expense_growth: "0.20", outstanding: "5000.00", cancellation_rate: "0.10", low_utilization: "0.30", coach_pending: "5000.00" },
    runtime: { case_sla_days: 3, approval_expiry_minutes: 60, retry_limit: 2 },
  },
  effective_from: "2026-08-11T00:00:00Z",
  effective_to: null,
  created_by: "user-1",
  activated_by: null,
  activated_at: null,
  created_at: "2026-08-11T00:00:00Z",
  updated_at: "2026-08-11T00:00:00Z",
  version: 4,
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("operations policy version management", () => {
  it("views and edits a named draft and sends its optimistic version on activation", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ ...policy, state: "active", version: 5 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([policy]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderOperations(<PolicySettingsPanel context={context} />);

    expect(await screen.findByText("日常运营规则")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看" }));
    expect(screen.getByText("欠费提醒")).toBeInTheDocument();
    expect(screen.getByText("7 天")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(screen.getByLabelText("版本名称")).toHaveValue("日常运营规则");

    fireEvent.click(screen.getByRole("button", { name: "激活" }));
    await waitFor(() => {
      const activation = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(activation).toBeDefined();
      expect(JSON.parse(String(activation?.[1]?.body))).toEqual({ expected_version: 4 });
    });
  });
});
