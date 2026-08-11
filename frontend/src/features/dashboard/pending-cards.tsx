import { Link } from "react-router";

type EndingWithinDays = 7 | 15 | 30;
type PendingCounts = {
  attendance: number;
  receivables: number;
  ending_classes: number;
  coach_fees: number;
};

const cards = [
  { key: "attendance", label: "今日待考勤", to: "/attendance/today" },
  { key: "receivables", label: "待收款项", to: "/finance" },
  { key: "coach_fees", label: "待结教练", to: "/payroll" },
] as const;

export function PendingCards({
  counts,
  endingWithinDays,
  onEndingWithinDaysChange,
}: {
  counts: PendingCounts;
  endingWithinDays: EndingWithinDays;
  onEndingWithinDaysChange: (value: EndingWithinDays) => void;
}) {
  return (
    <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
      {cards.map((card) => (
        <Link
          className="panel p-4 transition hover:border-emerald-300"
          key={card.key}
          to={card.to}
        >
          <span className="text-xs text-slate-500">{card.label}</span>
          <b className="mt-2 block text-xl text-slate-800">{counts[card.key] ?? 0}</b>
          <span className="mt-1 block text-[10px] text-emerald-700">查看待办 →</span>
        </Link>
      ))}
      <div className="panel p-4">
        <Link
          className="block transition hover:text-emerald-700"
          to={`/classes?attention=ending&days=${endingWithinDays}`}
        >
          <span className="text-xs text-slate-500">即将结束班级</span>
          <b className="mt-2 block text-xl text-slate-800">{counts.ending_classes ?? 0}</b>
          <span className="mt-1 block text-[10px] text-emerald-700">查看待办 →</span>
        </Link>
        <div className="mt-2 flex gap-1" aria-label="即将结束班级统计范围">
          {([7, 15, 30] as const).map((days) => (
            <button
              aria-pressed={endingWithinDays === days}
              className={`rounded px-1.5 py-0.5 text-[10px] ${
                endingWithinDays === days
                  ? "bg-emerald-100 font-semibold text-emerald-800"
                  : "bg-slate-100 text-slate-500"
              }`}
              key={days}
              onClick={() => onEndingWithinDaysChange(days)}
              type="button"
            >
              {days}天
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
