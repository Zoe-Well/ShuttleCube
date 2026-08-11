import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { ExpensesPage } from "./expenses-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it("shows miscellaneous income and expense in one cash-flow list", async () => {
  vi.mocked(api).mockImplementation((path) => {
    if (path === "/other-incomes") return Promise.resolve([{ id: "income-1", category: "drinks", received_at: "2026-08-04T10:00:00Z", amount: 25, payer: "散客", payment_method: "微信", status: "effective" }]);
    if (path === "/expenses") return Promise.resolve([{ id: "expense-1", category: "equipment", spent_at: "2026-08-03T10:00:00Z", amount: 100, payee: "器材商", payment_method: "银行卡", status: "effective" }]);
    return Promise.resolve([]);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ExpensesPage /></QueryClientProvider>);

  expect(await screen.findByText("饮料和水")).toBeInTheDocument();
  expect(screen.getByText("器材采购")).toBeInTheDocument();
  expect(screen.getByText("+¥25.00")).toBeInTheDocument();
  expect(screen.getByText("−¥100.00")).toBeInTheDocument();
});
