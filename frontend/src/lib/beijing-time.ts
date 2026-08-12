export const BEIJING_TIME_ZONE = "Asia/Shanghai";

type TimeValue = string | number | Date;

function dateValue(value: TimeValue) {
  const result = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(result.getTime())) throw new RangeError("Invalid date value");
  return result;
}

function parts(value: TimeValue) {
  const items = new Intl.DateTimeFormat("en-CA", {
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(dateValue(value));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    items.find((item) => item.type === type)?.value ?? "";
  return {
    year: part("year"),
    month: part("month"),
    day: part("day"),
    hour: part("hour"),
    minute: part("minute"),
    second: part("second"),
  };
}

export function beijingDateKey(value: TimeValue = new Date()) {
  const item = parts(value);
  return `${item.year}-${item.month}-${item.day}`;
}

export function toBeijingDateTimeInput(value: TimeValue) {
  const item = parts(value);
  return `${item.year}-${item.month}-${item.day}T${item.hour}:${item.minute}`;
}

export function beijingDateTimeInputToIso(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)) {
    throw new RangeError("Invalid Beijing local date-time");
  }
  return new Date(`${value}${value.length === 16 ? ":00" : ""}+08:00`).toISOString();
}

export function beijingDayRange(value: TimeValue = new Date()) {
  const date = beijingDateKey(value);
  const start = new Date(`${date}T00:00:00+08:00`);
  return { date, start, end: new Date(start.getTime() + 24 * 60 * 60 * 1000) };
}

export function formatBeijing(
  value: TimeValue,
  options: Intl.DateTimeFormatOptions,
  locale = "zh-CN",
) {
  return new Intl.DateTimeFormat(locale, { ...options, timeZone: BEIJING_TIME_ZONE }).format(
    dateValue(value),
  );
}

export function formatBeijingDate(
  value: TimeValue,
  options: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  },
) {
  return formatBeijing(value, options);
}

export function formatBeijingTime(
  value: TimeValue,
  options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" },
) {
  return formatBeijing(value, options);
}

export function formatBeijingDateTime(value: TimeValue) {
  return formatBeijing(value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBusinessDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return formatBeijingDate(new Date(`${value}T00:00:00+08:00`));
}
