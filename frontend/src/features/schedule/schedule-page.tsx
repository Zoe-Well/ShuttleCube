import { useQuery } from "@tanstack/react-query";
import { Filter, ListChecks, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "@/api/client";
import { BulkCancelBar } from "@/components/operations/bulk-cancel-bar";
import { Drawer } from "@/components/operations/drawer";
import { PageHeader, Panel } from "@/components/operations/page";
import { ScheduleCalendar, type ScheduleItem } from "./schedule-calendar";
import type { ScheduleSelection } from "./court-schedule-grid";
import { ScheduleCreationFlow } from "./schedule-creation-flow";
import { useCourtDirectory } from "./court-display";
import { ScheduleDetails } from "./schedule-details";
import { canBulkDeleteSchedule } from "./schedule-bulk";
import type { ScheduleCreationAction } from "./schedule-selection-actions";
import { useVenueHours } from "./use-venue-hours";
import { beijingDateKey } from "@/lib/beijing-time";

const filters = [
  { value: "all", label: "全部业务" },
  { value: "class_session", label: "固定班" },
  { value: "private_lesson", label: "私教" },
  { value: "venue_booking", label: "订场" },
  { value: "event", label: "活动" },
];
const legends = [
  { label: "固定班", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  { label: "私教", className: "border-indigo-200 bg-indigo-50 text-indigo-700" },
  { label: "订场", className: "border-amber-200 bg-amber-50 text-amber-700" },
  { label: "活动", className: "border-rose-200 bg-rose-50 text-rose-700" },
];
function pad(value: number) {
  return String(value).padStart(2, "0");
}
function dateValue(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function SchedulePage() {
  const [selected, setSelected] = useState<ScheduleItem | null>(null);
  const [selection, setSelection] = useState<ScheduleSelection | null>(null);
  const [action, setAction] = useState<ScheduleCreationAction | null>(null);
  const [batchMode, setBatchMode] = useState(false);
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [sourceType, setSourceType] = useState("all");
  const [weekStart, setWeekStart] = useState(() => beijingDateKey());
  const range = useMemo(() => {
    const start = new Date(`${weekStart}T00:00:00+08:00`);
    const end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);
    return { start, end };
  }, [weekStart]);
  const query = useQuery({
    queryKey: ["schedule", range.start.toISOString()],
    queryFn: () =>
      api<ScheduleItem[]>(
        `/schedule?from_=${encodeURIComponent(range.start.toISOString())}&to=${encodeURIComponent(range.end.toISOString())}`,
      ),
  });
  const courts = useCourtDirectory();
  const venue = useVenueHours();
  const items = (query.data ?? []).filter(
    (item) => sourceType === "all" || item.source_type === sourceType,
  );
  const bulkDeletableItems = items.filter(canBulkDeleteSchedule);
  const allBulkDeletableSelected =
    bulkDeletableItems.length > 0 && bulkDeletableItems.every((item) => selectedIds.has(item.id));
  const toggleBatchItem = (item: ScheduleItem) => {
    setBatchMessage(null);
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
  };
  return (
    <section>
      <PageHeader
        eyebrow="Resource planning"
        title="统一排期"
        description="在同一时间轴管理课程、私教、订场和活动资源"
        actions={
          <>
            <button className="btn" onClick={() => void query.refetch()}>
              <RefreshCw size={14} />
              刷新
            </button>
            <button
              className={
                batchMode ? "btn border-emerald-300 bg-emerald-50 text-emerald-800" : "btn"
              }
              onClick={() => {
                setBatchMode((current) => !current);
                setSelectedIds(new Set());
                setBatchMessage(null);
                setSelected(null);
                setSelection(null);
                setAction(null);
              }}
              type="button"
            >
              <ListChecks size={14} />
              {batchMode ? "退出批量管理" : "批量管理"}
            </button>
          </>
        }
      />
      <Panel>
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-slate-400" />
            <span className="text-xs font-semibold text-slate-600">周排期总览</span>
            <div className="ml-1 flex rounded-md bg-slate-100 p-0.5">
              {filters.map((filter) => (
                <button
                  className={`rounded px-3 py-1.5 text-[11px] font-medium ${sourceType === filter.value ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                  key={filter.value}
                  onClick={() => {
                    setSourceType(filter.value);
                    setSelectedIds(new Set());
                    setBatchMessage(null);
                  }}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {legends.map((item) => (
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${item.className}`}
                key={item.label}
              >
                {item.label}
              </span>
            ))}
          </div>
        </div>
        <div className="border-b border-slate-100 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">
          {batchMode
            ? "批量管理中：点击可删除的排期进行多选；固定班课次、已完成记录和特殊占用不可选择"
            : "在空白区域拖动选择连续时段，随后选择场地和创建类型"}
        </div>
        {batchMode && (
          <div className="flex min-h-14 items-center justify-between gap-3 border-b border-slate-200 bg-emerald-50/50 px-4 py-2">
            <div className="text-xs text-slate-600" role="status">
              {batchMessage ?? `当前筛选中有 ${bulkDeletableItems.length} 条可批量删除排期`}
            </div>
            <div className="flex items-center gap-2">
              <button
                className="btn"
                disabled={!bulkDeletableItems.length}
                onClick={() =>
                  setSelectedIds(
                    allBulkDeletableSelected
                      ? new Set()
                      : new Set(bulkDeletableItems.map((item) => item.id)),
                  )
                }
                type="button"
              >
                {allBulkDeletableSelected ? "取消全选" : "全选当前筛选"}
              </button>
              <BulkCancelBar
                endpoint="/schedule/bulk-delete"
                ids={[...selectedIds]}
                onDone={() => {
                  setSelectedIds(new Set());
                  setBatchMessage("所选排期已永久删除");
                  void query.refetch();
                }}
              />
            </div>
          </div>
        )}
        <div className="p-4">
          <ScheduleCalendar
            batchMode={batchMode}
            items={items}
            courts={courts.data}
            selectedIds={selectedIds}
            onBatchBlocked={(item, reason) => setBatchMessage(`${item.title}：${reason}`)}
            onBatchToggle={toggleBatchItem}
            onRangeChange={(start) => {
              const nextWeekStart = dateValue(start);
              if (nextWeekStart !== weekStart) {
                setWeekStart(nextWeekStart);
                setSelectedIds(new Set());
                setBatchMessage(null);
              }
            }}
            onSelect={setSelected}
            onTimeSelect={setSelection}
            venue={venue.data}
          />
        </div>
      </Panel>
      <ScheduleCreationFlow
        action={action}
        courts={courts.data ?? []}
        selection={selection}
        onActionChange={setAction}
        onSelectionChange={setSelection}
        onCreated={() => void query.refetch()}
      />
      <Drawer
        open={selected !== null}
        title="排期详情"
        description="查看资源占用与业务状态"
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
