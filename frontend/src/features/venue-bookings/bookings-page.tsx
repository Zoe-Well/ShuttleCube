import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Filter, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "@/api/client";
import { BulkCancelBar } from "@/components/operations/bulk-cancel-bar";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { ReceivableDetail } from "@/features/finance/receivable-detail";
import type { ScheduleItem } from "@/features/schedule/schedule-calendar";
import { ScheduleCreationFlow } from "@/features/schedule/schedule-creation-flow";
import { CourtScheduleGrid, type ScheduleSelection } from "@/features/schedule/court-schedule-grid";
import { formatCourtNames, useCourtDirectory } from "@/features/schedule/court-display";
import type { ScheduleCreationAction } from "@/features/schedule/schedule-selection-actions";
import { ScheduleDetails } from "@/features/schedule/schedule-details";
import { useVenueHours } from "@/features/schedule/use-venue-hours";

type Booking = {
  id: string;
  schedule_entry_id: string;
  customer_id: string;
  customer_name: string;
  starts_at: string;
  ends_at: string;
  court_ids: string[];
  actual_receivable: number;
  receivable_id?: string | null;
  outstanding_amount?: number;
  payment_status: string;
  status: string;
};
function pad(value: number) {
  return String(value).padStart(2, "0");
}
function dateValue(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
function bookingDisplayStatus(item: Booking) {
  return ["booked", "confirmed"].includes(item.status)
    && new Date(item.ends_at).getTime() <= Date.now()
    ? "pending_completion"
    : item.status;
}

export function BookingsPage() {
  const client = useQueryClient();
  const [action, setAction] = useState<ScheduleCreationAction | null>(null);
  const [focusDate, setFocusDate] = useState(() => dateValue(new Date()));
  const [selection, setSelection] = useState<ScheduleSelection | null>(null);
  const [selected, setSelected] = useState<ScheduleItem | null>(null);
  const [selectedReceivable, setSelectedReceivable] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [recordFromDate, setRecordFromDate] = useState("");
  const [recordToDate, setRecordToDate] = useState("");
  const scheduleRange = useMemo(() => {
    const start = new Date(`${focusDate}T00:00:00`);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return { start, end };
  }, [focusDate]);
  const query = useQuery({
    queryKey: ["bookings", recordFromDate, recordToDate],
    queryFn: () => {
      const params = new URLSearchParams();
      if (recordFromDate) params.set("from_date", recordFromDate);
      if (recordToDate) params.set("to_date", recordToDate);
      const queryString = params.toString();
      return api<Booking[]>(`/venue-bookings${queryString ? `?${queryString}` : ""}`);
    },
  });
  const schedule = useQuery({
    queryKey: ["schedule", "court-bookings", focusDate],
    queryFn: () =>
      api<ScheduleItem[]>(
        `/schedule?from_=${encodeURIComponent(scheduleRange.start.toISOString())}&to=${encodeURIComponent(scheduleRange.end.toISOString())}`,
      ),
  });
  const courts = useCourtDirectory();
  const venue = useVenueHours();
  const completeBooking = useMutation({
    mutationFn: (id: string) => api(`/venue-bookings/${id}/complete`, { method: "POST" }),
    onSuccess: () => {
      setSelected(null);
      void client.invalidateQueries({ queryKey: ["bookings"] });
      void client.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
  const rows = query.data ?? [];
  const total = rows
    .filter((item) => item.status !== "cancelled")
    .reduce((sum, item) => sum + Number(item.actual_receivable), 0);
  const cancellableIds = rows
    .filter((item) => ["booked", "confirmed"].includes(bookingDisplayStatus(item)))
    .map((item) => item.id);
  const select = (item: Booking) =>
    setSelected({
      id: item.schedule_entry_id,
      source_id: item.id,
      source_type: "venue_booking",
      title: `${item.customer_name} · 散客订场`,
      starts_at: item.starts_at,
      ends_at: item.ends_at,
      status: bookingDisplayStatus(item),
      resources: item.court_ids.map((id) => ({ type: "court", id })),
    });

  return (
    <section>
      <PageHeader
        eyebrow="Court reservations"
        title="场地预订"
        description="管理散客、多片场地连续预订与价格确认"
      />
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="metric-card">
          <div className="metric-label">有效预订</div>
          <div className="metric-value">
            {rows.filter((item) => item.status !== "cancelled").length}
          </div>
          <div className="metric-footnote">当前全部有效记录</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">预订应收</div>
          <div className="metric-value">¥{total.toFixed(2)}</div>
          <div className="metric-footnote">按实际确认金额汇总</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">待收款</div>
          <div className="metric-value">
            {
              rows.filter((item) => item.payment_status !== "paid" && item.status !== "cancelled")
                .length
            }
          </div>
          <div className="metric-footnote">需要跟进的订场订单</div>
        </div>
      </div>
      <Panel className="mb-4">
        <div className="flex min-h-14 items-center justify-between gap-4 border-b border-slate-200 px-4 py-2">
          <div>
            <div className="text-xs font-semibold text-slate-700">场地排期表</div>
            <div className="mt-1 text-[11px] text-slate-400">
              拖动选择连续时段和场地，松开后选择创建类型
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
            排期日期
            <input
              aria-label="排期日期"
              className="field h-9 w-40"
              type="date"
              value={focusDate}
              onChange={(event) => {
                setFocusDate(event.target.value);
                setSelection(null);
              }}
            />
          </label>
        </div>
        <CourtScheduleGrid
          courts={courts.data ?? []}
          date={focusDate}
          items={schedule.data ?? []}
          onSelectionChange={setSelection}
          onItemSelect={setSelected}
          selection={selection}
          venue={venue.data}
        />
      </Panel>
      <Panel>
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
            <input className="field h-9 pl-8" placeholder="搜索预订或客户" />
          </div>
          <div className="flex items-center gap-2">
            <Filter className="text-slate-400" size={14} />
            <label className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
              开始日期
              <input
                aria-label="预定记录开始日期"
                className="field h-9 w-36"
                max={recordToDate || undefined}
                type="date"
                value={recordFromDate}
                onChange={(event) => setRecordFromDate(event.target.value)}
              />
            </label>
            <label className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
              结束日期
              <input
                aria-label="预定记录结束日期"
                className="field h-9 w-36"
                min={recordFromDate || undefined}
                type="date"
                value={recordToDate}
                onChange={(event) => setRecordToDate(event.target.value)}
              />
            </label>
            {(recordFromDate || recordToDate) && (
              <button
                className="btn"
                onClick={() => {
                  setRecordFromDate("");
                  setRecordToDate("");
                }}
                type="button"
              >
                清空日期
              </button>
            )}
            <BulkCancelBar
              endpoint="/venue-bookings/bulk-delete"
              ids={[...selectedIds]}
              onDone={() => {
                setSelectedIds(new Set());
                void client.invalidateQueries({ queryKey: ["bookings"] });
                void client.invalidateQueries({ queryKey: ["schedule"] });
              }}
            />
          </div>
        </div>
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-10">
                  <input
                    aria-label="全选有效预订"
                    type="checkbox"
                    checked={
                      cancellableIds.length > 0 && cancellableIds.every((id) => selectedIds.has(id))
                    }
                    onChange={(event) =>
                      setSelectedIds(event.target.checked ? new Set(cancellableIds) : new Set())
                    }
                  />
                </th>
                <th>预订时间</th>
                <th>客户</th>
                <th>场地</th>
                <th>实际应收</th>
                <th>收款</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      aria-label={`选择 ${item.customer_name}`}
                      disabled={!["booked", "confirmed"].includes(bookingDisplayStatus(item))}
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={(event) =>
                        setSelectedIds((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(item.id);
                          else next.delete(item.id);
                          return next;
                        })
                      }
                    />
                  </td>
                  <td>
                    <div className="table-primary">
                      {new Date(item.starts_at).toLocaleDateString("zh-CN")}
                    </div>
                    <div className="table-secondary">
                      {new Date(item.starts_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      –{" "}
                      {new Date(item.ends_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </td>
                  <td className="table-primary">{item.customer_name}</td>
                  <td>{formatCourtNames(item.court_ids, courts.data)}</td>
                  <td className="table-primary">¥{Number(item.actual_receivable).toFixed(2)}</td>
                  <td>
                    <StatusBadge status={item.payment_status} />
                  </td>
                  <td>
                    <StatusBadge status={bookingDisplayStatus(item)} />
                  </td>
                  <td>
                    <div className="flex gap-2">
                      {item.receivable_id ? <button className="text-xs font-semibold text-emerald-700" onClick={() => setSelectedReceivable(item.receivable_id ?? null)} type="button">收款/详情</button> : null}
                      <button
                        className="text-xs font-semibold text-slate-600"
                        onClick={() => select(item)}
                        type="button"
                      >
                        {bookingDisplayStatus(item) === "pending_completion" ? "确认完成" : "修改/删除"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title="暂无场地预订"
            description="请在上方场地排期表选择场地和时间后创建订场。"
          />
        )}
      </Panel>
      <ScheduleCreationFlow
        action={action}
        courts={courts.data ?? []}
        selection={selection}
        onActionChange={setAction}
        onSelectionChange={setSelection}
        onCreated={() => {
          void client.invalidateQueries({ queryKey: ["bookings"] });
          void client.invalidateQueries({ queryKey: ["schedule"] });
        }}
      />
      <Drawer
        open={selected !== null}
        title="订场详情"
        description="查看、修改或删除散客订场"
        onClose={() => setSelected(null)}
      >
        {selected && (
          <>
            <ScheduleDetails
              item={selected}
              onChanged={() => {
                setSelected(null);
                void client.invalidateQueries({ queryKey: ["bookings"] });
                void client.invalidateQueries({ queryKey: ["schedule"] });
              }}
            />
            {selected.status === "pending_completion" && selected.source_id && (
              <button
                className="btn btn-primary mt-4 w-full"
                disabled={completeBooking.isPending}
                onClick={() => completeBooking.mutate(selected.source_id!)}
                type="button"
              >
                确认场地预定已完成
              </button>
            )}
          </>
        )}
      </Drawer>
      <Drawer open={selectedReceivable !== null} title="订场收款" description="查看该笔订场的应收、收款和退款" onClose={() => setSelectedReceivable(null)}>
        {selectedReceivable ? <ReceivableDetail receivableId={selectedReceivable} onChanged={() => void client.invalidateQueries({ queryKey: ["bookings"] })} /> : null}
      </Drawer>
    </section>
  );
}
