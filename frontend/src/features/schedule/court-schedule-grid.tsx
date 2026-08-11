import { LockKeyhole } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ScheduleItem } from "./schedule-calendar";
import { canonicalCourtId } from "./court-display";
import { PastTimeSelectionDialog } from "./schedule-time-fields";
import {
  defaultVenueHours,
  isPastScheduleStart,
  type ScheduleWarningCode,
  type VenueHours,
} from "./schedule-time";

export type CourtItem = { id: string; code?: string; name: string; is_active?: boolean };
export type ScheduleSelection = {
  starts_at: string;
  ends_at: string;
  court_ids: string[];
  warning_acknowledgements?: ScheduleWarningCode[];
};
type Cell = { court: number; slot: number };
type SelectedRange = { courtIndices: number[]; slotStart: number; slotEnd: number };

const openingSlot = 8;
const slots = Array.from({ length: 24 - 8 }, (_, index) => openingSlot + index);

const scheduleTypes: Record<string, { label: string; cellClass: string; legendClass: string }> = {
  class_session: {
    label: "固定班",
    cellClass: "border-l-4 border-l-green-600 bg-green-100 text-green-900 hover:bg-green-200",
    legendClass: "border-green-300 bg-green-100 text-green-900",
  },
  private_lesson: {
    label: "私教",
    cellClass: "border-l-4 border-l-indigo-600 bg-indigo-100 text-indigo-950 hover:bg-indigo-200",
    legendClass: "border-indigo-300 bg-indigo-100 text-indigo-950",
  },
  venue_booking: {
    label: "订场",
    cellClass: "border-l-4 border-l-amber-600 bg-amber-100 text-amber-950 hover:bg-amber-200",
    legendClass: "border-amber-300 bg-amber-100 text-amber-950",
  },
  event: {
    label: "活动",
    cellClass: "border-l-4 border-l-rose-600 bg-rose-100 text-rose-950 hover:bg-rose-200",
    legendClass: "border-rose-300 bg-rose-100 text-rose-950",
  },
  manual: {
    label: "临时排期",
    cellClass: "border-l-4 border-l-cyan-600 bg-cyan-100 text-cyan-950 hover:bg-cyan-200",
    legendClass: "border-cyan-300 bg-cyan-100 text-cyan-950",
  },
  court_block: {
    label: "场地停用",
    cellClass: "bg-slate-200 text-slate-700 hover:bg-slate-300",
    legendClass: "border-slate-300 bg-slate-100 text-slate-600",
  },
};

const defaultScheduleType = {
  label: "其他占用",
  cellClass: "border-l-4 border-l-slate-500 bg-slate-100 text-slate-800 hover:bg-slate-200",
  legendClass: "border-slate-300 bg-slate-100 text-slate-700",
};

