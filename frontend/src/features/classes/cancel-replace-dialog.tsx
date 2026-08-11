import { useState } from "react";

import { api } from "@/api/client";

function localInput(value: string | number | Date) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

type Props = {
  sessionId: string;
  version: number;
  scheduledStart: string;
  scheduledEnd: string;
  mode?: "cancel" | "replacement";
  onDone: () => void;
};

export function CancelReplaceDialog({
  sessionId,
  version,
  scheduledStart,
  scheduledEnd,
  mode = "cancel",
  onDone,
}: Props) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [decision, setDecision] = useState<"pending" | "scheduled" | "waived">(
    mode === "replacement" ? "scheduled" : "pending",
  );
  const [startsAt, setStartsAt] = useState(
    localInput(new Date(scheduledStart).getTime() + 7 * 24 * 60 * 60 * 1000),
  );
  const duration = new Date(scheduledEnd).getTime() - new Date(scheduledStart).getTime();
  const [endsAt, setEndsAt] = useState(
    localInput(new Date(scheduledStart).getTime() + 7 * 24 * 60 * 60 * 1000 + duration),
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError("");
    try {
      if (mode === "replacement") {
        await api(`/class-sessions/${sessionId}/replacement`, {
          method: "POST",
          body: JSON.stringify({
            starts_at: new Date(startsAt).toISOString(),
            ends_at: new Date(endsAt).toISOString(),
            version,
          }),
        });
      } else {
        await api(`/class-sessions/${sessionId}/cancel-and-replace`, {
          method: "POST",
          body: JSON.stringify({
            reason,
            replacement_decision: decision,
            version,
            ...(decision === "scheduled"
              ? {
                  replacement_start: new Date(startsAt).toISOString(),
                  replacement_end: new Date(endsAt).toISOString(),
                }
              : {}),
          }),
        });
      }
      setOpen(false);
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        className={`text-xs font-semibold ${mode === "replacement" ? "text-amber-700" : "text-rose-600"}`}
        onClick={() => setOpen(true)}
        type="button"
      >
        {mode === "replacement" ? "安排整班补排" : "取消课程"}
      </button>
    );
  }

  return (
    <div className="grid min-w-72 gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {mode === "cancel" ? (
        <>
          <input
            className="field h-8"
            placeholder="填写取消原因"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <select
            className="field h-8"
            value={decision}
            onChange={(event) =>
              setDecision(event.target.value as "pending" | "scheduled" | "waived")
            }
          >
            <option value="pending">稍后安排整班补排</option>
            <option value="scheduled">立即安排整班补排</option>
            <option value="waived">无需整班补排</option>
          </select>
        </>
      ) : null}
      {(mode === "replacement" || decision === "scheduled") && (
        <div className="grid grid-cols-2 gap-2">
          <input
            className="field h-8"
            type="datetime-local"
            value={startsAt}
            onChange={(event) => setStartsAt(event.target.value)}
          />
          <input
            className="field h-8"
            type="datetime-local"
            value={endsAt}
            onChange={(event) => setEndsAt(event.target.value)}
          />
        </div>
      )}
      {error ? <p className="text-xs text-red-600">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <button className="btn min-h-8 px-2" onClick={() => setOpen(false)} type="button">
          返回
        </button>
        <button
          className="btn btn-danger min-h-8 px-2"
          disabled={saving || (mode === "cancel" && !reason.trim())}
          onClick={() => void submit()}
          type="button"
        >
          确认
        </button>
      </div>
    </div>
  );
}
