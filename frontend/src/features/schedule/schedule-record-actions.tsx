import { useState } from "react";
import { useForm } from "react-hook-form";

import { api } from "@/api/client";
import { HourDateTimeField } from "./schedule-time-fields";
import { toApiDateTime } from "./schedule-time";
import type { ScheduleItem } from "./schedule-calendar";
import { useScheduleTimeConfirmation } from "./use-schedule-time-confirmation";
import { useVenueHours } from "./use-venue-hours";

type EditInput = { starts_at: string; ends_at: string; court_ids: string };

function localDateTime(value: string) {
  const date = new Date(value);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function resource(item: ScheduleItem, type: string) {
  return (item.resources ?? [])
    .filter((entry) => (entry.type ?? entry.resource_type) === type)
    .map((entry) => entry.id ?? entry.resource_id)
    .filter((id): id is string => Boolean(id));
}

function endpoint(item: ScheduleItem, action: "reschedule" | "delete") {
  const base = item.source_type === "private_lesson"
    ? `/private-lessons/${item.source_id}`
    : item.source_type === "venue_booking"
      ? `/venue-bookings/${item.source_id}`
      : item.source_type === "event"
        ? `/events/${item.source_id}`
        : `/schedule/${item.id}`;
  return action === "delete" ? base : `${base}/reschedule`;
}

export function ScheduleRecordActions({
  item,
  onChanged,
}: {
  item: ScheduleItem;
  onChanged: () => void;
}) {
  const supported = ["manual", "court_block", "private_lesson", "venue_booking", "event"].includes(item.source_type);
  const [mode, setMode] = useState<"actions" | "edit" | "cancel">("actions");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const venue = useVenueHours();
  const courts = resource(item, "court");
  const coach = resource(item, "coach")[0];
  const { handleSubmit, register } = useForm<EditInput>({
    defaultValues: {
      starts_at: localDateTime(item.starts_at),
      ends_at: localDateTime(item.ends_at),
      court_ids: courts.join(","),
    },
  });

  const save = async (value: EditInput & { warning_acknowledgements: string[] }) => {
    const courtIds = value.court_ids.split(",").map((id) => id.trim()).filter(Boolean);
    setSaving(true);
    setError(null);
    try {
      const common = {
        starts_at: toApiDateTime(value.starts_at),
        ends_at: toApiDateTime(value.ends_at),
        warning_acknowledgements: value.warning_acknowledgements,
      };
      const body = item.source_type === "private_lesson"
        ? { ...common, court_ids: courtIds, coach_id: coach }
        : item.source_type === "venue_booking" || item.source_type === "event"
          ? { ...common, court_ids: courtIds }
          : {
              ...common,
              reason: "修改排期",
              source_type: item.source_type,
              source_id: item.source_id,
              title: item.title,
              resources: [
                ...courtIds.map((id) => ({ type: "court", id })),
                ...resource(item, "coach").map((id) => ({ type: "coach", id })),
                ...resource(item, "student").map((id) => ({ type: "student", id })),
              ],
            };
      await api(endpoint(item, "reschedule"), { method: "POST", body: JSON.stringify(body) });
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "修改失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };
  const time = useScheduleTimeConfirmation(save, venue.data);

  const cancel = async () => {
    if (!reason.trim()) {
      setError("请填写删除原因");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api(endpoint(item, "delete"), {
        method: "DELETE",
        body: JSON.stringify({ reason: reason.trim() }),
      });
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  if (
    !supported
    || item.status === "cancelled"
    || item.status === "completed"
    || item.status === "pending_completion"
  ) return null;

  if (mode === "edit") {
    return (
      <form className="mt-6 grid gap-4 border-t border-slate-200 pt-5" onSubmit={handleSubmit(time.submit)}>
        <h4 className="m-0 text-sm font-semibold text-slate-800">修改时间与场地</h4>
        <div className="grid grid-cols-2 gap-4">
          <HourDateTimeField label="开始时间" {...register("starts_at", { required: true })} />
          <HourDateTimeField label="结束时间" {...register("ends_at", { required: true })} />
          <label className="field-label col-span-2">
            场地
            <input className="field" {...register("court_ids", { required: true })} />
          </label>
        </div>
        {time.feedback}
        {error && <div className="rounded-md bg-red-50 p-3 text-xs font-medium text-red-700" role="alert">{error}</div>}
        <footer className="flex justify-end gap-2">
          <button className="btn" onClick={() => setMode("actions")} type="button">返回</button>
          <button className="btn btn-primary" disabled={saving}>保存修改</button>
        </footer>
        {time.dialog}
      </form>
    );
  }

  if (mode === "cancel") {
    return (
      <div className="mt-6 grid gap-3 border-t border-slate-200 pt-5">
        <h4 className="m-0 text-sm font-semibold text-slate-800">永久删除记录</h4>
        <p className="m-0 text-xs leading-5 text-red-600">删除后业务记录、排期和资源占用都会永久移除，无法恢复。</p>
        <textarea className="field" placeholder="请输入删除原因" value={reason} onChange={(event) => setReason(event.target.value)} />
        {error && <div className="rounded-md bg-red-50 p-3 text-xs font-medium text-red-700" role="alert">{error}</div>}
        <footer className="flex justify-end gap-2">
          <button className="btn" onClick={() => setMode("actions")} type="button">返回</button>
          <button className="btn btn-danger" disabled={saving} onClick={() => void cancel()} type="button">确认永久删除</button>
        </footer>
      </div>
    );
  }

  return (
    <div className="mt-6 flex justify-end gap-2 border-t border-slate-200 pt-5">
      <button className="btn" onClick={() => setMode("edit")} type="button">修改</button>
      <button className="btn btn-danger" onClick={() => setMode("cancel")} type="button">删除</button>
    </div>
  );
}
