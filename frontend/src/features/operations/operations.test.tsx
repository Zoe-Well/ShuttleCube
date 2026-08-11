import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EventForm } from "@/features/events/event-form";
import { LessonForm } from "@/features/private-lessons/lesson-form";
import { BookingForm } from "@/features/venue-bookings/booking-form";
import { ScheduleForm } from "@/features/schedule/schedule-form";

afterEach(cleanup);

const courts = [{ id: "court-1", code: "C01", name: "1 号标准场" }];

function renderWithQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function selectCourt() {
  fireEvent.click(screen.getByRole("button", { name: "C01 · 1 号标准场" }));
}

describe("operations forms", () => {
  it("exposes private lesson, booking and event actions", () => {
    const fn = vi.fn();
    renderWithQuery(
      <>
        <LessonForm courts={courts} onSubmit={fn} />
        <BookingForm courts={courts} onQuote={fn} onSubmit={fn} />
        <EventForm courts={courts} onSubmit={fn} />
      </>,
    );
    expect(screen.getByRole("button", { name: "预约私教" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认订场" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建活动" })).toBeInTheDocument();
  });

  it("uses hourly inputs and blocks an invalid range in red", async () => {
    const submit = vi.fn();
    render(<BookingForm courts={courts} onQuote={vi.fn()} onSubmit={submit} />);
    const start = screen.getByLabelText(/开始时间/) as HTMLInputElement;
    const end = screen.getByLabelText(/结束时间/) as HTMLInputElement;
    expect(start.step).toBe("3600");
    fireEvent.change(screen.getByLabelText(/客户姓名/), { target: { value: "测试客户" } });
    selectCourt();
    fireEvent.change(start, { target: { value: "2099-08-01T15:00" } });
    fireEvent.change(end, { target: { value: "2099-08-01T14:00" } });
    fireEvent.click(screen.getByRole("button", { name: "确认订场" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("结束时间必须晚于开始时间");
    expect(submit).not.toHaveBeenCalled();
  });

  it("requires explicit confirmation for a warning and forwards the acknowledgement", async () => {
    const submit = vi.fn();
    render(<BookingForm courts={courts} onQuote={vi.fn()} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText(/客户姓名/), { target: { value: "测试客户" } });
    selectCourt();
    fireEvent.change(screen.getByLabelText(/开始时间/), { target: { value: "2020-08-01T08:00" } });
    fireEvent.change(screen.getByLabelText(/结束时间/), { target: { value: "2020-08-01T09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "确认订场" }));
    expect(await screen.findByRole("dialog", { name: "请确认排期时间" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "仍然保存" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(
        expect.objectContaining({ warning_acknowledgements: ["past_time"] }),
      ),
    );
  });

  it("does not ask twice when a past slot was already confirmed in the schedule", async () => {
    const submit = vi.fn();
    render(
      <BookingForm
        courts={courts}
        initialWarningAcknowledgements={["past_time"]}
        onQuote={vi.fn()}
        onSubmit={submit}
      />,
    );
    fireEvent.change(screen.getByLabelText(/客户姓名/), { target: { value: "补录客户" } });
    selectCourt();
    fireEvent.change(screen.getByLabelText(/开始时间/), { target: { value: "2020-08-01T08:00" } });
    fireEvent.change(screen.getByLabelText(/结束时间/), { target: { value: "2020-08-01T09:00" } });

    fireEvent.click(screen.getByRole("button", { name: "确认订场" }));

    expect(screen.queryByRole("dialog", { name: "请确认排期时间" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(
        expect.objectContaining({ warning_acknowledgements: ["past_time"] }),
      ),
    );
  });

  it("requires a package after switching a private lesson to package billing", async () => {
    const submit = vi.fn();
    renderWithQuery(<LessonForm courts={courts} initialValues={{ billing_mode: "single" }} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText(/学员/), { target: { value: "student-1" } });
    fireEvent.change(screen.getByLabelText(/教练$/), { target: { value: "coach-1" } });
    fireEvent.change(screen.getByLabelText(/结算方式/), { target: { value: "package" } });
    fireEvent.change(screen.getByLabelText(/开始时间/), { target: { value: "2099-08-01T10:00" } });
    fireEvent.change(screen.getByLabelText(/结束时间/), { target: { value: "2099-08-01T11:00" } });
    selectCourt();

    fireEvent.click(screen.getByRole("button", { name: "预约私教" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("课包扣课模式下必须选择关联课包");
    expect(submit).not.toHaveBeenCalled();
  });

  it("fills an empty booking price with the calculated default", async () => {
    const quote = vi.fn()
      .mockResolvedValueOnce(160)
      .mockResolvedValueOnce(240)
      .mockResolvedValueOnce(320);
    render(<BookingForm courts={courts} onQuote={quote} onSubmit={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/开始时间/), { target: { value: "2099-08-01T10:00" } });
    fireEvent.change(screen.getByLabelText(/结束时间/), { target: { value: "2099-08-01T12:00" } });
    selectCourt();

    fireEvent.click(screen.getByRole("button", { name: "计算建议金额" }));

    await waitFor(() => expect(screen.getByLabelText(/实际应收/)).toHaveValue(160));

    fireEvent.change(screen.getByLabelText(/结束时间/), { target: { value: "2099-08-01T13:00" } });
    fireEvent.click(screen.getByRole("button", { name: "计算建议金额" }));
    await waitFor(() => expect(screen.getByLabelText(/实际应收/)).toHaveValue(240));

    fireEvent.change(screen.getByLabelText(/实际应收/), { target: { value: "200" } });
    fireEvent.change(screen.getByLabelText(/结束时间/), { target: { value: "2099-08-01T14:00" } });
    fireEvent.click(screen.getByRole("button", { name: "计算建议金额" }));
    await waitFor(() => expect(quote).toHaveBeenCalledTimes(3));
    expect(screen.getByLabelText(/实际应收/)).toHaveValue(200);
  });

  it("locks prefilled courts with real court codes and supplies default names", () => {
    const fn = vi.fn();
    const { container } = renderWithQuery(
      <>
        <ScheduleForm courts={courts} initialValues={{ court_ids: "court-1" }} onCancel={fn} onCreated={fn} />
        <LessonForm courts={courts} initialValues={{ court_ids: "court-1" }} onSubmit={fn} />
        <BookingForm courts={courts} initialValues={{ court_ids: "court-1" }} onQuote={vi.fn()} onSubmit={fn} />
        <EventForm courts={courts} initialValues={{ court_ids: "court-1" }} onSubmit={fn} />
      </>,
    );

    const lockedCourts = screen.getAllByDisplayValue("C01 · 1 号标准场");
    expect(lockedCourts).toHaveLength(4);
    expect(lockedCourts.every((field) => field.hasAttribute("readonly"))).toBe(true);
    expect(screen.getAllByDisplayValue("court-1").every((field) => field.getAttribute("type") === "hidden")).toBe(true);
    expect(container.querySelector('input[name="title"]')).toHaveValue("临时排期");
    expect(container.querySelector('input[name="name"]')).toHaveValue("临时活动");
  });
});
