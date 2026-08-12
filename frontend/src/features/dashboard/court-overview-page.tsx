import { useQuery } from "@tanstack/react-query";
import { CalendarCheck2 } from "lucide-react";
import { Link } from "react-router";

import { api } from "@/api/client";
import { PageHeader, Panel } from "@/components/operations/page";
import type { ScheduleItem } from "@/features/schedule/schedule-calendar";
import { useCourtDirectory } from "@/features/schedule/court-display";
import { beijingDayRange } from "@/lib/beijing-time";
import { CourtUsageOverview } from "./court-usage-overview";

export function CourtOverviewPage() {
  const courts = useCourtDirectory();
  const { date: businessDate, start, end } = beijingDayRange();
  const usageWindowStart = new Date(start.getTime() + 8 * 60 * 60 * 1000);
  const schedule = useQuery({
    queryKey: ["court-overview", businessDate],
    queryFn: () =>
      api<ScheduleItem[]>(
        `/schedule?from_=${encodeURIComponent(start.toISOString())}&to=${encodeURIComponent(end.toISOString())}`,
      ),
  });

  return (
    <section>
      <PageHeader
        eyebrow="Court overview"
        title="全部场地概览"
        description="集中查看今日所有启用场地的资源使用情况"
        actions={
          <Link className="btn" to="/schedule">
            <CalendarCheck2 size={15} />
            查看统一排期
          </Link>
        }
      />
      <Panel title={businessDate} description="今日场地使用情况">
        <CourtUsageOverview
          courts={courts.data ?? []}
          expanded
          schedule={schedule.data ?? []}
          windowEnd={end}
          windowStart={usageWindowStart}
        />
      </Panel>
    </section>
  );
}
