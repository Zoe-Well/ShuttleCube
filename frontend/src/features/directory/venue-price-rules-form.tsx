import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDollarSign, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/api/client";
import type { VenueSettings } from "./venue-hours-form";

type PeriodType = "weekday_day" | "weekday_evening" | "weekend";
type PriceRule = {
  id: string;
  period_type: PeriodType;
  name: string;
  time_start: string;
  time_end: string;
  price_per_court_hour: number;
  version: number;
};
type PeriodDraft = {
  period_type: PeriodType;
  label: string;
  description: string;
  time_start: string;
  time_end: string;
  price: string;
};

const definitions: Record<PeriodType, Pick<PeriodDraft, "label" | "description">> = {
  weekday_day: { label: "工作日白天场", description: "适用于周一至周五的白天时段" },
  weekday_evening: { label: "工作日晚间场", description: "适用于周一至周五的晚间时段" },
  weekend: { label: "周末场", description: "适用于周六和周日" },
};

function inputTime(value: string) {
  return value.slice(0, 5);
}

function wholeHourRange(openValue: string, closeValue: string) {
  const [openHour, openMinute] = inputTime(openValue).split(":").map(Number);
  const [closeHour] = inputTime(closeValue).split(":").map(Number);
  const open = Math.min(22, openHour + (openMinute ? 1 : 0));
  const close = Math.max(open + 1, closeHour);
  return { open, close };
}

function hourValue(hour: number) {
  return `${String(hour).padStart(2, "0")}:00`;
}

function fallbackDrafts(venue?: VenueSettings): PeriodDraft[] {
  const weekday = wholeHourRange(
    venue?.weekday_open_time ?? "08:00",
    venue?.weekday_close_time ?? "22:00",
  );
  const weekend = wholeHourRange(
    venue?.weekend_open_time ?? "08:00",
    venue?.weekend_close_time ?? "22:00",
  );
  const split = Math.min(weekday.close - 1, Math.max(weekday.open + 1, 18));
  return [
    {
      period_type: "weekday_day",
      ...definitions.weekday_day,
      time_start: hourValue(weekday.open),
      time_end: hourValue(split),
      price: "",
    },
    {
      period_type: "weekday_evening",
      ...definitions.weekday_evening,
      time_start: hourValue(split),
      time_end: hourValue(weekday.close),
      price: "",
    },
    {
      period_type: "weekend",
      ...definitions.weekend,
      time_start: hourValue(weekend.open),
      time_end: hourValue(weekend.close),
      price: "",
    },
  ];
}

export function VenuePriceRulesForm({ venue }: { venue?: VenueSettings }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["venue-price-rules", "defaults"],
    queryFn: () => api<PriceRule[]>("/venue-price-rules/defaults"),
  });
  const fallback = useMemo(() => fallbackDrafts(venue), [venue]);
  const [drafts, setDrafts] = useState<PeriodDraft[]>(fallback);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const byType = new Map((query.data ?? []).map((rule) => [rule.period_type, rule]));
    setDrafts(fallback.map((draft) => {
      const rule = byType.get(draft.period_type);
      return rule ? {
        ...draft,
        time_start: inputTime(rule.time_start),
        time_end: inputTime(rule.time_end),
        price: String(Number(rule.price_per_court_hour)),
      } : draft;
    }));
  }, [fallback, query.data]);

  const save = useMutation({
    mutationFn: () => api<PriceRule[]>("/venue-price-rules/defaults", {
      method: "PUT",
      body: JSON.stringify({
        periods: drafts.map((draft) => ({
          period_type: draft.period_type,
          time_start: `${draft.time_start}:00`,
          time_end: `${draft.time_end}:00`,
          price_per_court_hour: Number(draft.price),
        })),
      }),
    }),
    onSuccess: (rules) => {
      client.setQueryData(["venue-price-rules", "defaults"], rules);
      setError(null);
      setSaved(true);
    },
    onError: (caught) => {
      setSaved(false);
      setError(caught instanceof Error ? caught.message : "默认价格保存失败");
    },
  });

  const update = (periodType: PeriodType, key: "time_start" | "time_end" | "price", value: string) => {
    setSaved(false);
    setError(null);
    setDrafts((current) => current.map((draft) =>
      draft.period_type === periodType ? { ...draft, [key]: value } : draft));
  };

  const submit = () => {
    if (drafts.some((draft) => !draft.time_start || !draft.time_end || !draft.price)) {
      setError("请完整填写三个时段和对应价格");
      return;
    }
    if (drafts.some((draft) => draft.time_end <= draft.time_start)) {
      setError("每个价格时段的结束时间必须晚于开始时间");
      return;
    }
    if (drafts.some((draft) => Number(draft.price) <= 0)) {
      setError("每小时价格必须大于 0");
      return;
    }
    const day = drafts.find((draft) => draft.period_type === "weekday_day");
    const evening = drafts.find((draft) => draft.period_type === "weekday_evening");
    if (day && evening && day.time_end > evening.time_start) {
      setError("工作日白天与晚间价格时段不能重叠");
      return;
    }
    save.mutate();
  };

  return (
    <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <div className="grid grid-cols-3 gap-3 p-5">
        {drafts.map((draft) => (
          <section className="rounded-md border border-slate-200 p-4" key={draft.period_type}>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
              <CircleDollarSign className="text-emerald-600" size={15} />
              {draft.label}
            </div>
            <p className="mb-3 mt-1 text-[11px] text-slate-400">{draft.description}</p>
            <div className="grid grid-cols-2 gap-3">
              <label className="field-label">
                开始时间
                <input aria-label={`${draft.label}开始时间`} className="field" step="3600" type="time" value={draft.time_start} onChange={(event) => update(draft.period_type, "time_start", event.target.value)} />
              </label>
              <label className="field-label">
                结束时间
                <input aria-label={`${draft.label}结束时间`} className="field" step="3600" type="time" value={draft.time_end} onChange={(event) => update(draft.period_type, "time_end", event.target.value)} />
              </label>
              <label className="field-label col-span-2">
                每片场地每小时价格
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">¥</span>
                  <input aria-label={`${draft.label}每小时价格`} className="field pl-7" min="0.01" placeholder="请输入默认价格" step="0.01" type="number" value={draft.price} onChange={(event) => update(draft.period_type, "price", event.target.value)} />
                </div>
              </label>
            </div>
          </section>
        ))}
      </div>
      <div className="border-t border-slate-100 px-5 py-4">
        <p className="m-0 text-[11px] leading-5 text-slate-400">
          订场跨越多个价格时段时，系统会逐小时累计，并按所选场地数量计算。
        </p>
        {error && <div className="mt-3 rounded-md bg-red-50 p-3 text-xs font-medium text-red-700" role="alert">{error}</div>}
        {saved && <div className="mt-3 rounded-md bg-emerald-50 p-3 text-xs font-medium text-emerald-700" role="status">默认场地价格已保存</div>}
        <footer className="mt-4 flex justify-end">
          <button className="btn btn-primary" disabled={query.isLoading || save.isPending} type="submit">
            <Save size={14} />{save.isPending ? "保存中…" : "保存默认价格"}
          </button>
        </footer>
      </div>
    </form>
  );
}
