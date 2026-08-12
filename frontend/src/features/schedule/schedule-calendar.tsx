import FullCalendar from "@fullcalendar/react";
import interactionPlugin from "@fullcalendar/interaction";
import timeGridPlugin from "@fullcalendar/timegrid";
import { LockKeyhole } from "lucide-react";
import { useState } from "react";

import type { ScheduleSelection } from "./court-schedule-grid";
import { formatScheduleCourtNames, type CourtDirectoryItem } from "./court-display";
import { bulkDeleteBlockedReason } from "./schedule-bulk";
import { PastTimeSelectionDialog } from "./schedule-time-fields";
import { defaultVenueHours, isPastScheduleStart, type VenueHours } from "./schedule-time";
import { beijingDateKey, toBeijingDateTimeInput } from "@/lib/beijing-time";

export type ScheduleResource = {
  type?: string;
  id?: string;
  resource_type?: string;
  resource_id?: string;
};
export type ScheduleItem = {
  id: string;
  source_id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  source_type: string;
  status: string;
  resources?: ScheduleResource[];
};

function pad(value: number) {
  return String(value).padStart(2, "0");
}
function localDateTime(value: Date) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}
function hourRangeLabel(date: Date) {
  return `${pad(date.getHours())}:00-${pad(date.getHours() + 1)}:00`;
}

function initialVisibleRange(now: Date) {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const dayFromMonday = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - dayFromMonday);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return { start, end };
}

function pastBackgroundEvents(
  range: { start: Date; end: Date },
  venue: VenueHours,
  now: Date,
) {
  const events = [];
  for (const cursor = new Date(range.start); cursor < range.end; cursor.setDate(cursor.getDate() + 1)) {
    for (let slot = 8; slot < 24; slot += 1) {
      const start = new Date(cursor);
      start.setHours(slot, 0, 0, 0);
      if (!isPastScheduleStart(localDateTime(start), venue, now)) continue;
      const end = new Date(start);
      end.setHours(end.getHours() + 1);
      events.push({
        id: `past-${localDateTime(start)}`,
        start: localDateTime(start),
        end: localDateTime(end),
        display: "background",
        classNames: ["past-time-background"],
      });
    }
  }
  return events;
}

export function ScheduleCalendar({
  items,
  batchMode = false,
  courts,
  selectedIds,
  onBatchBlocked,
  onBatchToggle,
  onRangeChange,
  onSelect,
  onTimeSelect,
  now = new Date(),
  venue = defaultVenueHours,
}: {
  items: ScheduleItem[];
  batchMode?: boolean;
  courts?: CourtDirectoryItem[];
  selectedIds?: Set<string>;
  onBatchBlocked?: (item: ScheduleItem, reason: string) => void;
  onBatchToggle?: (item: ScheduleItem) => void;
  onRangeChange?: (start: Date) => void;
  onSelect: (item: ScheduleItem) => void;
  onTimeSelect: (selection: ScheduleSelection) => void;
  now?: Date;
  venue?: VenueHours;
}) {
  const [visibleRange, setVisibleRange] = useState(() => initialVisibleRange(now));
  const [pendingPastSelection, setPendingPastSelection] = useState<ScheduleSelection | null>(null);
  const scheduleEvents = items.map((item) => {
    const blocked = batchMode && Boolean(bulkDeleteBlockedReason(item));
    const past = isPastScheduleStart(item.starts_at, venue, now);
    return {
      id: item.id,
      title: `${item.title} · ${formatScheduleCourtNames(item, courts)}`,
      start: toBeijingDateTimeInput(item.starts_at),
      end: toBeijingDateTimeInput(item.ends_at),
      extendedProps: { past },
      classNames: [
        `event-${item.source_type}`,
        selectedIds?.has(item.id) ? "event-batch-selected" : "",
        blocked ? "event-batch-disabled" : "",
        past ? "event-past" : "",
      ].filter(Boolean),
    };
  });
  return (
    <>
      <FullCalendar
      allDaySlot={false}
      buttonText={{ today: "今天", day: "日", week: "周" }}
      datesSet={({ start, end }) => {
        setVisibleRange({ start, end });
        onRangeChange?.(start);
      }}
      eventClick={({ event }) => {
        const item = items.find((candidate) => candidate.id === event.id);
        if (!item) return;
        if (batchMode) {
          const blockedReason = bulkDeleteBlockedReason(item);
          if (blockedReason) onBatchBlocked?.(item, blockedReason);
          else onBatchToggle?.(item);
          return;
        }
        onSelect(item);
      }}
      eventContent={({ event, timeText }) => (
        <div className="fc-event-main-frame">
          {timeText && <div className="fc-event-time">{timeText}</div>}
          <div className="fc-event-title-container">
            <div className="fc-event-title fc-sticky">{event.title}</div>
          </div>
          {event.extendedProps.past && (
            <LockKeyhole aria-hidden="true" className="schedule-past-lock" size={11} />
          )}
        </div>
      )}
      events={[...pastBackgroundEvents(visibleRange, venue, now), ...scheduleEvents]}
      headerToolbar={{
        left: "prev,next today",
        center: "title",
        right: "timeGridDay,timeGridWeek",
      }}
      height={720}
      initialView="timeGridWeek"
      initialDate={beijingDateKey(now)}
      locale="zh-cn"
      plugins={[timeGridPlugin, interactionPlugin]}
      select={({ start, end }) => {
        const selection = {
          starts_at: localDateTime(start),
          ends_at: localDateTime(end),
          court_ids: [],
        };
        if (isPastScheduleStart(selection.starts_at, venue, now)) {
          setPendingPastSelection(selection);
          return;
        }
        onTimeSelect(selection);
      }}
      selectAllow={({ start, end }) =>
        localDateTime(start).slice(0, 10)
          === localDateTime(new Date(end.getTime() - 1)).slice(0, 10)
      }
      selectMirror
      selectable={!batchMode}
      slotDuration="01:00:00"
      snapDuration="01:00:00"
      slotLabelContent={({ date }) => hourRangeLabel(date)}
      slotMaxTime="24:00:00"
      slotMinTime="08:00:00"
      />
      {pendingPastSelection && (
        <PastTimeSelectionDialog
          onCancel={() => setPendingPastSelection(null)}
          onConfirm={() => {
            onTimeSelect({
              ...pendingPastSelection,
              warning_acknowledgements: ["past_time"],
            });
            setPendingPastSelection(null);
          }}
        />
      )}
    </>
  );
}
