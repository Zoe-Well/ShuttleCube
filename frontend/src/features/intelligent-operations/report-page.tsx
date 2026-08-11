import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, Bot, CalendarDays, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import {
  generateOperationsReport,
  retryOperationsReportNarrative,
  type ReportMetric,
  useOperationRun,
  useOperationsReport,
  useOperationsReports,
} from "./api";

const labels: Record<string, string> = {
  cash_income: "实际收款",
  cash_refunds: "实际退款",
  operating_expense: "经营支出",
  cash_profit: "现金收付结余",
  outstanding_as_of: "截止时点待收",
  outstanding_receivables_as_of: "截止时点待收笔数",
  coach_fee_earned: "期间教练费",
  coach_fee_pending: "期间产生且当前待结教练费",
  coach_fee_settled: "实际结算教练费",
  coach_fee_current_pending_as_of: "截止时点全部待结教练费",
  coach_fee_current_pending_count_as_of: "截止时点待结费用笔数",
  coach_fee_items_earned: "期间教练费用明细数",
  coach_fee_items_pending: "期间产生且当前待结明细数",
  payroll_settlements: "期间工资结算单数",
  enrollments_created: "新增报名",
  attendance_records: "考勤记录",
  attendance_finalized_sessions: "已完成考勤课程",
  attendance_overdue_sessions: "逾期未考勤课程",
  attendance_present: "出勤",
  attendance_leave: "请假",
  attendance_absent: "缺勤",
  attendance_unprocessed: "未处理考勤",
  lesson_units_consumed: "消耗课时",
  fixed_class_lesson_units_consumed: "固定班消耗课时",
  private_lesson_units_consumed: "私教消耗课时",
  class_sessions_scheduled: "待完成固定班课程",
  class_sessions_completed: "完成课程",
  class_sessions_cancelled: "取消课程",
  private_lessons_booked: "待完成私教",
  private_lessons_completed: "完成私教",
  private_lessons_cancelled: "取消私教",
  venue_bookings_booked: "待确认订场",
  venue_bookings_confirmed: "已确认订场",
  venue_bookings_completed: "完成订场",
  venue_bookings_cancelled: "取消订场",
  temporary_events_confirmed: "待完成活动",
  temporary_events_completed: "完成活动",
  temporary_events_cancelled: "取消活动",
  business_cancellation_rate: "全部业务取消率",
  class_session_cancellation_rate: "固定班课程取消率",
  court_base_business_hours: "基础营业场地小时",
  court_block_unavailable_hours: "不可售场地小时",
  court_available_hours: "可售场地小时",
  court_commercial_usage_hours: "经营占用小时",
  court_outside_business_hours: "营业时间外经营占用",
  court_raw_utilization: "原始利用率",
  court_display_utilization: "展示利用率",
};

const metricGroups = [
  { title: "资金与时点余额", keys: ["cash_income", "cash_refunds", "operating_expense", "cash_profit", "outstanding_as_of", "outstanding_receivables_as_of"] },
  { title: "业务数量与取消", keys: ["enrollments_created", "class_sessions_scheduled", "class_sessions_completed", "class_sessions_cancelled", "private_lessons_booked", "private_lessons_completed", "private_lessons_cancelled", "venue_bookings_booked", "venue_bookings_confirmed", "venue_bookings_completed", "venue_bookings_cancelled", "temporary_events_confirmed", "temporary_events_completed", "temporary_events_cancelled", "business_cancellation_rate", "class_session_cancellation_rate"] },
  { title: "考勤与课时", keys: ["attendance_records", "attendance_finalized_sessions", "attendance_overdue_sessions", "attendance_present", "attendance_leave", "attendance_absent", "attendance_unprocessed", "lesson_units_consumed", "fixed_class_lesson_units_consumed", "private_lesson_units_consumed"] },
  { title: "教练费用与结算", keys: ["coach_fee_earned", "coach_fee_pending", "coach_fee_settled", "coach_fee_current_pending_as_of", "coach_fee_current_pending_count_as_of", "coach_fee_items_earned", "coach_fee_items_pending", "payroll_settlements"] },
  { title: "场地容量与利用", keys: ["court_base_business_hours", "court_block_unavailable_hours", "court_available_hours", "court_commercial_usage_hours", "court_outside_business_hours", "court_raw_utilization", "court_display_utilization"] },
] as const;

