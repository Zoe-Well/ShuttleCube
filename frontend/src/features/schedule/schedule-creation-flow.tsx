import { useState } from "react";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { EventForm, type EventFormInput } from "@/features/events/event-form";
import { LessonForm, type LessonInput } from "@/features/private-lessons/lesson-form";
import { BookingForm, type BookingInput } from "@/features/venue-bookings/booking-form";
import { QuotePanel } from "@/features/venue-bookings/quote-panel";
import type { CourtItem, ScheduleSelection } from "./court-schedule-grid";
import { ScheduleForm } from "./schedule-form";
import {
  ScheduleSelectionActions,
  type ScheduleCreationAction,
} from "./schedule-selection-actions";
import { toApiDateTime } from "./schedule-time";
import { useVenueHours } from "./use-venue-hours";

const drawerTitles: Record<ScheduleCreationAction, [string, string]> = {
  schedule: ["创建排期", "系统将在保存前自动检查资源冲突"],
  private_lesson: ["预约私教课程", "场地和时间已根据排期选择自动填写"],
  venue_booking: ["新增场地预订", "场地和时间已根据排期选择自动填写"],
  event: ["创建临时活动", "场地和时间已根据排期选择自动填写"],
};

function splitIds(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ScheduleCreationFlow({
  action,
  courts,
  onActionChange,
  onCreated,
  onSelectionChange,
  selection,
}: {
  action: ScheduleCreationAction | null;
  courts: CourtItem[];
  onActionChange: (action: ScheduleCreationAction | null) => void;
  onCreated: () => void;
  onSelectionChange: (selection: ScheduleSelection | null) => void;
  selection: ScheduleSelection | null;
}) {
  const [quote, setQuote] = useState<number | null>(null);
  const venue = useVenueHours();
  const initialWarningAcknowledgements = selection?.warning_acknowledgements ?? [];
  const prefill = selection
    ? {
        starts_at: selection.starts_at,
        ends_at: selection.ends_at,
        court_ids: selection.court_ids.join(","),
      }
    : undefined;

  const close = () => {
    onActionChange(null);
    onSelectionChange(null);
    setQuote(null);
  };
  const done = () => {
    close();
    onCreated();
  };
  const createLesson = async (value: LessonInput & { warning_acknowledgements: string[] }) => {
    await api("/private-lessons", {
      method: "POST",
      body: JSON.stringify({
        ...value,
        starts_at: toApiDateTime(value.starts_at),
        ends_at: toApiDateTime(value.ends_at),
        court_ids: splitIds(value.court_ids),
      }),
    });
    done();
  };
  const bookingWire = (value: BookingInput & { warning_acknowledgements?: string[] }) => ({
    ...value,
    starts_at: toApiDateTime(value.starts_at),
    ends_at: toApiDateTime(value.ends_at),
    court_ids: splitIds(value.court_ids),
  });
  const getQuote = async (value: BookingInput) => {
    setQuote(null);
    const result = await api<{ suggested_receivable: number }>("/venue-bookings/quote", {
      method: "POST",
      body: JSON.stringify(bookingWire(value)),
    });
    const suggested = Number(result.suggested_receivable);
    setQuote(suggested);
    return suggested;
  };
  const createBooking = async (value: BookingInput & { warning_acknowledgements: string[] }) => {
    await api("/venue-bookings", { method: "POST", body: JSON.stringify(bookingWire(value)) });
    done();
  };
  const createEvent = async (value: EventFormInput & { warning_acknowledgements: string[] }) => {
    await api("/events", {
      method: "POST",
      body: JSON.stringify({
        ...value,
        starts_at: toApiDateTime(value.starts_at),
        ends_at: toApiDateTime(value.ends_at),
        court_ids: splitIds(value.court_ids),
        participant_ids: splitIds(value.participant_ids),
      }),
    });
    done();
  };

  return (
    <>
      {selection && !action && (
        <ScheduleSelectionActions
          courts={courts}
          selection={selection}
          onCancel={() => onSelectionChange(null)}
          onChoose={(nextAction, courtIds) => {
            onSelectionChange({ ...selection, court_ids: courtIds });
            onActionChange(nextAction);
          }}
        />
      )}
      <Drawer
        open={action !== null}
        title={action ? drawerTitles[action][0] : ""}
        description={action ? drawerTitles[action][1] : ""}
        onClose={close}
      >
        {action === "schedule" && (
          <ScheduleForm
            courts={courts}
            initialValues={prefill}
            initialWarningAcknowledgements={initialWarningAcknowledgements}
            venue={venue.data}
            onCancel={close}
            onCreated={done}
          />
        )}
        {action === "private_lesson" && (
          <LessonForm
            courts={courts}
            initialValues={prefill}
            initialWarningAcknowledgements={initialWarningAcknowledgements}
            venue={venue.data}
            onSubmit={(value) => void createLesson(value)}
          />
        )}
        {action === "venue_booking" && (
          <>
            <div className="mb-5">
              <QuotePanel suggested={quote} />
            </div>
            <BookingForm
              courts={courts}
              initialValues={prefill}
              initialWarningAcknowledgements={initialWarningAcknowledgements}
              venue={venue.data}
              onQuote={getQuote}
              onSubmit={(value) => void createBooking(value)}
            />
          </>
        )}
        {action === "event" && (
          <EventForm
            courts={courts}
            initialValues={prefill}
            initialWarningAcknowledgements={initialWarningAcknowledgements}
            venue={venue.data}
            onSubmit={(value) => void createEvent(value)}
          />
        )}
      </Drawer>
    </>
  );
}
