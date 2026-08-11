import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { api } from "@/api/client";
import {
  HourDateTimeField,
  type ConfirmedScheduleInput,
} from "./schedule-time-fields";
import { analyzeScheduleTime, toApiDateTime, type ScheduleWarningCode, type VenueHours } from "./schedule-time";
import { useScheduleTimeConfirmation } from "./use-schedule-time-confirmation";
import { ConflictAlert, type ScheduleConflict } from "./conflict-alert";
import { CourtFormField } from "./court-form-field";
import type { CourtItem } from "./court-schedule-grid";

export type ScheduleInput = {
  title: string;
  source_type: string;
  source_id: string;
  starts_at: string;
  ends_at: string;
  court_ids: string;
  coach_id?: string;
  student_id?: string;
  notes?: string;
};

type ConflictResult = {
  has_conflicts: boolean;
  conflicts: ScheduleConflict[];
  warnings?: { code: string; message: string }[];
};

function courtIds(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function payload(value: ConfirmedScheduleInput<ScheduleInput>) {
  return {
    ...value,
    starts_at: toApiDateTime(value.starts_at),
    ends_at: toApiDateTime(value.ends_at),
    resources: [
      ...courtIds(value.court_ids).map((id) => ({ type: "court", id })),
      ...(value.coach_id ? [{ type: "coach", id: value.coach_id }] : []),
      ...(value.student_id ? [{ type: "student", id: value.student_id }] : []),
    ],
    court_ids: undefined,
  };
}

export function ScheduleForm({
  onCreated,
  onCancel,
  initialValues,
  courts,
  venue,
  initialWarningAcknowledgements = [],
}: {
  onCreated: () => void;
  onCancel: () => void;
  initialValues?: Partial<ScheduleInput>;
  courts: CourtItem[];
  venue?: VenueHours;
  initialWarningAcknowledgements?: ScheduleWarningCode[];
}) {
  const { register, handleSubmit, getValues, setValue, watch } = useForm<ScheduleInput>({
    defaultValues: {
      source_type: "manual",
      source_id: crypto.randomUUID(),
      title: "临时排期",
      ...initialValues,
    },
  });
  const [conflicts, setConflicts] = useState<ScheduleConflict[] | null>(null);
  const [warnings, setWarnings] = useState<{ code: string; message: string }[]>([]);
  const selectedCourts = watch("court_ids") ?? "";
  const courtsLocked = Boolean(initialValues?.court_ids);

  const create = async (value: ConfirmedScheduleInput<ScheduleInput>) => {
    const body = payload(value);
    const result = await api<ConflictResult>("/schedule/conflicts:check", {
      method: "POST",
      body: JSON.stringify(body),
    });
    setConflicts(result.conflicts);
    setWarnings(result.warnings ?? []);
    if (result.has_conflicts) return;
    await api("/schedule", { method: "POST", body: JSON.stringify(body) });
    onCreated();
  };
  const time = useScheduleTimeConfirmation(create, venue, initialWarningAcknowledgements);
  const check = async () => {
    const value = getValues();
    const analysis = analyzeScheduleTime(value.starts_at, value.ends_at, venue);
    time.setError(analysis.error);
    if (analysis.error) return;
    const result = await api<ConflictResult>("/schedule/conflicts:check", {
      method: "POST",
      body: JSON.stringify(payload({
        ...value,
        warning_acknowledgements: initialWarningAcknowledgements,
      })),
    });
    setConflicts(result.conflicts);
    setWarnings(result.warnings ?? []);
  };

  return (
    <form className="grid gap-5" onSubmit={handleSubmit(time.submit)}>
      <div className="grid grid-cols-2 gap-4">
        <label className="field-label col-span-2">
          排期名称
          <input className="field" placeholder="例如：临时体验课" {...register("title", { required: true })} />
        </label>
        <label className="field-label">
          业务类型
          <select className="field" {...register("source_type")}>
            <option value="manual">临时排期</option>
            <option value="court_block">场地停用</option>
          </select>
        </label>
        <CourtFormField courts={courts} locked={courtsLocked} value={selectedCourts} onChange={(value) => setValue("court_ids", value, { shouldValidate: true })} />
        <input type="hidden" {...register("court_ids", { required: true })} />
        <HourDateTimeField label="开始时间" {...register("starts_at", { required: true })} />
        <HourDateTimeField label="结束时间" {...register("ends_at", { required: true })} />
        <label className="field-label">
          教练 <span className="field-hint">可选</span>
          <input className="field" placeholder="选择教练" {...register("coach_id")} />
        </label>
        <label className="field-label">
          学员 <span className="field-hint">可选</span>
          <input className="field" placeholder="搜索学员" {...register("student_id")} />
        </label>
        <label className="field-label col-span-2">
          备注
          <textarea className="field" placeholder="补充说明或特殊安排" {...register("notes")} />
        </label>
      </div>
      {time.feedback}
      {conflicts !== null && <ConflictAlert conflicts={conflicts} />}
      {warnings.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          {warnings.map((warning) => warning.message).join("；")}
        </div>
      )}
      <div className="rounded-md border border-emerald-100 bg-emerald-50/60 p-3 text-xs text-emerald-800">
        <ShieldCheck className="mr-2 inline" size={14} />保存前将检查场地、教练和学员的时间冲突。
      </div>
      <footer className="flex justify-end gap-2 border-t border-slate-200 pt-4">
        <button type="button" className="btn" onClick={onCancel}>取消</button>
        <button type="button" className="btn" onClick={() => void check()}>预检冲突</button>
        <button className="btn btn-primary">确认创建</button>
      </footer>
      {time.dialog}
    </form>
  );
}
