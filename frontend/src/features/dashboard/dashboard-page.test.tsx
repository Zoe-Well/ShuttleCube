import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { localDateKey } from "@/lib/utils";
import { DashboardPage } from "./dashboard-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => vi.clearAllMocks());

describe("dashboard timeline", () => {
  it("renders every item inside its own scroll area", async () => {
    const schedule = Array.from({ length: 9 }, (_, index) => {
      const startsAt = new Date();
      startsAt.setHours(8 + index, 0, 0, 0);
      const endsAt = new Date(startsAt);
      endsAt.setMinutes(30);
      return {
        id: `schedule-${index}`,
        source_id: `booking-${index}`,
        source_type: "venue_booking",
        title: `散客 ${index + 1} · 散客订场`,
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
        status: "booked",
        resources: [{ type: "court", id: "court-1" }],
      };
    });
    vi.mocked(api).mockImplementation((path) => {
      if (path.startsWith("/schedule?")) return Promise.resolve(schedule);
      if (path.startsWith("/dashboard?"))
        return Promise.resolve({
          today_counts: { venue_booking: 9 },
          pending_counts: { attendance: 1, receivables: 2, ending_classes: 1, coach_fees: 1 },
          ending_within_days: 30,
          month_finance: { income: 900, refunds: 50, expense: 100, profit: 750, outstanding: 200 },
        });
      if (path === "/classes") return Promise.resolve([]);
      if (path === "/students") return Promise.resolve({ items: [] });
      if (path === "/venue-bookings") return Promise.resolve([]);
      if (path === "/courts")
        return Promise.resolve([
          { id: "court-1", code: "1", name: "1 号场地" },
          { id: "court-2", code: "2", name: "2 号场地" },
          { id: "court-3", code: "3", name: "3 号场地" },
          { id: "court-4", code: "4", name: "4 号场地" },
          { id: "court-5", code: "5", name: "5 号场地" },
        ]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <DashboardPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("散客 9 · 散客订场")).toBeInTheDocument();
    expect(screen.getAllByText(/1 号场地/)).toHaveLength(10);
    expect(screen.getByTestId("today-timeline-scroll")).toHaveClass("overflow-y-auto");
    expect(screen.getByTestId("court-usage-court-1")).toHaveClass("h-56", "bg-white");
    expect(screen.getAllByTestId(/court-usage-segment-court-1-/)).toHaveLength(9);
    expect(screen.getByTestId("court-usage-segment-court-1-schedule-0")).toHaveClass(
      "bg-amber-100",
    );
    expect(screen.getByTestId("court-usage-court-2").children).toHaveLength(0);
    expect(screen.queryByTestId("court-usage-court-5")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看全部" })).toHaveAttribute(
      "href",
      "/courts/overview",
    );
    expect(screen.queryByText("待安排补课")).not.toBeInTheDocument();
    const attendanceCard = screen.getByText("今日待考勤").closest("a");
    expect(attendanceCard).toHaveAttribute("href", "/attendance/today");
    expect(screen.getByText("待结教练")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "7天" }));
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(expect.stringContaining("ending_within_days=7")),
    );
    unmount();
    client.clear();
  });

  it("formats the business date from local calendar fields", () => {
    expect(localDateKey(new Date(2026, 7, 4, 0, 30))).toBe("2026-08-04");
  });
});
