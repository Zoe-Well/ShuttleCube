import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { OperationsReportPage } from "./operations-report-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

it("renders cash-basis operations metrics", async () => {
  vi.mocked(api).mockResolvedValue({
    from: "2026-08-01",
    to: "2026-08-04",
    income: 1000,
    refunds: 100,
    expense: 200,
    profit: 700,
    outstanding: 300,
    coach_pending: 180,
    coach_earned: 680,
    current_coach_pending: 180,
    coach_settled: 500,
    income_by_source: { venue_booking: 750, enrollment: 250 },
    income_by_class: { "class-1": 300 },
    fixed_class_finance: [
      {
        class_id: "class-1",
        class_name: "周末提高班",
        payment_amount: 300,
        refund_amount: 50,
        net_received: 250,
        outstanding_amount: 100,
      },
    ],
    court_usage_hours: { "court-uuid": 10 },
    court_utilization: { "court-uuid": 0.25 },
    court_names: { "court-uuid": "1 号场地" },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <OperationsReportPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  expect(await screen.findByText("¥700.00")).toBeInTheDocument();
  expect(screen.getByText("1 号场地")).toBeInTheDocument();
  expect(screen.queryByText("court-uuid")).not.toBeInTheDocument();
  expect(screen.getByText("25.0% · 10.0 小时")).toBeInTheDocument();
  expect(screen.getByText("当前待处理")).toBeInTheDocument();
  expect(screen.queryByText("固定班收款与待收款")).not.toBeInTheDocument();
  expect(screen.queryByText("周末提高班")).not.toBeInTheDocument();
});