function pad(value: number) { return String(value).padStart(2, "0"); }
function slotLabel(slot: number) { return `${pad(slot)}:00-${pad(slot + 1)}:00`; }
function localValue(date: string, slot: number) {
  const value = new Date(`${date}T00:00:00`);
  value.setHours(slot);
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

export function CourtScheduleGrid({
  courts,
  date,
  items,
  onSelectionChange,
  selection,
  initialHour,
  onItemSelect,
  now = new Date(),
  venue = defaultVenueHours,
}: {
  courts: CourtItem[];
  date: string;
  items: ScheduleItem[];
  onSelectionChange: (selection: ScheduleSelection) => void;
  selection?: ScheduleSelection | null;
  initialHour?: number;
  onItemSelect?: (item: ScheduleItem) => void;
  now?: Date;
  venue?: VenueHours;
}) {
  const activeCourts = courts.filter((court) => court.is_active !== false);
  const [anchor, setAnchor] = useState<Cell | null>(null);
  const [hover, setHover] = useState<Cell | null>(null);
  const [selected, setSelected] = useState<SelectedRange | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingPastSelection, setPendingPastSelection] = useState<ScheduleSelection | null>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const weekday = new Date(`${date}T00:00:00`).getDay();
  const targetHour = initialHour ?? (weekday === 0 || weekday === 6 ? 8 : 14);

  useEffect(() => {
    if (scrollArea.current) {
      scrollArea.current.scrollTop = Math.max(0, (targetHour - 8) * 48 - 44);
    }
  }, [activeCourts.length, date, targetHour]);

  useEffect(() => {
    if (selection !== null) return;
    setAnchor(null);
    setHover(null);
    setSelected(null);
    setMessage(null);
  }, [selection]);

  const busy = useMemo(() => {
    const map = new Map<string, ScheduleItem>();
    for (const item of items) {
      if (item.status === "cancelled") continue;
      const starts = new Date(item.starts_at).getTime();
      const ends = new Date(item.ends_at).getTime();
      for (const resource of item.resources ?? []) {
        const type = resource.type ?? resource.resource_type;
        const id = resource.id ?? resource.resource_id;
        if (type !== "court" || !id) continue;
        const courtId = canonicalCourtId(id, courts);
        for (const slot of slots) {
          const slotStart = new Date(localValue(date, slot)).getTime();
          const slotEnd = new Date(localValue(date, slot + 1)).getTime();
          if (starts < slotEnd && ends > slotStart) map.set(`${courtId}:${slot}`, item);
        }
      }
    }
    return map;
  }, [courts, date, items]);

  const rangeFor = (from: Cell, to: Cell) => ({
    courtStart: Math.min(from.court, to.court),
    courtEnd: Math.max(from.court, to.court),
    slotStart: Math.min(from.slot, to.slot),
    slotEnd: Math.max(from.slot, to.slot),
  });
  const preview = anchor && hover ? rangeFor(anchor, hover) : null;
  const inRange = (court: number, slot: number) => preview
    ? court >= preview.courtStart && court <= preview.courtEnd && slot >= preview.slotStart && slot <= preview.slotEnd
    : selected?.courtIndices.includes(court) && slot >= selected.slotStart && slot <= selected.slotEnd;

  const publish = (range: SelectedRange) => {
    setSelected(range);
    const nextSelection = {
      starts_at: localValue(date, range.slotStart),
      ends_at: localValue(date, range.slotEnd + 1),
      court_ids: range.courtIndices.map((court) => activeCourts[court].id),
    };
    if (isPastScheduleStart(nextSelection.starts_at, venue, now)) {
      setPendingPastSelection(nextSelection);
      return;
    }
    onSelectionChange(nextSelection);
  };

  const finish = (cell: Cell) => {
    if (!anchor) return;
    const range = rangeFor(anchor, cell);
    const clickedOneCell = anchor.court === cell.court && anchor.slot === cell.slot;
    setAnchor(null);
    setHover(null);
    if (clickedOneCell && selected && cell.slot >= selected.slotStart && cell.slot <= selected.slotEnd) {
      const courtIndices = new Set(selected.courtIndices);
      if (courtIndices.has(cell.court) && courtIndices.size > 1) courtIndices.delete(cell.court);
      else courtIndices.add(cell.court);
      for (let slot = selected.slotStart; slot <= selected.slotEnd; slot += 1) {
        if (busy.has(`${activeCourts[cell.court].id}:${slot}`)) {
          setMessage("该场地在所选连续时段内已有排期，请选择其他场地。");
          return;
        }
      }
      setMessage(null);
      publish({ ...selected, courtIndices: [...courtIndices].sort((a, b) => a - b) });
      return;
    }
    const courtIndices = Array.from({ length: range.courtEnd - range.courtStart + 1 }, (_, index) => range.courtStart + index);
    for (const court of courtIndices) {
      for (let slot = range.slotStart; slot <= range.slotEnd; slot += 1) {
        if (busy.has(`${activeCourts[court].id}:${slot}`)) {
          setMessage("选择范围内已有排期，请避开已占用的场地时段。");
          return;
        }
      }
    }
    setMessage(null);
    publish({ courtIndices, slotStart: range.slotStart, slotEnd: range.slotEnd });
  };

  if (!activeCourts.length) return <p className="p-5 text-sm text-slate-500">请先添加可用场地。</p>;

  return (
    <div className="court-schedule-grid">
      <div className="flex min-h-14 flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-3" aria-label="场地使用类型图例">
        {Object.entries(scheduleTypes).map(([type, style]) => (
          <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm ${style.legendClass}`} key={type}>
            {style.label}
          </span>
        ))}
      </div>
      <div className="max-h-[720px] overflow-auto select-none" data-testid="court-schedule-scroll" ref={scrollArea}>
        <div className="grid min-w-[720px]" style={{ gridTemplateColumns: `max-content repeat(${activeCourts.length}, minmax(140px, 1fr))` }}>
          <div className="sticky left-0 top-0 z-30 flex min-h-12 items-center justify-center border-b border-r border-slate-200 bg-slate-50 px-1 text-[11px] font-semibold text-slate-500">时间</div>
          {activeCourts.map((court) => <div className="sticky top-0 z-20 flex min-h-12 items-center justify-center border-b border-r border-slate-200 bg-slate-50 px-3 text-center text-xs font-semibold text-slate-600" key={court.id}>{court.name}<span className="ml-1.5 text-[10px] font-normal text-slate-400">{court.code}</span></div>)}
          {slots.flatMap((slot) => [
            <div className="sticky left-0 z-10 flex h-12 items-center justify-end border-b border-r border-slate-100 bg-white px-1 text-[11px] font-medium text-slate-400" key={`time-${slot}`}>{slotLabel(slot)}</div>,
            ...activeCourts.map((court, courtIndex) => {
              const item = busy.get(`${court.id}:${slot}`);
              const highlighted = Boolean(inRange(courtIndex, slot));
              const scheduleType = item ? (scheduleTypes[item.source_type] ?? defaultScheduleType) : null;
              const past = isPastScheduleStart(localValue(date, slot), venue, now);
              return <button
                aria-label={`${court.name} ${slotLabel(slot)}${item && scheduleType ? `，${scheduleType.label}，${item.title}` : ""}`}
                className={`relative h-12 border-b border-r border-slate-100 px-3 text-center text-xs transition-colors ${item && scheduleType ? `cursor-pointer font-bold shadow-[inset_0_1px_rgba(255,255,255,.38)] ${scheduleType.cellClass} ${past ? "grayscale-[.35] opacity-65" : ""}` : highlighted ? "bg-emerald-100 font-semibold text-emerald-800 ring-1 ring-inset ring-emerald-400" : past ? "bg-slate-100 text-slate-400 hover:bg-slate-200" : "bg-white text-slate-700 hover:bg-emerald-50"}`}
                data-testid={`court-cell-${court.id}-${slot}`}
                key={`${court.id}-${slot}`}
                onClick={() => { if (item) onItemSelect?.(item); }}
                onMouseDown={(event) => { event.preventDefault(); if (!item) { setAnchor({ court: courtIndex, slot }); setHover({ court: courtIndex, slot }); } }}
                onMouseEnter={() => { if (anchor) setHover({ court: courtIndex, slot }); }}
                onMouseUp={() => finish({ court: courtIndex, slot })}
                type="button"
                title={item && scheduleType ? `${scheduleType.label} · ${item.title} · ${court.name}` : undefined}
              >
                {past && <LockKeyhole aria-hidden="true" className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-55" size={11} />}
                <span className="block truncate leading-5">{item?.title ?? ""}</span>
                {item && <span className="block truncate text-[10px] font-medium opacity-75">{court.name}</span>}
              </button>;
            }),
          ])}
        </div>
      </div>
      <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 text-[11px] leading-5 text-slate-500">拖动可连续选择一小时时段；关闭创建选项后，单击同一时段的其他场地可追加或取消选择。</div>
      {message && <div className="border-t border-red-100 bg-red-50 px-4 py-3 text-xs font-medium text-red-700" role="alert">{message}</div>}
      {pendingPastSelection && (
        <PastTimeSelectionDialog
          onCancel={() => {
            setPendingPastSelection(null);
            setSelected(null);
          }}
          onConfirm={() => {
            onSelectionChange({
              ...pendingPastSelection,
              warning_acknowledgements: ["past_time"],
            });
            setPendingPastSelection(null);
          }}
        />
      )}
    </div>
  );
}
