import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourtScheduleGrid } from "./court-schedule-grid";
import { ScheduleSelectionActions } from "./schedule-selection-actions";

afterEach(cleanup);

const courts = [
  { id: "court-1", code: "C01", name: "1 号场" },
  { id: "court-2", code: "C02", name: "2 号场" },
  { id: "court-3", code: "C03", name: "3 号场" },
];
const beforeSchedule = new Date("2026-08-01T07:00:00+08:00");

describe("court schedule selection", () => {
  it("only exposes hourly slots from 08:00 through 24:00", () => {
    const onChange = vi.fn();
    render(
      <CourtScheduleGrid
        courts={courts}
        date="2026-08-01"
        items={[]}
        now={beforeSchedule}
        onSelectionChange={onChange}
      />,
    );

    expect(screen.queryByTestId("court-cell-court-1-7")).not.toBeInTheDocument();
    expect(screen.getByTestId("court-cell-court-1-8")).toBeInTheDocument();
    expect(screen.getByTestId("court-cell-court-1-23")).toBeInTheDocument();
    expect(screen.queryByTestId("court-cell-court-1-24")).not.toBeInTheDocument();
    expect(screen.getByText("10:00-11:00")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId("court-cell-court-1-23"));
    fireEvent.mouseUp(screen.getByTestId("court-cell-court-1-23"));
    expect(onChange).toHaveBeenCalledWith({
      starts_at: "2026-08-01T23:00",
      ends_at: "2026-08-02T00:00",
      court_ids: ["court-1"],
    });
  });

  it("scrolls to the requested initial hour using hourly row heights", () => {
    render(
      <CourtScheduleGrid
        courts={courts}
        date="2026-08-03"
        initialHour={14}
        items={[]}
        now={beforeSchedule}
        onSelectionChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId("court-schedule-scroll").scrollTop).toBe(244);
  });

  it("creates one continuous range across selected courts", () => {
    const onChange = vi.fn();
    render(
      <CourtScheduleGrid
        courts={courts}
        date="2026-08-01"
        items={[]}
        now={beforeSchedule}
        onSelectionChange={onChange}
      />,
    );

    fireEvent.mouseDown(screen.getByTestId("court-cell-court-1-10"));
    fireEvent.mouseEnter(screen.getByTestId("court-cell-court-2-12"));
    fireEvent.mouseUp(screen.getByTestId("court-cell-court-2-12"));

    expect(onChange).toHaveBeenCalledWith({
      starts_at: "2026-08-01T10:00",
      ends_at: "2026-08-01T13:00",
      court_ids: ["court-1", "court-2"],
    });
  });

  it("can add non-adjacent courts while preserving the continuous time range", () => {
    const onChange = vi.fn();
    render(
      <CourtScheduleGrid
        courts={courts}
        date="2026-08-01"
        items={[]}
        now={beforeSchedule}
        onSelectionChange={onChange}
      />,
    );

    fireEvent.mouseDown(screen.getByTestId("court-cell-court-1-10"));
    fireEvent.mouseUp(screen.getByTestId("court-cell-court-1-10"));
    fireEvent.mouseDown(screen.getByTestId("court-cell-court-3-10"));
    fireEvent.mouseUp(screen.getByTestId("court-cell-court-3-10"));

    expect(onChange).toHaveBeenLastCalledWith({
      starts_at: "2026-08-01T10:00",
      ends_at: "2026-08-01T11:00",
      court_ids: ["court-1", "court-3"],
    });
  });

  it("opens an existing occupied record for consistent edit actions", () => {
    const onItemSelect = vi.fn();
    const item = {
      id: "schedule-1",
      source_id: "booking-1",
      source_type: "venue_booking",
      title: "林先生 · 散客订场",
      starts_at: "2026-08-01T10:00:00+08:00",
      ends_at: "2026-08-01T11:00:00+08:00",
      status: "booked",
      resources: [{ type: "court", id: "C01" }],
    };
    render(
      <CourtScheduleGrid
        courts={courts}
        date="2026-08-01"
        items={[item]}
        onItemSelect={onItemSelect}
        onSelectionChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("court-cell-court-1-10"));
    expect(onItemSelect).toHaveBeenCalledWith(item);
    expect(screen.getByTestId("court-cell-court-1-10")).toHaveClass("h-12", "bg-amber-100", "text-amber-950");
    expect(screen.getByTestId("court-cell-court-1-10")).toHaveClass("opacity-65");
    expect(screen.getByTestId("court-cell-court-1-10")).toHaveTextContent("1 号场");
    expect(screen.getByLabelText("场地使用类型图例")).toHaveTextContent("订场");
  });

  it("marks an empty past slot and requires one confirmation before publishing it", () => {
    const onChange = vi.fn();
    render(
      <CourtScheduleGrid
        courts={courts}
        date="2026-08-01"
        items={[]}
        now={new Date("2026-08-01T12:30:00+08:00")}
        onSelectionChange={onChange}
      />,
    );

    const cell = screen.getByTestId("court-cell-court-1-10");
    expect(cell).toHaveClass("bg-slate-100", "text-slate-400");
    expect(cell.querySelector("svg")).toBeInTheDocument();

    fireEvent.mouseDown(cell);
    fireEvent.mouseUp(cell);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "这是已经失效的场地时段" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "继续补录" }));
    expect(onChange).toHaveBeenCalledWith({
      starts_at: "2026-08-01T10:00",
      ends_at: "2026-08-01T11:00",
      court_ids: ["court-1"],
      warning_acknowledgements: ["past_time"],
    });
  });

  it("offers all four creation actions after selection", () => {
    render(
      <ScheduleSelectionActions
        courts={courts}
        selection={{
          starts_at: "2026-08-01T10:00",
          ends_at: "2026-08-01T11:00",
          court_ids: ["court-1"],
        }}
        onCancel={vi.fn()}
        onChoose={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /新建排期/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /预约私教/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /新建订场/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /创建活动/ })).toBeInTheDocument();
  });
});
