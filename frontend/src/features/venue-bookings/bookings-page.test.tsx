import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { BookingsPage } from "./bookings-page";

vi.mock("@/api/client", () => ({ api: vi.fn().mockResolvedValue([]) }));

afterEach(() => {
  vi.clearAllMocks();
});

describe("venue bookings", () => {
  it("hosts the court schedule grid and its four creation actions", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/courts")
        return Promise.resolve([{ id: "court-1", code: "C01", name: "1 号场" }]);
      if (path === "/venue-bookings")
        return Promise.resolve([
          {
            id: "booking-1",
            customer_id: "customer-1",
            customer_name: "林先生",
            starts_at: "2026-08-01T02:00:00+00:00",
            ends_at: "2026-08-01T02:30:00+00:00",
            court_ids: ["court-1"],
            actual_receivable: 80,
            payment_status: "unpaid",
            status: "booked",
          },
        ]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <BookingsPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("场地预订")).toBeInTheDocument();
    expect(screen.getByText("场地排期表")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增订场" })).not.toBeInTheDocument();
    expect(await screen.findByText("林先生")).toBeInTheDocument();
    expect(screen.getAllByText("1 号场").length).toBeGreaterThan(1);
    fireEvent.change(screen.getByLabelText("排期日期"), { target: { value: "2099-08-04" } });
    await waitFor(() => expect(screen.getByTestId("court-cell-court-1-23")).toBeInTheDocument());

    fireEvent.mouseDown(screen.getByTestId("court-cell-court-1-23"));
    fireEvent.mouseUp(screen.getByTestId("court-cell-court-1-23"));

    expect(await screen.findByRole("button", { name: /新建排期/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /预约私教/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /新建订场/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /创建活动/ })).toBeInTheDocument();

    view.unmount();
    client.clear();
  });

  it("clears the highlighted court slots when closing creation choices", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/courts")
        return Promise.resolve([{ id: "court-1", code: "C01", name: "1 号场" }]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <BookingsPage />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText("排期日期"), { target: { value: "2099-08-04" } });
    const cell = await screen.findByTestId("court-cell-court-1-23");

    fireEvent.mouseDown(cell);
    fireEvent.mouseUp(cell);
    expect(cell).toHaveClass("bg-emerald-100");

    fireEvent.click(await screen.findByRole("button", { name: "继续选择场地" }));

    expect(cell).not.toHaveClass("bg-emerald-100");
    view.unmount();
    client.clear();
  });

  it("queries booking records with the selected date range", async () => {
    vi.mocked(api).mockResolvedValue([]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <BookingsPage />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByLabelText("预定记录开始日期"), {
      target: { value: "2026-08-01" },
    });
    fireEvent.change(screen.getByLabelText("预定记录结束日期"), {
      target: { value: "2026-08-07" },
    });

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        "/venue-bookings?from_date=2026-08-01&to_date=2026-08-07",
      ),
    );
    view.unmount();
    client.clear();
  });

  it("marks an ended booking as awaiting completion and completes it explicitly", async () => {
    const endedAt = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const startedAt = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/venue-bookings") {
        return Promise.resolve([{
          id: "booking-past",
          schedule_entry_id: "schedule-past",
          customer_id: "customer-past",
          customer_name: "过期订场客户",
          starts_at: startedAt,
          ends_at: endedAt,
          court_ids: ["court-1"],
          actual_receivable: 80,
          payment_status: "paid",
          status: "booked",
        }]);
      }
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <BookingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("待确认完成")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认完成" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认场地预定已完成" }));

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        "/venue-bookings/booking-past/complete",
        { method: "POST" },
      ),
    );
    view.unmount();
    client.clear();
  });
});