const dataStatusLabels: Record<string, string> = {
  partial: "部分数据",
  insufficient: "数据不足",
  data_quality_issue: "存在数据质量提示",
};

const anomalyLabels: Record<string, string> = {
  income_decline: "收入较对比期下降",
  refund_ratio_high: "退款比例偏高",
  refund_without_period_income: "本期无收入但发生退款",
  cash_profit_negative: "现金收付结余为负",
  expense_growth: "支出较对比期增长",
  outstanding_high: "当前待收金额偏高",
  business_cancellation_rate_high: "业务取消率偏高",
  attendance_overdue: "存在逾期未考勤课程",
  court_utilization_low: "场地利用率偏低",
  coach_fee_pending_high: "当前待结教练费偏高",
};

function formatMetric(metric: ReportMetric) {
  const value = Number(metric.value);
  if (metric.unit === "cny") return `¥${value.toLocaleString("zh-CN", { minimumFractionDigits: metric.display_precision, maximumFractionDigits: metric.display_precision })}`;
  if (metric.unit === "ratio") return `${(value * 100).toFixed(metric.display_precision)}%`;
  if (metric.unit === "hour") return `${value.toFixed(metric.display_precision)} 小时`;
  if (metric.unit === "lesson_unit") return `${value.toFixed(metric.display_precision)} 课时`;
  return value.toFixed(metric.display_precision);
}

