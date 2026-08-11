import { AlertTriangle, ClockAlert, LockKeyhole } from "lucide-react";
import type { InputHTMLAttributes } from "react";

import type { ScheduleTimeWarning } from "./schedule-time";

export type TimeBoundInput = { starts_at: string; ends_at: string };
export type ConfirmedScheduleInput<T> = T & { warning_acknowledgements: string[] };

export function HourDateTimeField({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="field-label">
      {label}
      <input className="field" type="datetime-local" step={3600} {...props} />
      <span className="field-hint">按整点选择，每次至少 1 小时</span>
    </label>
  );
}

export function TimeValidationAlert({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-700" role="alert">
      <AlertTriangle className="mr-2 inline" size={14} />
      {message}，请修改后再保存。
    </div>
  );
}

export function TimeWarningDialog({
  warnings,
  onCancel,
  onConfirm,
}: {
  warnings: ScheduleTimeWarning[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-slate-950/35 p-6" role="presentation">
      <section
        aria-labelledby="time-warning-title"
        aria-modal="true"
        className="w-full max-w-md rounded-lg border border-amber-200 bg-white p-5 shadow-2xl"
        role="dialog"
      >
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-amber-100 text-amber-700">
            <ClockAlert size={18} />
          </span>
          <div>
            <h2 className="m-0 text-sm font-semibold text-slate-800" id="time-warning-title">
              请确认排期时间
            </h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">以下情况不会阻止保存，但需要你明确确认：</p>
          </div>
        </div>
        <ul className="my-4 grid gap-2 pl-5 text-xs leading-5 text-amber-800">
          {warnings.map((warning) => (
            <li key={warning.code}>{warning.message}</li>
          ))}
        </ul>
        <footer className="flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button className="btn" onClick={onCancel} type="button">
            返回修改
          </button>
          <button className="btn btn-primary" onClick={onConfirm} type="button">
            仍然保存
          </button>
        </footer>
      </section>
    </div>
  );
}

export function PastTimeSelectionDialog({
  onCancel,
  onConfirm,
}: {
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-slate-950/35 p-6" role="presentation">
      <section
        aria-labelledby="past-time-selection-title"
        aria-modal="true"
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-2xl"
        role="dialog"
      >
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
            <LockKeyhole size={18} />
          </span>
          <div>
            <h2 className="m-0 text-sm font-semibold text-slate-800" id="past-time-selection-title">
              这是已经失效的场地时段
            </h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              该时间已经过去，需要补充场地预订信息吗？确认后可继续创建，本次操作不会再次提示。
            </p>
          </div>
        </div>
        <footer className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button className="btn" onClick={onCancel} type="button">
            取消
          </button>
          <button className="btn btn-primary" onClick={onConfirm} type="button">
            继续补录
          </button>
        </footer>
      </section>
    </div>
  );
}
