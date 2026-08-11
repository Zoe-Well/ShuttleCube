import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { ScheduleDetails } from "./schedule-details";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => vi.clearAllMocks());

describe("shared schedule details", () => {
  it("resolves legacy court codes to the current court name", async () => {
    vi.mocked(api).mockResolvedValue([
      { id: "court-uuid-1", code: "1", name: "1 号场地" },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <ScheduleDetails item={{
          id: "schedule-1",
          source_id: "session-1",
          source_type: "class_session",
          title: "周六固定班",
          starts_at: "2026-08-01T10:00:00+08:00",
          ends_at: "2026-08-01T11:00:00+08:00",
          status: "confirmed",
          resources: [{ type: "court", id: "1" }],
        }} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("1 号场地")).toBeInTheDocument();

    view.unmount();
    client.clear();
  });
});
