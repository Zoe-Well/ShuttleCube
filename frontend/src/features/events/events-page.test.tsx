import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { api } from "@/api/client";
import { EventsPage } from "./events-page";

vi.mock("@/api/client", () => ({ api: vi.fn().mockResolvedValue([]) }));

afterEach(() => vi.clearAllMocks());

describe("temporary events", () => {
  it("filters events by name or type", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/events")
        return Promise.resolve([
          {
            id: "event-1",
            schedule_entry_id: "schedule-1",
            name: "周末交流赛",
            event_type: "competition",
            starts_at: "2026-08-01T02:00:00+00:00",
            ends_at: "2026-08-01T04:00:00+00:00",
            court_ids: ["court-1"],
            status: "confirmed",
          },
          {
            id: "event-2",
            schedule_entry_id: "schedule-2",
            name: "暑期集训营",
            event_type: "camp",
            starts_at: "2026-08-02T02:00:00+00:00",
            ends_at: "2026-08-02T04:00:00+00:00",
            court_ids: ["court-1"],
            status: "confirmed",
          },
        ]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <EventsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("周末交流赛")).toBeInTheDocument();
    expect(screen.getByText("暑期集训营")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("搜索活动"), {
      target: { value: "集训" },
    });
    expect(screen.queryByText("周末交流赛")).not.toBeInTheDocument();
    expect(screen.getByText("暑期集训营")).toBeInTheDocument();

    view.unmount();
    client.clear();
  });

  it("shows the concrete court names in the event list", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/events")
        return Promise.resolve([
          {
            id: "event-1",
            schedule_entry_id: "schedule-1",
            name: "周末交流赛",
            event_type: "competition",
            starts_at: "2026-08-01T02:00:00+00:00",
            ends_at: "2026-08-01T04:00:00+00:00",
            court_ids: ["court-1", "court-2"],
            status: "confirmed",
          },
        ]);
      if (path === "/courts")
        return Promise.resolve([
          { id: "court-1", code: "1", name: "1 号场地" },
          { id: "court-2", code: "2", name: "2 号场地" },
        ]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <EventsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("1 号场地、2 号场地")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "创建活动" })).toHaveAttribute("href", "/schedule");

    view.unmount();
    client.clear();
  });
});
