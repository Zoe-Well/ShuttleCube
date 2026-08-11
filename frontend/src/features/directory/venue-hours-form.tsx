import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Clock3, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/api/client";

export type VenueSettings = {
  id: string;
  name: string;
  timezone: string;
  weekday_open_time: string;
  weekday_close_time: string;
  weekend_open_time: string;
  weekend_close_time: string;
  version: number;
};

type HoursDraft = Pick<
  VenueSettings,
  "weekday_open_time" | "weekday_close_time" | "weekend_open_time" | "weekend_close_time"
>;

const emptyDraft: HoursDraft = {
  weekday_open_time: "",
  weekday_close_time: "",
  weekend_open_time: "",
  weekend_close_time: "",
};

function inputTime(value: string) {
  return value.slice(0, 5);
}

function apiTime(value: string) {
  return value.length === 5 ? `${value}:00` : value;
}

export function VenueHoursForm({ value }: { value?: VenueSettings }) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<HoursDraft>(emptyDraft);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!value) return;
    setDraft({
      weekday_open_time: inputTime(value.weekday_open_time),
      weekday_close_time: inputTime(value.weekday_close_time),
      weekend_open_time: inputTime(value.weekend_open_time),
      weekend_close_time: inputTime(value.weekend_close_time),
    });
  }, [value]);

  const update = useMutation({
    mutationFn: async () => {
      if (!value) throw new Error("场馆设置尚未加载完成");
      return api<VenueSettings>("/venue/settings", {
        method: "PUT",
        body: JSON.stringify({
          name: value.name,
          timezone: value.timezone,
          weekday_open_time: apiTime(draft.weekday_open_time),
          weekday_close_time: apiTime(draft.weekday_close_time),
          weekend_open_time: apiTime(draft.weekend_open_time),
          weekend_close_time: apiTime(draft.weekend_close_time),
          version: value.version,
        }),
      });
    },
    onSuccess: (next) => {
      client.setQueryData(["venue-settings"], next);
      setError(null);
      setSaved(true);
    },
    onError: (caught) => {
      setSaved(false);
      setError(caught instanceof Error ? caught.message : "营业时间保存失败");
    },
  });

  const setTime = (key: keyof HoursDraft, next: string) => {
    setSaved(false);
    setError(null);
    setDraft((current) => ({ ...current, [key]: next }));
  };

  const submit = () => {
    if (draft.weekday_close_time <= draft.weekday_open_time) {
      setError("工作日关门时间必须晚于开门时间");
      return;
    }
    if (draft.weekend_close_time <= draft.weekend_open_time) {
      setError("周末关门时间必须晚于开门时间");
      return;
    }
    update.mutate();
  };

  return (
    <form className="mt-5" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <div className="grid grid-cols-2 gap-3">
        <section className="rounded-md border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
            <Clock3 size={14} />工作日营业
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="field-label">
              开门时间
              <input
                aria-label="工作日开门时间"
                className="field"
                required
                step="1800"
                type="time"
                value={draft.weekday_open_time}
                onChange={(event) => setTime("weekday_open_time", event.target.value)}
              />
            </label>
            <label className="field-label">
              关门时间
              <input
                aria-label="工作日关门时间"
                className="field"
                required
                step="1800"
                type="time"
                value={draft.weekday_close_time}
                onChange={(event) => setTime("weekday_close_time", event.target.value)}
              />
            </label>
          </div>
        </section>
        <section className="rounded-md border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
            <Clock3 size={14} />周末营业
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="field-label">
              开门时间
              <input
                aria-label="周末开门时间"
                className="field"
                required
                step="1800"
                type="time"
                value={draft.weekend_open_time}
                onChange={(event) => setTime("weekend_open_time", event.target.value)}
              />
            </label>
            <label className="field-label">
              关门时间
              <input
                aria-label="周末关门时间"
                className="field"
                required
                step="1800"
                type="time"
                value={draft.weekend_close_time}
                onChange={(event) => setTime("weekend_close_time", event.target.value)}
              />
            </label>
          </div>
        </section>
      </div>
      <p className="mb-0 mt-3 text-[11px] leading-5 text-slate-400">
        保存后，新的营业时间会立即用于排期提示和校验；已有排期不会自动变更。
      </p>
      {error && <div className="mt-3 rounded-md bg-red-50 p-3 text-xs font-medium text-red-700" role="alert">{error}</div>}
      {saved && <div className="mt-3 rounded-md bg-emerald-50 p-3 text-xs font-medium text-emerald-700" role="status">营业时间已保存</div>}
      <footer className="mt-4 flex justify-end border-t border-slate-100 pt-4">
        <button className="btn btn-primary" disabled={!value || update.isPending} type="submit">
          <Save size={14} />{update.isPending ? "保存中…" : "保存营业时间"}
        </button>
      </footer>
    </form>
  );
}
