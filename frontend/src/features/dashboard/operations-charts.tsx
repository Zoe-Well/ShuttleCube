type Report = {
  income: number;
  refunds: number;
  expense: number;
  profit: number;
  income_by_source: Record<string, number>;
  court_usage_hours: Record<string, number>;
  court_utilization: Record<string, number>;
  court_names: Record<string, string>;
};

const sourceNames: Record<string, string> = {
  enrollment: "固定班",
  private_package: "私教课包",
  private_lesson: "单次私教",
  venue_booking: "场地预订",
  event: "临时活动",
  other_income: "其他收入",
};

export function OperationsCharts({ report }: { report: Report }) {
  const maxIncome = Math.max(...Object.values(report.income_by_source), 1);
  return (
    <div className="grid grid-cols-2 gap-4">
      <section className="panel p-4">
        <h3 className="text-sm font-semibold">业务收入构成</h3>
        <div className="mt-4 grid gap-3">
          {Object.entries(report.income_by_source).map(([key, value]) => (
            <div key={key}>
              <div className="flex justify-between text-xs">
                <span>{sourceNames[key] ?? key}</span>
                <b>¥{Number(value).toFixed(2)}</b>
              </div>
              <div className="mt-1 h-2 rounded bg-slate-100">
                <div
                  className="h-2 rounded bg-emerald-500"
                  style={{ width: `${Math.max((Number(value) / maxIncome) * 100, 2)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="panel p-4">
        <h3 className="text-sm font-semibold">场地利用率</h3>
        <div className="mt-4 grid gap-3">
          {Object.entries(report.court_utilization).map(([key, value]) => (
            <div key={key}>
              <div className="flex justify-between text-xs">
                <span>{report.court_names[key] ?? "未知场地"}</span>
                <b>
                  {(Number(value) * 100).toFixed(1)}% ·{" "}
                  {Number(report.court_usage_hours[key] ?? 0).toFixed(1)} 小时
                </b>
              </div>
              <div className="mt-1 h-2 rounded bg-slate-100">
                <div
                  className="h-2 rounded bg-cyan-500"
                  style={{ width: `${Number(value) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
