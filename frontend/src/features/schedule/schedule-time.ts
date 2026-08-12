export type ScheduleWarningCode = "past_time" | "outside_business_hours";

export type VenueHours = {
  timezone: string;
  weekday_open_time: string;
  weekday_close_time: string;
  weekend_open_time: string;
  weekend_close_time: string;
};

export type ScheduleTimeWarning = {
  code: ScheduleWarningCode;
  message: string;
};

export const defaultVenueHours: VenueHours = {
  timezone: "Asia/Shanghai",
  weekday_open_time: "14:00:00",
  weekday_close_time: "22:00:00",
  weekend_open_time: "08:00:00",
  weekend_close_time: "22:00:00",
};

export function venueNowKey(now: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function isPastScheduleStart(
  startsAt: string,
  venue: VenueHours = defaultVenueHours,
  now = new Date(),
) {
  return Boolean(startsAt) && startsAt < venueNowKey(now, venue.timezone);
}

function isWeekend(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return weekday === 0 || weekday === 6;
}

export function analyzeScheduleTime(
  startsAt: string,
  endsAt: string,
  venue: VenueHours = defaultVenueHours,
  now = new Date(),
): { error: string | null; warnings: ScheduleTimeWarning[] } {
  if (!startsAt || !endsAt) return { error: "请选择完整的开始和结束时间", warnings: [] };
  if (![startsAt, endsAt].every((value) => /T\d{2}:00$/.test(value))) {
    return { error: "开始和结束时间必须选择整点", warnings: [] };
  }
  if (endsAt <= startsAt) return { error: "结束时间必须晚于开始时间", warnings: [] };

  const warnings: ScheduleTimeWarning[] = [];
  if (isPastScheduleStart(startsAt, venue, now)) {
    warnings.push({ code: "past_time", message: "所选开始时间已经过去。" });
  }

  const startDate = startsAt.slice(0, 10);
  const endDate = endsAt.slice(0, 10);
  const weekend = isWeekend(startDate);
  const open = (weekend ? venue.weekend_open_time : venue.weekday_open_time).slice(0, 5);
  const close = (weekend ? venue.weekend_close_time : venue.weekday_close_time).slice(0, 5);
  if (startDate !== endDate || startsAt.slice(11, 16) < open || endsAt.slice(11, 16) > close) {
    warnings.push({
      code: "outside_business_hours",
      message: `所选时间不在球馆营业时段 ${open}–${close} 内。`,
    });
  }
  return { error: null, warnings };
}

export function toApiDateTime(value: string) {
  return beijingDateTimeInputToIso(value);
}
import { beijingDateTimeInputToIso } from "@/lib/beijing-time";
