import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { api } from "@/api/client";
import { AttendancePanel } from "./attendance-panel";
import { ClassDetailPage } from "./class-detail-page";
import { ClassesPage } from "./classes-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

beforeEach(() => vi.mocked(api).mockReset());
afterEach(cleanup);

function provider(children: React.ReactNode) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

describe("classes", () => {
  it("renders class management entry", () => {
    vi.mocked(api).mockResolvedValue([]);
    render(provider(<MemoryRouter><ClassesPage /></MemoryRouter>));
    expect(screen.getByText("固定班管理")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建固定班" })).toBeInTheDocument();
  });

  it("shows and fills the fixed-class coach fee from the selected coach rate", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/classes") return Promise.resolve([]);
      if (path === "/coaches") {
        return Promise.resolve([{ id: "coach-1", name: "陈教练", is_active: true, fixed_class_fee: 180 }]);
      }
      if (path === "/courts") {
        return Promise.resolve([{ id: "court-1", code: "1", name: "1 号场地", is_active: true }]);
      }
      return Promise.resolve([]);
    });
    render(provider(<MemoryRouter><ClassesPage /></MemoryRouter>));

    const createButtons = screen.getAllByRole("button", { name: "新建固定班" });
    fireEvent.click(createButtons[createButtons.length - 1]);
    const coachField = await screen.findByLabelText("授课教练");
    await screen.findByRole("option", { name: "陈教练" });
    fireEvent.change(coachField, { target: { value: "coach-1" } });

    await waitFor(() => expect(screen.getByLabelText(/单节教练费/)).toHaveValue(180));
    expect(screen.getByLabelText("1 号场地")).toBeInTheDocument();
  });

  it("keeps the lesson unit when a leave is marked as non-deducting", async () => {
    vi.mocked(api).mockResolvedValue({});
    render(provider(
      <AttendancePanel
        sessionId="session-target"
        enrollments={[{ id: "enrollment-1", student_id: "student-1", student_name: "请假学员" }]}
        onDone={vi.fn()}
      />,
    ));

    const deduct = screen.getByLabelText("扣本节课时");
    fireEvent.change(screen.getByLabelText("请假学员出勤状态"), { target: { value: "leave" } });
    fireEvent.click(deduct);
    expect(deduct).not.toBeChecked();
    expect(screen.getByText(/原班续期课程或转移到其他班级/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "完成考勤并生成教练费用" }));
    await waitFor(() => {
      const attendanceCall = vi.mocked(api).mock.calls.find(
        ([path]) => path === "/class-sessions/session-target/attendance:finalize",
      );
      expect(attendanceCall).toBeDefined();
      const body = JSON.parse(String(attendanceCall?.[1]?.body));
      expect(body.decisions[0]).toMatchObject({ status: "leave", deduct_units: 0 });
      expect(body.decisions[0]).not.toHaveProperty("grants_makeup");
    });
  });

  it("marks a zero-enrollment session as not held instead of opening attendance", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/classes/class-empty") {
        return Promise.resolve({
          id: "class-empty",
          name: "测试周五固定班",
          status: "active",
          version: 1,
          session_count: 1,
          capacity: 10,
          coach_fee_per_session: 80,
          finance: { actual_amount: 0, received_amount: 0, refunded_amount: 0, net_received: 0, outstanding_amount: 0 },
          sessions: [{
            id: "session-empty",
            version: 3,
            sequence_number: 1,
            scheduled_start: "2026-08-07T10:00:00Z",
            scheduled_end: "2026-08-07T11:00:00Z",
            status: "scheduled",
            replacement_for_session_id: null,
            replacement_for_sequence: null,
            replacement_decision: null,
            attendance_finalized_at: null,
            attendance: [],
            coach_fee: null,
          }],
          enrollments: [],
        });
      }
      return Promise.resolve({});
    });
    render(provider(
      <MemoryRouter initialEntries={["/classes/class-empty"]}>
        <Routes><Route path="/classes/:id" element={<ClassDetailPage />} /></Routes>
      </MemoryRouter>,
    ));

    expect(await screen.findByRole("button", { name: "标记未开课（无学员）" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "完成考勤" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "标记未开课（无学员）" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/class-sessions/session-empty/no-enrollment:mark-not-held",
      { method: "POST", body: JSON.stringify({ version: 3 }) },
    ));
  });

  it("shows ending classes for the selected day range", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (typeof path === "string" && path.includes("ending_within_days=15")) {
        return Promise.resolve([
          {
            id: "class-ending",
            name: "暑期进阶班",
            class_type: "training",
            start_date: "2026-07-01",
            default_start_time: "18:00:00",
            session_count: 10,
            capacity: 12,
            default_coach_id: "coach-1",
            status: "active",
            last_scheduled_end: "2026-08-18T11:00:00Z",
            remaining_scheduled_sessions: 2,
          },
        ]);
      }
      return Promise.resolve([]);
    });

    render(provider(
      <MemoryRouter initialEntries={["/classes?attention=ending&days=15"]}>
        <ClassesPage />
      </MemoryRouter>,
    ));

    expect(await screen.findByText("暑期进阶班")).toBeInTheDocument();
    expect(screen.getByText("2 节")).toBeInTheDocument();
    expect(api).toHaveBeenCalledWith(expect.stringContaining("ending_within_days=15"));
  });

  it("opens completed attendance results from the course plan", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/classes/class-attendance") {
        return Promise.resolve({
          id: "class-attendance",
          name: "周末基础班",
          status: "active",
          session_count: 1,
          capacity: 12,
          finance: { actual_amount: 100, received_amount: 100, refunded_amount: 0, net_received: 100, outstanding_amount: 0 },
          sessions: [{
            id: "session-1",
            sequence_number: 1,
            scheduled_start: "2026-08-04T10:00:00Z",
            scheduled_end: "2026-08-04T11:00:00Z",
            status: "completed",
            attendance_finalized_at: "2026-08-04T11:05:00Z",
            attendance: [{
              id: "attendance-1",
              student_id: "student-1",
              student_name: "考勤学员",
              status: "leave",
              deduct_units: 0,
              decision_note: "已提前请假",
            }],
          }],
          enrollments: [],
        });
      }
      return Promise.resolve([]);
    });
    render(provider(
      <MemoryRouter initialEntries={["/classes/class-attendance"]}>
        <Routes><Route path="/classes/:id" element={<ClassDetailPage />} /></Routes>
      </MemoryRouter>,
    ));

    fireEvent.click(await screen.findByRole("button", { name: "查看考勤（1人）" }));

    expect(screen.getByText("考勤学员")).toBeInTheDocument();
    expect(screen.getByText("请假")).toBeInTheDocument();
    expect(screen.getByText("未扣课时")).toBeInTheDocument();
    expect(screen.getByText("已提前请假")).toBeInTheDocument();
  });

  it("shows enrollment cash facts and opens the shared payment flow", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/classes/class-1") {
        return Promise.resolve({
          id: "class-1",
          name: "周末提高班",
          status: "active",
          session_count: 10,
          capacity: 12,
          finance: { actual_amount: 400, received_amount: 150, refunded_amount: 0, net_received: 150, outstanding_amount: 250 },
          sessions: [],
          enrollments: [{
            id: "enrollment-1",
            student_id: "student-1",
            student_name: "林小羽",
            purchased_units: 4,
            status: "active",
            finance: { receivable_id: "receivable-1", actual_amount: 400, received_amount: 150, refunded_amount: 0, net_received: 150, outstanding_amount: 250, payment_status: "partial" },
          }],
        });
      }
      if (path === "/receivables/receivable-1") {
        return Promise.resolve({
          receivable_id: "receivable-1",
          source_type: "enrollment",
          source_id: "enrollment-1",
          business_name: "固定班-林小羽",
          suggested_amount: 400,
          actual_amount: 400,
          received_amount: 150,
          refunded_amount: 0,
          net_received: 150,
          outstanding_amount: 250,
          refundable_amount: 150,
          payment_status: "partial",
          status: "open",
          version: 1,
          payments: [],
          refunds: [],
        });
      }
      return Promise.resolve([]);
    });
    render(provider(
      <MemoryRouter initialEntries={["/classes/class-1"]}>
        <Routes><Route path="/classes/:id" element={<ClassDetailPage />} /></Routes>
      </MemoryRouter>,
    ));

    expect(await screen.findByText("林小羽")).toBeInTheDocument();
    expect(screen.getAllByText("¥250.00").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "收费/流水" }));
    expect(await screen.findByText("固定班-林小羽")).toBeInTheDocument();
    expect(screen.getByText("业务应收、收款与退款明细")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登记收款" })).toBeInTheDocument();
  });
});
