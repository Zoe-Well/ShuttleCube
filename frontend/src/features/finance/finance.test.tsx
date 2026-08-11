import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { FinancePage } from "./finance-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it("shows receivable cash facts and opens the detail", async () => {
  vi.mocked(api).mockImplementation((path) => {
    if (path === "/receivables")
      return Promise.resolve([
        {
          receivable_id: "r1",
          source_type: "venue_booking",
          source_id: "b1",
          business_name: "场地预订-张先生",
          suggested_amount: 100,
          actual_amount: 100,
          received_amount: 60,
          refunded_amount: 0,
          net_received: 60,
          outstanding_amount: 40,
          refundable_amount: 60,
          payment_status: "partial",
          status: "open",
          version: 1,
        },
      ]);
    if (path === "/receivables/r1")
      return Promise.resolve({
        receivable_id: "r1",
        source_type: "venue_booking",
        source_id: "b1",
        business_name: "场地预订-张先生",
        suggested_amount: 100,
        actual_amount: 100,
        received_amount: 60,
        refunded_amount: 0,
        net_received: 60,
        outstanding_amount: 40,
        refundable_amount: 60,
        payment_status: "partial",
        status: "open",
        version: 1,
        payments: [],
        refunds: [],
      });
    if (String(path).startsWith("/attachments")) return Promise.resolve([]);
    return Promise.resolve([]);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FinancePage />
    </QueryClientProvider>,
  );
  expect(await screen.findAllByText("¥40.00")).toHaveLength(2);
  const row = screen.getByText("场地预订-张先生").closest("tr");
  expect(row).toHaveClass("[&_*]:!text-red-600");
  fireEvent.click(screen.getByRole("button", { name: "收款/详情" }));
  expect(await screen.findByText("业务应收、收款与退款明细")).toBeInTheDocument();
  expect(screen.getAllByText("场地预订-张先生")).toHaveLength(2);
  expect(screen.getByRole("button", { name: "登记收款" })).toBeInTheDocument();
});
