import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { TodayAttendancePage } from "./today-attendance-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it("lists today's sessions and links directly to attendance", async () => {
  vi.mocked(api).mockResolvedValue([
    {
      session_id: "session-1",
      class_id: "class-1",
      class_name: "周二基础班",
      sequence_number: 3,
      scheduled_start: "2026-08-04T10:00:00Z",
      scheduled_end: "2026-08-04T11:00:00Z",
      coach_name: "陈教练",
      active_enrollment_count: 6,
    },
  ]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TodayAttendancePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByText("周二基础班")).toBeInTheDocument();
  expect(screen.getByText("第 3 节")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "去考勤" })).toHaveAttribute(
    "href",
    "/classes/class-1?attendance_session=session-1",
  );
});
