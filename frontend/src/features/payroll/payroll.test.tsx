import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { CoachFeesPage } from "./coach-fees-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it("shows pending coach fees from completed business", async () => {
  vi.mocked(api).mockImplementation((path) => {
    if (path.startsWith("/coach-fees?")) return Promise.resolve({ calculated_amount: 180, items: [{ id: "f1", coach_id: "c1", coach_name: "陈教练", source_type: "private_lesson", source_id: "l1", business_name: "私教-胡东东", business_path: "/private-lessons", occurred_at: "2026-08-04T10:00:00Z", base_amount: 180, adjustment_amount: 0, amount: 180, status: "pending", version: 1 }] });
    if (path === "/coach-fees/f1") return Promise.resolve({});
    if (path === "/coaches") return Promise.resolve([{ id: "c1", name: "陈教练" }]);
    if (path.startsWith("/payroll-settlements?")) return Promise.resolve([]);
    return Promise.resolve([]);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<MemoryRouter><QueryClientProvider client={client}><CoachFeesPage /></QueryClientProvider></MemoryRouter>);
  expect(await screen.findByText("陈教练")).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "私教-胡东东" })).toHaveAttribute("href", "/private-lessons");
  expect((await screen.findAllByText("¥180.00")).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "调整" }));
  fireEvent.change(screen.getByLabelText(/调增\/调减金额/), { target: { value: "-20" } });
  fireEvent.change(screen.getByLabelText(/调整原因/), { target: { value: "临时代课调整" } });
  fireEvent.click(screen.getByRole("button", { name: "保存调整" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/coach-fees/f1", expect.objectContaining({ method: "PATCH" })));
});
