import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { api } from "@/api/client";
import { LessonForm } from "./lesson-form";
import { PrivateLessonsPage } from "./private-lessons-page";

vi.mock("@/api/client", () => ({ api: vi.fn().mockResolvedValue([]) }));

afterEach(() => {
  vi.clearAllMocks();
});

describe("private lessons", () => {
  it("fills the private lesson fee from the selected coach rate", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/students") return Promise.resolve({ items: [] });
      if (path === "/coaches") {
        return Promise.resolve([
          { id: "coach-1", name: "陈教练", private_lesson_fee: 220 },
        ]);
      }
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <LessonForm courts={[]} onSubmit={vi.fn()} />
      </QueryClientProvider>,
    );

    const coachField = await screen.findByLabelText("教练");
    await screen.findByRole("option", { name: "陈教练" });
    fireEvent.change(coachField, { target: { value: "coach-1" } });

    await waitFor(() => expect(screen.getByLabelText(/教练费/)).toHaveValue(220));
    view.unmount();
    client.clear();
  });

  it("opens the linked lesson detail from a coach fee source", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/private-lessons") {
        return Promise.resolve([
          {
            id: "lesson-1",
            schedule_entry_id: "schedule-1",
            student_id: "student-1",
            student_name: "胡东东",
            coach_id: "coach-1",
            coach_name: "陈教练",
            billing_mode: "single",
            actual_receivable: 300,
            coach_fee: 220,
            starts_at: "2026-08-01T10:00:00+00:00",
            ends_at: "2026-08-01T11:00:00+00:00",
            court_ids: ["court-1"],
            status: "completed",
          },
        ]);
      }
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/private-lessons?lesson_id=lesson-1"]}>
          <PrivateLessonsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("私教课程详情")).toBeInTheDocument();
    expect(screen.getByText(/单次收费：¥300.00/)).toBeInTheDocument();
    view.unmount();
    client.clear();
  });

  it("filters private lessons by student or coach name", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/private-lessons")
        return Promise.resolve([
          {
            id: "lesson-1",
            schedule_entry_id: "schedule-1",
            student_id: "student-1",
            student_name: "胡东东",
            coach_id: "coach-1",
            coach_name: "陈教练",
            billing_mode: "single",
            starts_at: "2026-08-01T02:00:00+00:00",
            ends_at: "2026-08-01T02:30:00+00:00",
            court_ids: ["court-1"],
            status: "booked",
          },
          {
            id: "lesson-2",
            schedule_entry_id: "schedule-2",
            student_id: "student-2",
            student_name: "林小羽",
            coach_id: "coach-2",
            coach_name: "王教练",
            billing_mode: "single",
            starts_at: "2026-08-01T03:00:00+00:00",
            ends_at: "2026-08-01T03:30:00+00:00",
            court_ids: ["court-1"],
            status: "booked",
          },
        ]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PrivateLessonsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("胡东东")).toBeInTheDocument();
    expect(screen.getByText("林小羽")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("搜索私教预约"), {
      target: { value: "王教练" },
    });
    expect(screen.queryByText("胡东东")).not.toBeInTheDocument();
    expect(screen.getByText("林小羽")).toBeInTheDocument();

    view.unmount();
    client.clear();
  });

  it("shows student and coach names instead of identifiers", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/private-lessons")
        return Promise.resolve([
          {
            id: "lesson-1",
            schedule_entry_id: "schedule-1",
            student_id: "student-1",
            student_name: "胡东东",
            coach_id: "coach-1",
            coach_name: "陈教练",
            billing_mode: "single",
            starts_at: "2026-08-01T02:00:00+00:00",
            ends_at: "2026-08-01T02:30:00+00:00",
            court_ids: ["court-1"],
            status: "booked",
          },
        ]);
      if (path === "/courts")
        return Promise.resolve([{ id: "court-1", code: "1", name: "1 号场地" }]);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PrivateLessonsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("胡东东")).toBeInTheDocument();
    expect(screen.getByText("陈教练")).toBeInTheDocument();
    expect(screen.getByText("1 号场地")).toBeInTheDocument();
    expect(screen.queryByText(/student-1/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "预约私教" })).toHaveAttribute("href", "/schedule");

    view.unmount();
    client.clear();
  });

  it("requires explicit confirmation for an ended private lesson", async () => {
    const endedAt = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const startedAt = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/private-lessons") {
        return Promise.resolve([{
          id: "lesson-past",
          schedule_entry_id: "schedule-past",
          student_id: "student-past",
          student_name: "待完成学员",
          coach_id: "coach-past",
          coach_name: "待完成教练",
          billing_mode: "single",
          actual_receivable: 300,
          coach_fee: 200,
          starts_at: startedAt,
          ends_at: endedAt,
          court_ids: ["court-1"],
          status: "booked",
        }]);
      }
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PrivateLessonsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("待确认完成")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认完成" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "确认完成私教并扣课、生成教练费用" }),
    );

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        "/private-lessons/lesson-past/complete",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    view.unmount();
    client.clear();
  });
});
