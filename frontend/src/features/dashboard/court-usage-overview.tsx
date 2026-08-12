import { MapPin } from "lucide-react";

import type { ScheduleItem } from "@/features/schedule/schedule-calendar";
import { formatBeijingTime } from "@/lib/beijing-time";
import {
  canonicalCourtId,
  type CourtDirectoryItem,
  scheduleCourtReferences,
} from "@/features/schedule/court-display";

type CourtUsageSegment = {
  item: ScheduleItem;
  top: number;
  height: number;
};

const usageStyles: Record<string, string> = {
  fixed_class: "border-green-300 bg-green-100",
  class_session: "border-green-300 bg-green-100",
  private_lesson: "border-indigo-300 bg-indigo-100",
  venue_booking: "border-amber-300 bg-amber-100",
  event: "border-rose-300 bg-rose-100",
  manual: "border-cyan-300 bg-cyan-100",
  court_block: "border-slate-300 bg-slate-200",
};

const usageLegend = [
  { label: "固定班", className: "border-green-300 bg-green-100" },
  { label: "私教", className: "border-indigo-300 bg-indigo-100" },
  { label: "订场", className: "border-amber-300 bg-amber-100" },
  { label: "活动", className: "border-rose-300 bg-rose-100" },
];

const courtUsageSourceNames: Record<string, string> = {
  fixed_class: "固定班",
  class_session: "固定班",
  private_lesson: "私教",
  venue_booking: "订场",
  event: "活动",
  manual: "临时排期",
};

function usageSegments(
  schedule: ScheduleItem[],
  courtId: string,
  courtDirectory: CourtDirectoryItem[],
  windowStart: Date,
  windowEnd: Date,
): CourtUsageSegment[] {
  const rangeStart = windowStart.getTime();
  const rangeEnd = windowEnd.getTime();
  const duration = rangeEnd - rangeStart;
  return schedule.flatMap((item) => {
    if (item.status === "cancelled") return [];
    const usesCourt = scheduleCourtReferences(item).some(
      (reference) => canonicalCourtId(reference, courtDirectory) === courtId,
    );
    if (!usesCourt) return [];
    const itemStart = Math.max(new Date(item.starts_at).getTime(), rangeStart);
    const itemEnd = Math.min(new Date(item.ends_at).getTime(), rangeEnd);
    if (itemEnd <= itemStart) return [];
    return [
      {
        item,
        top: ((itemStart - rangeStart) / duration) * 100,
        height: ((itemEnd - itemStart) / duration) * 100,
      },
    ];
  });
}

function shortTime(value: string) {
  return formatBeijingTime(value);
}

export function CourtUsageOverview({
  schedule,
  courts,
  windowStart,
  windowEnd,
  maxCourts,
  expanded = false,
}: {
  schedule: ScheduleItem[];
  courts: CourtDirectoryItem[];
  windowStart: Date;
  windowEnd: Date;
  maxCourts?: number;
  expanded?: boolean;
}) {
  const activeCourts = courts.filter((court) => court.is_active !== false);
  const courtUsage = activeCourts.map((court) => ({
    court,
    segments: usageSegments(schedule, court.id, activeCourts, windowStart, windowEnd),
  }));
  const scheduledCourtCount = courtUsage.filter((item) => item.segments.length > 0).length;
  const visibleCourtUsage = maxCourts === undefined ? courtUsage : courtUsage.slice(0, maxCourts);

  return (
    <div className={expanded ? "p-5" : "p-4"}>
      <div className="flex items-end justify-between">
        <div>
          <b className="text-2xl text-slate-800">
            {scheduledCourtCount}
            <small className="ml-1 text-xs font-normal text-slate-400">
              / {activeCourts.length}
            </small>
          </b>
          <p className="mb-0 mt-1 text-xs text-slate-500">片场地已有安排</p>
        </div>
        <span className="grid size-9 place-items-center rounded-md bg-emerald-50 text-emerald-700">
          <MapPin size={17} />
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5" aria-label="场地使用类型图例">
        {usageLegend.map((item) => (
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold text-slate-600 ${item.className}`}
            key={item.label}
          >
            {item.label}
          </span>
        ))}
      </div>
      <div
        className={
          expanded
            ? "mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8"
            : "mt-4 grid grid-cols-4 gap-2.5"
        }
      >
        {visibleCourtUsage.map(({ court, segments }) => (
          <div className="min-w-0" key={court.id}>
            <div
              aria-label={`${court.name}今日使用情况`}
              className={`relative overflow-hidden rounded-md border border-slate-300 bg-white shadow-inner ${expanded ? "h-72" : "h-56"}`}
              data-testid={`court-usage-${court.id}`}
            >
              {segments.map(({ item, top, height }) => (
                <div
                  aria-label={`${courtUsageSourceNames[item.source_type] ?? item.source_type}，${item.title}，${shortTime(item.starts_at)} 至 ${shortTime(item.ends_at)}`}
                  className={`absolute inset-x-0 border-y ${usageStyles[item.source_type] ?? "border-slate-300 bg-slate-100"}`}
                  data-source-type={item.source_type}
                  data-testid={`court-usage-segment-${court.id}-${item.id}`}
                  key={item.id}
                  role="img"
                  style={{ top: `${top}%`, height: `${height}%`, minHeight: "4px" }}
                  title={`${courtUsageSourceNames[item.source_type] ?? item.source_type} · ${item.title}\n${shortTime(item.starts_at)}–${shortTime(item.ends_at)}`}
                />
              ))}
            </div>
            <div
              className="mt-2 truncate text-center text-[10px] font-medium text-slate-500"
              title={court.name}
            >
              {court.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
