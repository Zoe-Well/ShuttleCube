import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { ScheduleRecordActions } from "./schedule-record-actions";

vi.mock("@/api/client", () => ({ api: vi.fn().mockResolvedValue({}) }));
afterEach(() => vi.clearAllMocks());

describe("schedule record actions", () => {
  it("permanently deletes a venue booking through its business endpoint", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onChanged = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <ScheduleRecordActions
          item={{
            id: "schedule-1",
            source_id: "booking-1",
            source_type: "venue_booking",
            title: "林先生 · 散客订场",
            starts_at: "2026-08-01T10:00:00+08:00",
            ends_at: "2026-08-01T10:30:00+08:00",
            status: "booked",
            resources: [{ type: "court", id: "court-1" }],
          }}
          onChanged={onChanged}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.change(screen.getByPlaceholderText("请输入删除原因"), { target: { value: "客户要求删除" } });
    fireEvent.click(screen.getByRole("button", { name: "确认永久删除" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/venue-bookings/booking-1",
      { method: "DELETE", body: JSON.stringify({ reason: "客户要求删除" }) },
    ));
    expect(onChanged).toHaveBeenCalled();
    client.clear();
  });
});
