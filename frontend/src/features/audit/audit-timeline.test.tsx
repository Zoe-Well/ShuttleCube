import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { AuditTimeline } from "./audit-timeline";

vi.mock("@/api/client", () => ({ api: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it("shows human-readable audit actions and business names", async () => {
  vi.mocked(api).mockResolvedValue([
    {
      id: "audit-1",
      actor_name: "管理员",
      action_type: "payment.recorded",
      action_label: "登记收款",
      entity_type: "receivable",
      entity_id: "internal-uuid",
      entity_label: "应收业务",
      entity_name: "固定班-胡东东",
      occurred_at: "2026-08-05T00:00:00+08:00",
      request_id: "request-1",
      business_summary: "累计收款：¥0.00 → ¥100.00",
      changes: [{ field: "累计收款", before: "¥0.00", after: "¥100.00" }],
      is_noop: false,
    },
  ]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuditTimeline />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("登记收款")).toBeInTheDocument();
  expect(screen.getByText("应收业务 · 固定班-胡东东")).toBeInTheDocument();
  expect(screen.queryByText("payment.recorded")).not.toBeInTheDocument();
  expect(screen.queryByText("internal-uuid")).not.toBeInTheDocument();
});
