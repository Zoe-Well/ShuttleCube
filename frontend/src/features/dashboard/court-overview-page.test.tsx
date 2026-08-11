import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { CourtOverviewPage } from "./court-overview-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => vi.clearAllMocks());

describe("court overview page", () => {
  it("shows every active court while the dashboard remains limited", async () => {
    const startsAt = new Date();
    startsAt.setHours(10, 0, 0, 0);
    const endsAt = new Date(startsAt);
    endsAt.setHours(11);
    const courts = Array.from({ length: 6 }, (_, index) => ({
      id: `court-${index + 1}`,
      code: String(index + 1),
      name: `${index + 1} 号场地`,
      is_active: index < 5,
    }));
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/courts") return Promise.resolve(courts);
      if (path.startsWith("/schedule?")) {
        return Promise.resolve([
          {
            id: "booking-5",
            source_id: "booking-5",
            source_type: "venue_booking",
            title: "5 号场订场",
            starts_at: startsAt.toISOString(),
            ends_at: endsAt.toISOString(),
            status: "booked",
            resources: [{ type: "court", id: "court-5" }],
          },
        ]);
      }
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <CourtOverviewPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("court-usage-court-5")).toHaveClass("h-72");
    expect(screen.getByTestId("court-usage-segment-court-5-booking-5")).toHaveClass("bg-amber-100");
    expect(screen.queryByTestId("court-usage-court-6")).not.toBeInTheDocument();
    expect(screen.getByText("全部场地概览")).toBeInTheDocument();
    unmount();
    client.clear();
  });
});