export function IntelligentOperationsReportPage() {
  const client = useQueryClient();
  const today = new Date().toISOString().slice(0, 10);
  const [periodType, setPeriodType] = useState<"day" | "week" | "month">("month");
  const [anchorDate, setAnchorDate] = useState(today);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const reports = useOperationsReports(periodType);
  const effectiveSelectedId = selectedId ?? reports.data?.items[0]?.id ?? null;
  const report = useOperationsReport(effectiveSelectedId);
  const run = useOperationRun(runId);
  const generate = useMutation({
    mutationFn: () =>
      generateOperationsReport({
        period_type: periodType,
        anchor_date: anchorDate,
        include_narrative: true,
      }),
    onSuccess: (result) => setRunId(result.run_id),
  });
  const retryNarrative = useMutation({
    mutationFn: () => retryOperationsReportNarrative(report.data!.id),
    onSuccess: (result) => setRunId(result.run_id),
  });
  useEffect(() => {
    if (run.data?.state !== "succeeded") return;
    const value = run.data.checkpoint?.state?.snapshot_id;
    if (typeof value === "string") setSelectedId(value);
    void client.invalidateQueries({ queryKey: ["operations-reports"] });
    void client.invalidateQueries({ queryKey: ["operations-report-snapshot", value] });
  }, [client, run.data]);
  const metricMap = useMemo(
    () => new Map(report.data?.metrics.map((metric) => [metric.metric_key, metric]) ?? []),
    [report.data],
  );
  const headlineKeys = [
    "cash_income",
    "cash_profit",
    "outstanding_as_of",
    "court_display_utilization",
    "lesson_units_consumed",
    "class_sessions_cancelled",
  ];
  const visibleMetricGroups = metricGroups
    .map((group) => ({
      ...group,
      metrics: group.keys
        .map((key) => metricMap.get(key))
        .filter((metric): metric is ReportMetric => Boolean(metric)),
    }))
    .filter((group) => group.metrics.length > 0);

  return (
    <div className="space-y-5">
      <header className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-emerald-700">Deterministic operations report</div>
            <h1 className="mt-1 text-2xl font-semibold">智能经营报告</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">金额、数量、课时、场地容量、利用率与异常命中全部由业务程序计算并保存为不可变快照；模型只生成可失败、可重试的解释和建议。</p>
          </div>
          <Link className="btn" to="/reports/legacy">查看旧报表对照</Link>
        </div>
      </header>

      <section className="panel p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs font-medium">周期
            <select className="field mt-1 block" value={periodType} onChange={(event) => { setPeriodType(event.target.value as typeof periodType); setSelectedId(null); }}>
              <option value="day">指定日</option><option value="week">自然周</option><option value="month">自然月</option>
            </select>
          </label>
          <label className="text-xs font-medium">周期内任意日期
            <input className="field mt-1 block" max={today} type="date" value={anchorDate} onChange={(event) => setAnchorDate(event.target.value)} />
          </label>
          <button className="btn btn-primary" disabled={generate.isPending} onClick={() => generate.mutate()}>
            <CalendarDays size={15} />{generate.isPending ? "正在创建…" : "生成报告快照"}
          </button>
          {runId ? <span className="text-xs text-slate-500">运行状态：{run.data?.state ?? "queued"}</span> : null}
        </div>
        {generate.error ? <p className="mt-3 text-sm text-red-600">{generate.error.message}</p> : null}
      </section>

      {reports.data?.items.length ? (
        <section className="panel p-4">
          <div className="flex gap-2 overflow-x-auto">
            {reports.data.items.map((item) => (
              <button className={`rounded-lg border px-3 py-2 text-left text-xs ${effectiveSelectedId === item.id ? "border-emerald-500 bg-emerald-50" : "bg-white"}`} key={item.id} onClick={() => setSelectedId(item.id)}>
                <div className="font-medium">{item.period_start} 至 {item.period_end}</div>
                <div className="mt-1 text-slate-500">{item.period_state === "in_progress" ? "进行中快照" : "已结束周期"} · {new Date(item.generated_at).toLocaleString()}</div>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {report.isPending && effectiveSelectedId ? <section className="panel p-8 text-sm text-slate-500">正在读取确定性快照…</section> : null}
      {report.error ? <section className="panel p-5 text-sm text-red-600">{report.error.message}</section> : null}
      {report.data ? (
        <>
          <section className="panel p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 font-semibold"><BarChart3 size={18} />{report.data.period_start} 至 {report.data.period_end}</h2>
                <p className="mt-1 text-xs text-slate-500">统计截止 {new Date(report.data.effective_end).toLocaleString()} · {report.data.period_state === "in_progress" ? "当前周期进行中，比较窗口按相同已过时长截取" : "完整周期"} · 对比数据{report.data.comparison_status === "available" ? "可用" : "不足"}</p>
              </div>
              <code className="text-[10px] text-slate-400">证据 {report.data.evidence_hash.slice(0, 16)}</code>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {headlineKeys.map((key) => metricMap.get(key)).filter((metric): metric is ReportMetric => Boolean(metric)).map((metric) => (
                <div className="rounded-xl border bg-white p-4" key={metric.metric_ref}>
                  <div className="text-xs text-slate-500">{labels[metric.metric_key] ?? metric.metric_key}</div>
                  <div className="mt-1 text-xl font-semibold">{formatMetric(metric)}</div>
                  {metric.data_status !== "complete" ? <div className="mt-1 text-xs text-amber-700">{dataStatusLabels[metric.data_status] ?? metric.data_status}</div> : null}
                </div>
              ))}
            </div>
          </section>

          <section className="panel p-5">
            <h2 className="font-semibold">完整确定性指标</h2>
            <p className="mt-1 text-xs text-slate-500">“期间”表示所选日、周或月内发生；“生成时点”表示报告生成当时的全场余额，两种口径不会混算。</p>
            <div className="mt-4 space-y-5">
              {visibleMetricGroups.map((group) => (
                <div key={group.title}>
                  <h3 className="text-sm font-medium text-slate-700">{group.title}</h3>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {group.metrics.map((metric) => (
                      <div className="rounded-lg border bg-white p-3" key={metric.metric_ref}>
                        <div className="flex items-center justify-between gap-2 text-xs text-slate-500"><span>{labels[metric.metric_key] ?? metric.metric_key}</span><span>{metric.scope === "as_of" ? "生成时点" : "期间"}</span></div>
                        <div className="mt-1 text-base font-semibold">{formatMetric(metric)}</div>
                        {metric.data_status !== "complete" ? <div className="mt-1 text-xs text-amber-700">{dataStatusLabels[metric.data_status] ?? metric.data_status}</div> : null}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {report.data.anomalies.length ? (
            <section className="panel p-5">
              <h2 className="flex items-center gap-2 font-semibold"><AlertTriangle className="text-amber-600" size={18} />确定性异常提示</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {report.data.anomalies.map((anomaly) => (
                  <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3" key={anomaly.anomaly_id}>
                    <div className="text-sm font-medium">{anomalyLabels[anomaly.rule_key] ?? anomaly.rule_key} · {anomaly.severity}</div>
                    <div className="mt-1 text-xs text-slate-600">指标：{anomaly.metric_refs.join("、")} · 数据充分性：{anomaly.data_sufficiency}</div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {report.data.breakdowns.court_capacity ? (
            <section className="panel overflow-hidden">
              <div className="p-5"><h2 className="font-semibold">场地容量与利用率</h2><p className="mt-1 text-xs text-slate-500">CourtBlock 从可售容量分母扣除，不计作经营使用；原始利用率保留数据质量信号，展示值最多显示 100%。</p></div>
              <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="p-3">场地</th><th>营业容量</th><th>不可售</th><th>可售</th><th>经营占用</th><th>利用率</th></tr></thead><tbody>
                {report.data.breakdowns.court_capacity.per_court.map((court) => <tr className="border-t" key={String(court.court_id)}><td className="p-3 font-medium">{String(court.court_name)}</td><td>{String(court.base_business_hours)}h</td><td>{String(court.court_block_unavailable_hours)}h</td><td>{String(court.available_hours)}h</td><td>{String(court.commercial_usage_hours)}h</td><td>{(Number(court.display_utilization) * 100).toFixed(2)}%</td></tr>)}
              </tbody></table></div>
            </section>
          ) : null}

          <section className="panel p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="flex items-center gap-2 font-semibold"><Bot size={18} />模型解释与运营建议</h2><p className="mt-1 text-xs text-slate-500">这一部分与确定性快照分离；失败或无权限不会影响上方数字和异常。</p></div>
              {report.data.narrative.state !== "available" ? <button className="btn" disabled={retryNarrative.isPending} onClick={() => retryNarrative.mutate()}><RefreshCw size={14} />重试解释</button> : null}
            </div>
            {report.data.narrative.summary ? <div className="mt-4 space-y-3 text-sm"><p>{report.data.narrative.summary}</p>{report.data.narrative.recommendations.map((item) => <div className="rounded-lg bg-emerald-50 p-3" key={item.text}><span className="mr-2 text-xs font-medium uppercase text-emerald-700">{item.priority}</span>{item.text}</div>)}</div> : <p className="mt-4 text-sm text-slate-500">当前没有可展示的模型解释。可能是模型未启用、生成失败，或当前角色无权查看其中引用的受限财务/工资指标。</p>}
            {retryNarrative.error ? <p className="mt-2 text-sm text-red-600">{retryNarrative.error.message}</p> : null}
          </section>

          {report.data.narrative.caveats.length ? <section className="panel p-5"><h2 className="font-semibold">口径与数据提示</h2><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-600">{report.data.narrative.caveats.map((item) => <li key={item.code}>{item.message}</li>)}</ul></section> : null}
        </>
      ) : null}
    </div>
  );
}
