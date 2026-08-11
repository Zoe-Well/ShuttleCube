import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { SchedulePage } from "./schedule-page";

vi.mock("@fullcalendar/react", () => ({
  default: ({
    eventClick,
    select,
    selectable,
    events,
    slotMinTime,
    slotMaxTime,
    slotDuration,
    snapDuration,
    slotLabelContent,
  }: {
    eventClick: (value: { event: { id: string } }) => void;
    select: (value: { start: Date; end: Date }) => void;
    selectable: boolean;
    events: { id: string; title?: string; classNames?: string[]; display?: string }[];
    slotMinTime: string;
    slotMaxTime: string;
    slotDuration: string;
    snapDuration: string;
    slotLabelContent: (value: { date: Date }) => string;
  }) => (
    <div>
      <button
        data-slot-max={slotMaxTime}
        data-slot-min={slotMinTime}
        data-slot-duration={slotDuration}
        data-snap-duration={snapDuration}
        data-selectable={String(selectable)}
        data-testid="calendar"
        onClick={() =>
          select({ start: new Date("2026-08-03T10:00:00"), end: new Date("2026-08-03T11:00:00") })
        }
      >
        {slotLabelContent({ date: new Date("2026-08-03T10:00:00") })}
      </button>
      {events.map((event) => (
        <button
          data-classes={event.classNames?.join(" ")}
          data-display={event.display}
          data-testid={`calendar-event-${event.id}`}
          key={event.id}
          onClick={() => eventClick({ event: { id: event.id } })}
          type="button"
        >
          {event.title}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("@/api/client", () => ({ api: vi.fn().mockResolvedValue([]) }));

afterEach(() => {
  vi.clearAllMocks();
});

describe("schedule", () => {
  it("shows unified schedule", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/courts") return Promise.resolve([{ id: "court-1", name: "1 号场" }]);
      if (path.startsWith("/schedule?"))
        return Promise.resolve([
          {
            id: "schedule-1",
            source_id: "class-session-1",
            source_type: "class_session",
            title: "周六固定班",
            starts_at: "2026-08-03T10:00:00+08:00",
            ends_at: "2026-08-03T11:00:00+08:00",
            status: "confirmed",
            resources: [{ type: "court", id: "court-1" }],
          },
        ]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <SchedulePage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("统一排期")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建排期" })).not.toBeInTheDocument();
    expect(await screen.findByTestId("calendar")).toBeInTheDocument();
    expect(screen.getByTestId("calendar")).toHaveAttribute("data-slot-min", "08:00:00");
    expect(screen.getByTestId("calendar")).toHaveAttribute("data-slot-max", "24:00:00");
    expect(screen.getByTestId("calendar")).toHaveAttribute("data-slot-duration", "01:00:00");
    expect(screen.getByTestId("calendar")).toHaveAttribute("data-snap-duration", "01:00:00");
    expect(screen.getByTestId("calendar")).toHaveTextContent("10:00-11:00");
    expect(await screen.findByText("周六固定班 · 1 号场")).toBeInTheDocument();
    expect(screen.getByTestId("calendar-event-schedule-1").getAttribute("data-classes")).toContain(
      "event-past",
    );
    expect(screen.getByTestId("calendar-event-past-2026-08-03T08:00")).toHaveAttribute(
      "data-display",
      "background",
    );
    await waitFor(() => expect(api).toHaveBeenCalledTimes(3));
    expect(screen.queryByText("场地排期表")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("calendar"));
    expect(
      await screen.findByRole("dialog", { name: "这是已经失效的场地时段" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续补录" }));
    const dialog = await screen.findByRole("dialog", { name: "用所选场地时段创建" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "1 号场" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /新建排期/ })).toBeDisabled();

    fireEvent.click(within(dialog).getByRole("button", { name: "1 号场" }));
    expect(within(dialog).getByRole("button", { name: /新建排期/ })).toBeEnabled();

    view.unmount();
    client.clear();
  });

  it("selects deletable schedule items and permanently deletes them in bulk", async () => {
    const schedule = [
      {
        id: "manual-1",
        source_id: "manual-source-1",
        source_type: "manual",
        title: "临时手工排期",
        starts_at: "2026-08-03T10:00:00+08:00",
        ends_at: "2026-08-03T10:30:00+08:00",
        status: "confirmed",
        resources: [{ type: "court", id: "court-1" }],
      },
      {
        id: "class-1",
        source_id: "class-session-1",
        source_type: "class_session",
        title: "周六固定班",
        starts_at: "2026-08-03T11:00:00+08:00",
        ends_at: "2026-08-03T12:00:00+08:00",
        status: "scheduled",
        resources: [{ type: "court", id: "court-1" }],
      },
    ];
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/courts") return Promise.resolve([{ id: "court-1", name: "1 号场" }]);
      if (path.startsWith("/schedule?")) return Promise.resolve(schedule);
      if (path === "/schedule/bulk-delete") return Promise.resolve({ status: "deleted" });
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <SchedulePage />
      </QueryClientProvider>,
    );
    await screen.findByTestId("calendar-event-manual-1");

    fireEvent.click(screen.getByRole("button", { name: "批量管理" }));
    expect(screen.getByTestId("calendar")).toHaveAttribute("data-selectable", "false");
    fireEvent.click(screen.getByTestId("calendar-event-class-1"));
    expect(screen.getByRole("status")).toHaveTextContent("固定班课次请在固定班业务中管理");

    fireEvent.click(screen.getByTestId("calendar-event-manual-1"));
    expect(screen.getByText("已选 1 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批量删除" }));
    fireEvent.change(screen.getByPlaceholderText("请输入统一删除原因"), {
      target: { value: "批量清理测试排期" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认永久删除" }));

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith("/schedule/bulk-delete", {
        method: "POST",
        body: JSON.stringify({ ids: ["manual-1"], reason: "批量清理测试排期" }),
      }),
    );

    view.unmount();
    client.clear();
  });
});
