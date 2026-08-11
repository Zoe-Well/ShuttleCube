import type { CourtItem } from "./court-schedule-grid";
import { courtForReference } from "./court-display";

function splitIds(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function courtLabel(court: CourtItem) {
  return court.code ? `${court.code} · ${court.name}` : court.name;
}

export function CourtFormField({
  courts,
  label = "场地",
  locked,
  onChange,
  value,
}: {
  courts: CourtItem[];
  label?: string;
  locked: boolean;
  onChange: (value: string) => void;
  value: string;
}) {
  const ids = splitIds(value);
  const activeCourts = courts.filter((court) => court.is_active !== false);
  const display = ids.map((id) => {
    const court = courtForReference(id, courts);
    return court ? courtLabel(court) : "未识别场地";
  }).join("、");

  if (locked) {
    return (
      <label className="field-label">
        {label} <span className="field-hint">已根据所选排期锁定</span>
        <input aria-label={label} className="field bg-slate-50 text-slate-600" readOnly value={display} />
      </label>
    );
  }

  return (
    <fieldset className="field-label">
      <legend>{label} <span className="field-hint">可多选</span></legend>
      <div className="mt-1 flex min-h-10 flex-wrap gap-2 rounded-md border border-slate-200 bg-white p-2" role="group" aria-label={label}>
        {activeCourts.map((court) => {
          const selected = ids.includes(court.id);
          return (
            <button
              aria-pressed={selected}
              className={`rounded border px-2.5 py-1 text-xs font-medium ${selected ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-600 hover:border-emerald-300"}`}
              key={court.id}
              onClick={() => onChange(
                selected ? ids.filter((id) => id !== court.id).join(",") : [...ids, court.id].join(","),
              )}
              type="button"
            >
              {courtLabel(court)}
            </button>
          );
        })}
        {!activeCourts.length && <span className="px-1 py-1 text-xs text-slate-400">暂无可用场地</span>}
      </div>
    </fieldset>
  );
}
