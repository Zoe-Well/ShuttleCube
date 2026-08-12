import { type FormEvent, useState } from "react";

import { api } from "@/api/client";
import { beijingDateTimeInputToIso, toBeijingDateTimeInput } from "@/lib/beijing-time";

function localInput(value: string) {
  return toBeijingDateTimeInput(value);
}

export function SessionTimeEditor({
  session,
  onDone,
}: {
  session: { id: string; version: number; scheduled_start: string; scheduled_end: string };
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  if (!open) {
    return (
      <button className="text-xs font-semibold text-sky-700" onClick={() => setOpen(true)} type="button">
        修改时间
      </button>
    );
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError("");
    try {
      await api(`/class-sessions/${session.id}/reschedule`, {
        method: "POST",
        body: JSON.stringify({
          starts_at: beijingDateTimeInputToIso(String(data.get("starts_at"))),
          ends_at: beijingDateTimeInputToIso(String(data.get("ends_at"))),
          reason: String(data.get("reason")),
          version: session.version,
        }),
      });
      setOpen(false);
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "修改失败");
    }
  };
  return (
    <form className="grid min-w-72 gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-sm" onSubmit={(event) => void submit(event)}>
      <div className="grid grid-cols-2 gap-2">
        <input className="field h-8" defaultValue={localInput(session.scheduled_start)} name="starts_at" type="datetime-local" required />
        <input className="field h-8" defaultValue={localInput(session.scheduled_end)} name="ends_at" type="datetime-local" required />
      </div>
      <input className="field h-8" name="reason" placeholder="修改原因" required />
      {error ? <p className="text-xs text-red-600">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <button className="btn min-h-8 px-2" onClick={() => setOpen(false)} type="button">返回</button>
        <button className="btn btn-primary min-h-8 px-2">保存</button>
      </div>
    </form>
  );
}
