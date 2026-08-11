import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "@/api/client";
import { BulkCancelBar } from "@/components/operations/bulk-cancel-bar";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { ReceivableDetail } from "@/features/finance/receivable-detail";
import type { ScheduleItem } from "@/features/schedule/schedule-calendar";
import { ScheduleDetails } from "@/features/schedule/schedule-details";
import { formatCourtNames, useCourtDirectory } from "@/features/schedule/court-display";

type Event = {
  id: string;
  schedule_entry_id: string;
  name: string;
  event_type: string;
  starts_at: string;
  ends_at: string;
  court_ids: string[];
  actual_receivable: number;
  finance?: { receivable_id: string; outstanding_amount: number; payment_status: string } | null;
  status: string;
};
const eventNames: Record<string, string> = {
  experience: "体验课",
  camp: "集训",
  competition: "赛事",
  exclusive: "包场",
};

export function EventsPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ScheduleItem | null>(null);
  const [selectedReceivable, setSelectedReceivable] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const courts = useCourtDirectory();
  const query = useQuery({ queryKey: ["events"], queryFn: () => api<Event[]>("/events") });
  const normalizedSearch = search.trim().toLowerCase();
  const rows = (query.data ?? []).filter((item) =>
    `${item.name} ${eventNames[item.event_type] ?? item.event_type}`
      .toLowerCase()
      .includes(normalizedSearch),
  );
  const cancellableIds = rows.filter((item) => item.status === "confirmed").map((item) => item.id);
  const select = (item: Event) =>
    setSelected({
      id: item.schedule_entry_id,
      source_id: item.id,
      source_type: "event",
      title: item.name,
      starts_at: item.starts_at,
      ends_at: item.ends_at,
      status: item.status,
      resources: item.court_ids.map((id) => ({ type: "court", id })),
    });

  return (
    <section>
      <PageHeader
        eyebrow="Event operations"
        title="临时活动"
        description="管理体验课、集训、比赛和包场等非周期业务"
        actions={
          <Link className="btn btn-primary" to="/schedule">
            <Plus size={15} />
            创建活动
          </Link>
        }
      />
      <Panel>
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-slate-200 px-4 py-2">
          <div className="relative w-64">
            <input
              className="field h-9 pr-8"
              placeholder="搜索活动"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
              size={14}
            />
          </div>
          <div className="flex items-center gap-3">
            <BulkCancelBar
              endpoint="/events/bulk-delete"
              ids={[...selectedIds]}
              onDone={() => {
                setSelectedIds(new Set());
                void client.invalidateQueries({ queryKey: ["events"] });
                void client.invalidateQueries({ queryKey: ["schedule"] });
              }}
            />
            <span className="text-xs text-slate-500">共 {rows.length} 个活动</span>
          </div>
        </div>
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-10">
                  <input
                    aria-label="全选可删除活动"
                    type="checkbox"
                    checked={
                      cancellableIds.length > 0 && cancellableIds.every((id) => selectedIds.has(id))
                    }
                    onChange={(event) =>
                      setSelectedIds(event.target.checked ? new Set(cancellableIds) : new Set())
                    }
                  />
                </th>
                <th>活动</th>
                <th>类型</th>
                <th>开始时间</th>
                <th>场地</th>
                <th>收费</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      aria-label={`选择 ${item.name}`}
                      disabled={item.status !== "confirmed"}
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
                  <td className="table-primary">{item.name}</td>
                  <td>{eventNames[item.event_type] ?? item.event_type}</td>
                  <td>
                    <div>{new Date(item.starts_at).toLocaleDateString("zh-CN")}</div>
                    <div className="table-secondary">
                      {new Date(item.starts_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </td>
                  <td>{formatCourtNames(item.court_ids, courts.data)}</td>
                  <td><div>¥{Number(item.actual_receivable).toFixed(2)}</div><StatusBadge status={item.finance?.payment_status ?? (item.actual_receivable > 0 ? "unpaid" : "paid")} label={item.actual_receivable === 0 ? "无需收款" : undefined} /></td>
                  <td>
                    <StatusBadge status={item.status} />
                  </td>
                  <td>
                    <div className="flex gap-2">
                      {item.finance?.receivable_id ? <button type="button" className="text-xs font-semibold text-emerald-700" onClick={() => setSelectedReceivable(item.finance?.receivable_id ?? null)}>收款/详情</button> : null}
                      <button
                        type="button"
                        className="text-xs font-semibold text-slate-600"
                        onClick={() => select(item)}
                      >
                        修改/删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title="暂无临时活动"
            description="请前往统一排期创建体验课、集训、比赛或包场活动。"
          />
        )}
      </Panel>
      <Drawer
        open={selected !== null}
        title="活动详情"
        description="查看、修改或删除临时活动"
        onClose={() => setSelected(null)}
      >
        {selected && (
          <ScheduleDetails
            item={selected}
            onChanged={() => {
              setSelected(null);
              void client.invalidateQueries({ queryKey: ["events"] });
              void client.invalidateQueries({ queryKey: ["schedule"] });
            }}
          />
        )}
      </Drawer>
      <Drawer open={selectedReceivable !== null} title="活动收款" description="查看该活动的应收、收款和退款" onClose={() => setSelectedReceivable(null)}>
        {selectedReceivable ? <ReceivableDetail receivableId={selectedReceivable} onChanged={() => void client.invalidateQueries({ queryKey: ["events"] })} /> : null}
      </Drawer>
    </section>
  );
}
