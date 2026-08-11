import { useQuery } from "@tanstack/react-query";
import {
  CalendarCheck2,
  ChevronRight,
  Clock3,
  GraduationCap,
  MapPin,
  Plus,
  UsersRound,
  WalletCards,
} from "lucide-react";
import { Link } from "react-router";
import { useState } from "react";

import { api } from "@/api/client";
import { EmptyState } from "@/components/operations/empty-state";
import { Drawer } from "@/components/operations/drawer";
import { MetricCard, PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { ScheduleDetails } from "@/features/schedule/schedule-details";
import { localDateKey } from "@/lib/utils";
import { PendingCards } from "./pending-cards";
import { CourtUsageOverview } from "./court-usage-overview";
import type { ScheduleItem } from "@/features/schedule/schedule-calendar";
import { formatScheduleCourtNames, useCourtDirectory } from "@/features/schedule/court-display";

type Schedule = ScheduleItem;
type DashboardData = {
  schedule: Schedule[];
  overview: {
    today_counts: Record<string, number>;
    pending_counts: {
      attendance: number;
      receivables: number;
      ending_classes: number;
      coach_fees: number;
    };
    ending_within_days: number;
    month_finance: {
      income: number;
      refunds: number;
      expense: number;
      profit: number;
      outstanding: number;
    };
  };
};

type EndingWithinDays = 7 | 15 | 30;

const sourceNames: Record<string, string> = {
  fixed_class: "固定班",
  class_session: "固定班",
  private_lesson: "私教",
  venue_booking: "订场",
  event: "活动",
  manual: "临时排期",
};

export function DashboardPage() {
  const [selected, setSelected] = useState<Schedule | null>(null);
  const [endingWithinDays, setEndingWithinDays] = useState<EndingWithinDays>(30);
  const courts = useCourtDirectory();
  const now = new Date();
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  const query = useQuery({
    queryKey: ["dashboard", localDateKey(start), endingWithinDays],
    queryFn: async (): Promise<DashboardData> => {
      const [schedule, overview] = await Promise.all([
        api<Schedule[]>(
          `/schedule?from_=${encodeURIComponent(start.toISOString())}&to=${encodeURIComponent(end.toISOString())}`,
        ),
        api<DashboardData["overview"]>(
          `/dashboard?business_date=${localDateKey(start)}&ending_within_days=${endingWithinDays}`,
        ),
      ]);
      return { schedule, overview };
    },
  });
  const data = query.data;
  const overview = data?.overview;
  const usageWindowStart = new Date(start);
  usageWindowStart.setHours(8, 0, 0, 0);
  return (
    <section>
      <PageHeader
        eyebrow="Operations overview"
        title="经营工作台"
        description="掌握今日课程、场地占用与需要处理的运营事项"
        actions={
          <>
            <Link className="btn" to="/schedule">
              <CalendarCheck2 size={15} />
              查看排期
            </Link>
            <Link className="btn btn-primary" to="/bookings">
              <Plus size={15} />
              快速订场
            </Link>
          </>
        }
      />
      <div className="grid grid-cols-4 gap-3">
        <MetricCard
          label="今日安排"
          value={String(data?.schedule.length ?? 0)}
          footnote="覆盖课程、私教、订场与活动"
          icon={<Clock3 size={16} />}
        />
        <MetricCard
          label="本月实际收入"
          value={`¥${Number(overview?.month_finance.income ?? 0).toFixed(2)}`}
          footnote="以有效收款为准"
          icon={<GraduationCap size={16} />}
        />
        <MetricCard
          label="当前待收款"
          value={`¥${Number(overview?.month_finance.outstanding ?? 0).toFixed(2)}`}
          footnote="全部未结清应收"
          icon={<UsersRound size={16} />}
        />
        <MetricCard
          label="本月收付利润"
          value={`¥${Number(overview?.month_finance.profit ?? 0).toFixed(2)}`}
          footnote="收款减退款和支出"
          icon={<WalletCards size={16} />}
        />
      </div>
      <PendingCards
        counts={
          overview?.pending_counts ?? {
            attendance: 0,
            receivables: 0,
            ending_classes: 0,
            coach_fees: 0,
          }
        }
        endingWithinDays={endingWithinDays}
        onEndingWithinDaysChange={setEndingWithinDays}
      />
      <div className="responsive-grid mt-4 grid grid-cols-[minmax(0,1.55fr)_minmax(320px,.75fr)] gap-4">
        <Panel
          title="今日运营时间轴"
          description="按开始时间排列的全部资源占用"
          actions={
            <span className="text-xs text-slate-500">{data?.schedule.length ?? 0} 项安排</span>
          }
        >
          {data?.schedule.length ? (
            <div
              className="max-h-[460px] divide-y divide-slate-100 overflow-y-auto px-4"
              data-testid="today-timeline-scroll"
            >
              {data.schedule.map((item, index) => (
                <button
                  className="grid w-full grid-cols-[70px_12px_1fr_auto] items-center gap-3 py-3 text-left hover:bg-slate-50"
                  key={item.id}
                  onClick={() => setSelected(item)}
                  type="button"
                >
                  <time className="text-xs font-semibold text-slate-600">
                    {new Date(item.starts_at).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                  <span
                    className={`size-2 rounded-full ${index === 0 ? "bg-emerald-500" : "bg-slate-300"}`}
                  />
                  <div>
                    <div className="text-[13px] font-semibold text-slate-700">{item.title}</div>
                    <div className="mt-0.5 text-[11px] text-slate-400">
                      {sourceNames[item.source_type] ?? item.source_type} · 至{" "}
                      {new Date(item.ends_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      · {formatScheduleCourtNames(item, courts.data)}
                    </div>
                  </div>
                  <StatusBadge status={item.status} />
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="今日暂无安排" description="从统一排期或场地预订创建第一项安排。" />
          )}
        </Panel>
        <div className="grid gap-4">
          <Panel
            title="场地概览"
            description="今日资源使用情况"
            actions={
              <Link
                className="flex items-center gap-1 text-xs font-semibold text-emerald-700"
                to="/courts/overview"
              >
                查看全部
                <ChevronRight size={13} />
              </Link>
            }
          >
            <CourtUsageOverview
              courts={courts.data ?? []}
              maxCourts={4}
              schedule={data?.schedule ?? []}
              windowEnd={end}
              windowStart={usageWindowStart}
            />
          </Panel>
          <Panel title="快捷入口">
            <div className="grid grid-cols-2 gap-px bg-slate-200">
              {[
                { to: "/classes", label: "新建固定班", icon: GraduationCap },
                { to: "/private-lessons", label: "预约私教", icon: UsersRound },
                { to: "/bookings", label: "散客订场", icon: MapPin },
                { to: "/events", label: "创建活动", icon: CalendarCheck2 },
              ].map(({ to, label, icon: Icon }) => (
                <Link
                  className="flex items-center gap-2 bg-white p-3 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  to={to}
                  key={to}
                >
                  <Icon size={14} className="text-slate-400" />
                  {label}
                </Link>
              ))}
            </div>
          </Panel>
        </div>
      </div>
      <Drawer
        open={selected !== null}
        title="运营安排详情"
        description="查看、修改或删除今日经营安排"
        onClose={() => setSelected(null)}
      >
        {selected && (
          <ScheduleDetails
            item={selected}
            onChanged={() => {
              setSelected(null);
              void query.refetch();
            }}
          />
        )}
      </Drawer>
    </section>
  );
}
