import { CalendarPlus, MapPinPlus, Trophy, UserRoundPlus, X } from "lucide-react";

import { useEffect, useState } from "react";

import type { CourtItem, ScheduleSelection } from "./court-schedule-grid";

export type ScheduleCreationAction = "schedule" | "private_lesson" | "venue_booking" | "event";

const actions = [
  {
    type: "schedule" as const,
    title: "新建排期",
    description: "创建临时安排或场地停用",
    icon: CalendarPlus,
  },
  {
    type: "private_lesson" as const,
    title: "预约私教",
    description: "填写学员、教练和结算方式",
    icon: UserRoundPlus,
  },
  {
    type: "venue_booking" as const,
    title: "新建订场",
    description: "为散客报价并创建场地预订",
    icon: MapPinPlus,
  },
  {
    type: "event" as const,
    title: "创建活动",
    description: "创建体验课、集训、比赛或包场",
    icon: Trophy,
  },
];

export function ScheduleSelectionActions({
  courts,
  selection,
  onChoose,
  onCancel,
}: {
  courts: CourtItem[];
  selection: ScheduleSelection;
  onChoose: (action: ScheduleCreationAction, courtIds: string[]) => void;
  onCancel: () => void;
}) {
  const [courtIds, setCourtIds] = useState(selection.court_ids);
  const activeCourts = courts.filter((court) => court.is_active !== false);

  useEffect(() => setCourtIds(selection.court_ids), [selection]);

  const toggleCourt = (courtId: string) => {
    setCourtIds((current) =>
      current.includes(courtId) ? current.filter((id) => id !== courtId) : [...current, courtId],
    );
  };

  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-slate-950/30 p-6">
      <section
        aria-labelledby="selection-title"
        aria-modal="true"
        className="w-full max-w-2xl rounded-lg border border-slate-200 bg-white p-5 shadow-2xl"
        role="dialog"
      >
        <header className="flex items-start justify-between">
          <div>
            <h2 className="m-0 text-base font-semibold text-slate-800" id="selection-title">
              用所选场地时段创建
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              已选 {courtIds.length} 片场地 · {selection.starts_at.replace("T", " ")} 至{" "}
              {selection.ends_at.replace("T", " ")}
            </p>
          </div>
          <button
            aria-label="继续选择场地"
            className="icon-btn"
            onClick={onCancel}
            title="继续选择场地"
            type="button"
          >
            <X size={15} />
          </button>
        </header>
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold text-slate-600">选择场地</p>
          <div className="flex flex-wrap gap-2">
            {activeCourts.map((court) => (
              <button
                aria-pressed={courtIds.includes(court.id)}
                className={`rounded-md border px-3 py-2 text-xs font-medium ${courtIds.includes(court.id) ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-600 hover:border-emerald-300"}`}
                key={court.id}
                onClick={() => toggleCourt(court.id)}
                type="button"
              >
                {court.name}
              </button>
            ))}
          </div>
        </div>
        {!courtIds.length && (
          <p className="mt-3 text-xs font-medium text-red-600" role="alert">
            请至少选择一片场地
          </p>
        )}
        <div className="mt-5 grid grid-cols-2 gap-3">
          {actions.map(({ type, title, description, icon: Icon }) => (
            <button
              className="flex items-start gap-3 rounded-md border border-slate-200 p-4 text-left hover:border-emerald-300 hover:bg-emerald-50/50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!courtIds.length}
              key={type}
              onClick={() => onChoose(type, courtIds)}
              type="button"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-emerald-50 text-emerald-700">
                <Icon size={17} />
              </span>
              <span>
                <strong className="block text-sm text-slate-800">{title}</strong>
                <small className="mt-1 block text-xs leading-5 text-slate-500">{description}</small>
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
