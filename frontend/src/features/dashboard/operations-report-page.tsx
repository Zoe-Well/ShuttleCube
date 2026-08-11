import { useQuery } from "@tanstack/react-query";
import { BarChart3, CircleDollarSign, ReceiptText, WalletCards } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { MetricCard, PageHeader, Panel } from "@/components/operations/page";
import { OperationsCharts } from "./operations-charts";

type FixedClassFinance = {
  class_id: string;
  class_name: string;
  payment_amount: number;
  refund_amount: number;
  net_received: number;
  outstanding_amount: number;
};

type Report = {
  from: string;
  to: string;
  income: number;
  refunds: number;
  expense: number;
  profit: number;
  outstanding: number;
  coach_pending: number;
  coach_earned: number;
  current_coach_pending: number;
  coach_settled: number;
  income_by_source: Record<string, number>;
  income_by_class: Record<string, number>;
  fixed_class_finance: FixedClassFinance[];
  court_usage_hours: Record<string, number>;
  court_utilization: Record<string, number>;
  court_names: Record<string, string>;
};

export function OperationsReportPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [from, setFrom] = useState(`${today.slice(0, 8)}01`);
  const [to, setTo] = useState(today);
  const query = useQuery({
    queryKey: ["operations-report", from, to],
    queryFn: () => api<Report>(`/reports/operations?from=${from}&to=${to}`),
  });
  const report = query.data;
  return (
    <section>
      <PageHeader
        eyebrow="Operations analytics"
        title="经营报表"
        description="按实际资金收付核对收入、退款、支出、利润与场地利用"
      />
      <Panel className="mb-4">
        <div className="flex items-end gap-3 p-4">
          <label className="text-xs font-medium">
            开始日期
            <input
              className="field mt-1"
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label className="text-xs font-medium">
            结束日期
            <input
              className="field mt-1"
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
            />
          </label>
        </div>
      </Panel>
      {report && (
        <>
          <div className="mb-4 grid grid-cols-4 gap-3">
            <MetricCard
              label="实际收入"
              value={`¥${report.income.toFixed(2)}`}
              footnote="有效收款"
              icon={<CircleDollarSign size={16} />}
            />
            <MetricCard
              label="退款"
              value={`¥${report.refunds.toFixed(2)}`}
              footnote="实际现金流出"
              icon={<WalletCards size={16} />}
            />
            <MetricCard
              label="经营支出"
              value={`¥${report.expense.toFixed(2)}`}
              footnote="不重复计算退款"
              icon={<ReceiptText size={16} />}
            />
            <MetricCard
              label="收付利润"
              value={`¥${report.profit.toFixed(2)}`}
              footnote="收入－退款－支出"
              icon={<BarChart3 size={16} />}
            />
          </div>
          <OperationsCharts report={report} />
          <Panel
            className="mt-4"
            title="当前待处理"
            description="以下为当前余额，不随上方报表日期回溯"
          >
            <div className="grid grid-cols-2 gap-4 p-4 text-sm">
              <div>
                <span className="text-slate-400">当前业务待收款</span>
                <b className="mt-1 block">¥{report.outstanding.toFixed(2)}</b>
              </div>
              <div>
                <span className="text-slate-400">当前全部待结教练费</span>
                <b className="mt-1 block">¥{report.current_coach_pending.toFixed(2)}</b>
              </div>
            </div>
          </Panel>
          <Panel
            className="mt-4"
            title="期间教练费用"
            description="应付按授课发生日期统计，实际支付按结算付款日期统计"
          >
            <div className="grid grid-cols-3 gap-4 p-4 text-sm">
              <div>
                <span className="text-slate-400">期间授课产生的教练费</span>
                <b className="mt-1 block">¥{report.coach_earned.toFixed(2)}</b>
              </div>
              <div>
                <span className="text-slate-400">其中当前仍未结算</span>
                <b className="mt-1 block">¥{report.coach_pending.toFixed(2)}</b>
              </div>
              <div>
                <span className="text-slate-400">期间实际支付</span>
                <b className="mt-1 block">¥{report.coach_settled.toFixed(2)}</b>
              </div>
            </div>
          </Panel>
        </>
      )}
    </section>
  );
}
