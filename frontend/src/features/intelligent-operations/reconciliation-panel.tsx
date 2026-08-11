import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, Bot, CheckCircle2, ExternalLink, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import {
  analyzeOperationCase,
  type OperationCase,
  startOperationsScan,
  useOperationRun,
  useReconciliationContext,
} from "./api";

type Explanation = {
  summary?: string;
  hypotheses?: string[];
  repair_order?: string[];
  abstained?: boolean;
  abstention_reason?: string | null;
};

export function ReconciliationPanel({ item }: { item: OperationCase }) {
  const client = useQueryClient();
  const context = useReconciliationContext(
    item.case_type === "reconciliation_failure" ? item.id : undefined,
  );
  const [analysisRunId, setAnalysisRunId] = useState<string | null>(null);
  const [scanRunId, setScanRunId] = useState<string | null>(null);
  const analysisRun = useOperationRun(analysisRunId);
  const scanRun = useOperationRun(scanRunId);
  const analyze = useMutation({
    mutationFn: () => analyzeOperationCase(item.id),
    onSuccess: (result) => setAnalysisRunId(result.run_id),
  });
  const rerun = useMutation({
    mutationFn: () => startOperationsScan(["reconciliation.failed"]),
    onSuccess: (result) => setScanRunId(result.run_id),
  });
  const explanationValue = analysisRun.data?.checkpoint?.state?.explanation;
  const explanation = explanationValue && typeof explanationValue === "object"
    ? (explanationValue as Explanation)
    : null;
  const scanFinished = scanRun.data && ["succeeded", "failed", "escalated", "cancelled"].includes(scanRun.data.state);
  useEffect(() => {
    if (!scanFinished) return;
    void client.invalidateQueries({ queryKey: ["operation-case", item.id] });
    void client.invalidateQueries({ queryKey: ["operation-reconciliation-context", item.id] });
  }, [client, item.id, scanFinished]);

  if (item.case_type !== "reconciliation_failure") return null;
  if (context.isPending) {
    return <section className="panel p-5 text-sm text-slate-500">正在读取确定性对账结果…</section>;
  }
  if (context.error || !context.data) {
    return <section className="panel p-5 text-sm text-red-600">{context.error?.message ?? "对账结果不存在"}</section>;
  }
  const result = context.data.result;
  const impact = result.impact;
  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><AlertOctagon size={18} />数据一致性对账</h2>
          <p className="mt-1 text-xs text-slate-500">规则、结果和影响均由确定性程序计算；智能解释不会修改任何业务记录。</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${result.severity === "critical" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-800"}`}>
          {result.severity} · 连续发现 {context.data.failure_count} 次
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">规则</div><div className="mt-1 font-medium">{result.rule_key} v{result.rule_version}</div></div>
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">影响金额</div><div className="mt-1 font-medium">¥{impact.affected_amount}</div></div>
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">影响课时 / 排期</div><div className="mt-1 font-medium">{impact.affected_lesson_units} / {impact.affected_schedules}</div></div>
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">关联记录</div><div className="mt-1 font-medium">{impact.downstream_records}</div></div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b text-xs text-slate-500"><tr><th className="py-2 pr-3">不变量</th><th className="py-2 pr-3">预期</th><th className="py-2 pr-3">实际</th><th className="py-2">结果</th></tr></thead>
          <tbody>
            {result.invariants.map((invariant) => (
              <tr className="border-b last:border-0" key={invariant.key}>
                <td className="py-3 pr-3 font-medium">{invariant.key}</td>
                <td className="py-3 pr-3 text-xs text-slate-600">{invariant.expected}</td>
                <td className="py-3 pr-3 text-xs text-slate-600">{invariant.actual}</td>
                <td className="py-3">{invariant.passed ? <CheckCircle2 className="text-emerald-600" size={16} /> : <XCircle className="text-red-600" size={16} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {result.repair_entry_points.map((entry) => (
          <Link className="btn" key={`${entry.route}:${entry.label}`} to={entry.route}><ExternalLink size={14} />{entry.label}</Link>
        ))}
        <button className="btn" disabled={rerun.isPending} onClick={() => rerun.mutate()}>
          <RefreshCw className={rerun.isPending ? "animate-spin" : ""} size={14} />重新运行对账
        </button>
        <button className="btn" disabled={analyze.isPending} onClick={() => analyze.mutate()}>
          <Bot size={14} />生成只读解释
        </button>
      </div>
      <p className="mt-3 text-xs text-amber-700">MVP 不提供自动补账、同步应收、冲正费用、作废结算或修复排期工具。请从业务入口核对并按现有流程修复。</p>

      {scanRun.data ? <p className="mt-2 text-xs text-slate-500">对账运行：{scanRun.data.state}</p> : null}
      {analysisRun.data?.checkpoint?.state?.reason ? <p className="mt-2 text-xs text-slate-500">智能解释不可用：{String(analysisRun.data.checkpoint.state.reason)}</p> : null}
      {explanation ? (
        <div className="mt-4 rounded-xl border bg-white p-4">
          <h3 className="font-medium">智能解释（只读）</h3>
          <p className="mt-2 text-sm">{explanation.summary}</p>
          {explanation.hypotheses?.length ? <div className="mt-3"><div className="text-xs font-medium text-slate-500">待人工验证的假设</div><ul className="mt-1 list-disc space-y-1 pl-5 text-sm">{explanation.hypotheses.map((value) => <li key={value}>{value}</li>)}</ul></div> : null}
          {explanation.repair_order?.length ? <div className="mt-3"><div className="text-xs font-medium text-slate-500">建议核对顺序</div><ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">{explanation.repair_order.map((value) => <li key={value}>{value}</li>)}</ol></div> : null}
        </div>
      ) : null}
      {rerun.error ? <p className="mt-2 text-sm text-red-600">{rerun.error.message}</p> : null}
      {analyze.error ? <p className="mt-2 text-sm text-red-600">{analyze.error.message}</p> : null}
    </section>
  );
}
