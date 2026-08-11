import { describe, expect, it } from "vitest";

import { analyzeScheduleTime, type VenueHours } from "./schedule-time";

const venue: VenueHours = {
  timezone: "Asia/Shanghai",
  weekday_open_time: "14:00:00",
  weekday_close_time: "22:00:00",
  weekend_open_time: "08:00:00",
  weekend_close_time: "22:00:00",
};

describe("schedule time rules", () => {
  it("blocks an end time that is not after the start", () => {
    const result = analyzeScheduleTime("2026-07-31T15:00", "2026-07-31T14:00", venue);

    expect(result.error).toContain("结束时间必须晚于开始时间");
  });

  it("blocks time values that are not on the hour", () => {
    const result = analyzeScheduleTime("2026-07-31T14:30", "2026-07-31T16:00", venue);

    expect(result.error).toContain("必须选择整点");
  });

  it("returns confirmable warnings for a past, off-hours slot", () => {
    const result = analyzeScheduleTime(
      "2026-07-31T13:00",
      "2026-07-31T14:00",
      venue,
      new Date("2026-07-31T15:00:00+08:00"),
    );

    expect(result.error).toBeNull();
    expect(result.warnings.map((warning) => warning.code)).toEqual([
      "past_time",
      "outside_business_hours",
    ]);
  });
});
