import { CalendarClock, Clock3, Layers3, MapPin } from "lucide-react";
import { StatusBadge } from "@/components/status/status-badge";
import { formatScheduleCourtNames, useCourtDirectory } from "./court-display";
import type { ScheduleItem } from "./schedule-calendar";
import { ScheduleRecordActions } from "./schedule-record-actions";

const sourceNames: Record<string, string> = {
  class_session: "固定班课程",
  fixed_class: "固定班课程",
  private_lesson: "私教课程",
  venue_booking: "场地预订",
  event: "临时活动",
  manual: "临时排期",
};

export function ScheduleDetails({ item, onChanged }: { item: ScheduleItem; onChanged?: () => void }) {
  const courts = useCourtDirectory();
  return (
    <div>
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="m-0 text-xs text-slate-500">排期名称</p>
            <h3 className="mb-0 mt-1 text-base font-semibold text-slate-800">{item.title}</h3>
          </div>
          <StatusBadge status={item.status} />
        </div>
      </div>
      <dl className="mt-6 grid gap-5">
        <div className="flex gap-3">
          <span className="grid size-8 place-items-center rounded-md bg-slate-100 text-slate-500">
            <Layers3 size={15} />
          </span>
          <div>
            <dt className="text-[11px] text-slate-400">业务类型</dt>
            <dd className="m-0 mt-1 text-sm font-medium text-slate-700">
              {sourceNames[item.source_type] ?? item.source_type}
            </dd>
          </div>
        </div>
        <div className="flex gap-3">
          <span className="grid size-8 place-items-center rounded-md bg-slate-100 text-slate-500">
            <CalendarClock size={15} />
          </span>
          <div>
            <dt className="text-[11px] text-slate-400">日期</dt>
            <dd className="m-0 mt-1 text-sm font-medium text-slate-700">
              {new Date(item.starts_at).toLocaleDateString("zh-CN", {
                year: "numeric",
                month: "long",
                day: "numeric",
                weekday: "long",
              })}
            </dd>
          </div>
        </div>
        <div className="flex gap-3">
          <span className="grid size-8 place-items-center rounded-md bg-slate-100 text-slate-500">
            <MapPin size={15} />
          </span>
          <div>
            <dt className="text-[11px] text-slate-400">使用场地</dt>
            <dd className="m-0 mt-1 text-sm font-medium text-slate-700">
              {formatScheduleCourtNames(item, courts.data)}
            </dd>
          </div>
        </div>
        <div className="flex gap-3">
          <span className="grid size-8 place-items-center rounded-md bg-slate-100 text-slate-500">
            <Clock3 size={15} />
          </span>
          <div>
            <dt className="text-[11px] text-slate-400">时间</dt>
            <dd className="m-0 mt-1 text-sm font-medium text-slate-700">
              {new Date(item.starts_at).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })}{" "}
              –{" "}
              {new Date(item.ends_at).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </dd>
          </div>
        </div>
      </dl>
      {onChanged && <ScheduleRecordActions item={item} onChanged={onChanged} />}
    </div>
  );
}
