import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bot, CheckCircle2, History, RefreshCw, Settings2, UserRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { formatBeijingDateTime } from "@/lib/beijing-time";

import { hasOperationsCapability } from "./access-control";
import {
  startOperationsScan,
  useOperationCases,
  useOperationsBrief,
  useOperationsContext,
} from "./api";
import { caseStateLabel, severityLabel } from "./terminology";

const queueNames: Record<string, string> = {
  operations: "日常运营",
  training: "培训管理",
  revenue: "收入跟进",
  control: "数据核对",
};

const severityClass: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-sky-100 text-sky-700",
  info: "bg-slate-100 text-slate-600",
};

export function OperationsCenterPage() {
  const client = useQueryClient();
  const [view, setView] = useState<"active" | "history">("active");
  const [queue, setQueue] = useState<string>();
  const [historyState, setHistoryState] = useState<"all" | "resolved" | "dismissed">("all");
  const context = useOperationsContext();
  const cases = useOperationCases(view === "active"
    ? { queue }
    : { states: historyState === "all" ? ["resolved", "dismissed"] : [historyState] });
  const brief = useOperationsBrief();
  const scan = useMutation({
    mutationFn: startOperationsScan,
    onSuccess: () => {
      window.setTimeout(() => {
        void client.invalidateQueries({ queryKey: ["operations-cases"] });
        void client.invalidateQueries({ queryKey: ["operations-brief"] });
      }, 1200);
    },
  });

  if (context.isPending || cases.isPending || brief.isPending) {
    return <div className="panel p-8 text-sm text-slate-500">正在加载智能运营中心…</div>;
  }
  const error = context.error ?? cases.error ?? brief.error;
  if (error || !context.data) {
    return <div className="panel p-8 text-sm text-red-600">{error?.message ?? "运营范围不可用"}</div>;
  }

  const canScan = hasOperationsCapability(context.data, "operations.case.manage");
  const canManageSettings = ["operations.policy.manage", "operations.model.manage"]
    .some((capability) => hasOperationsCapability(context.data, capability));
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">智能运营中心</h1>
          <p className="mt-1 text-sm text-slate-500">自动发现需要关注的问题，明确处理人并持续跟进到解决。</p>
        </div>
        <div className="flex flex-wrap gap-2">
        {canManageSettings ? <Link className="btn" to="/operations/settings"><Settings2 size={15} />运营设置</Link> : null}
        {canScan ? (
          <button
            className="btn btn-primary"
            disabled={scan.isPending}
            onClick={() => scan.mutate(null)}
          >
            <RefreshCw className={scan.isPending ? "animate-spin" : ""} size={15} />
            立即检查一次
          </button>
        ) : null}
        </div>
      </header>

      {!context.data.operations_enabled ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          自动检查尚未开启。已有事项和报告仍可查看；具备权限的管理人员可前往运营设置开启。
        </div>
      ) : (
        <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 p-3 text-xs text-emerald-800">
          自动检查正在运行 · 最近更新 {formatBeijingDateTime(brief.data?.generated_at ?? Date.now())} · 后续检查由系统按运营规则自动安排
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="panel p-4">
          <div className="text-xs text-slate-500">待处理事项</div>
          <div className="mt-2 text-2xl font-semibold">{brief.data?.total ?? 0}</div>
        </div>
        <div className="panel p-4">
          <div className="text-xs text-slate-500">已超时事项</div>
          <div className="mt-2 text-2xl font-semibold text-orange-600">
            {brief.data?.groups.reduce((sum, group) => sum + group.overdue, 0) ?? 0}
          </div>
        </div>
        <div className="panel p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Bot size={14} />AI 总结与建议</div>
          <div className="mt-2 flex items-center gap-2 text-sm font-medium">
            {context.data.model_enabled ? <CheckCircle2 className="text-emerald-600" size={17} /> : <AlertTriangle className="text-amber-600" size={17} />}
            {context.data.model_enabled ? "已开启" : "未开启；不影响业务数据和报告"}
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            AI 没有单独的聊天入口，会在经营报告、欠费／续费案件和数据核对案件中按需出现。
          </p>
          <Link className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-700 hover:text-emerald-800" to="/reports">
            查看 AI 经营总结 <ArrowRight size={13} />
          </Link>
        </div>
      </div>

      <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <div className="flex gap-2" role="tablist" aria-label="事项范围">
            <button className={`btn ${view === "active" ? "btn-primary" : ""}`} onClick={() => setView("active")}>待处理</button>
            <button className={`btn ${view === "history" ? "btn-primary" : ""}`} onClick={() => setView("history")}><History size={14} />已完成</button>
          </div>
          {view === "history" ? (
            <select className="field" aria-label="完成状态" value={historyState} onChange={(event) => setHistoryState(event.target.value as typeof historyState)}>
              <option value="all">全部完成事项</option>
              <option value="resolved">已解决</option>
              <option value="dismissed">已关闭</option>
            </select>
          ) : null}
        </div>
        {view === "active" ? (
          <div className="flex flex-wrap gap-2 border-b p-4">
            <button className={`btn ${queue ? "" : "btn-primary"}`} onClick={() => setQueue(undefined)}>全部</button>
            {brief.data?.groups.map((group) => (
              <button className={`btn ${queue === group.queue_key ? "btn-primary" : ""}`} key={group.queue_key} onClick={() => setQueue(group.queue_key)}>
                {queueNames[group.queue_key] ?? group.queue_key} · {group.total}
              </button>
            ))}
          </div>
        ) : null}
        {cases.data?.length ? (
          <div className="divide-y">
            {cases.data.map((item) => (
              <Link className="grid gap-3 p-4 transition hover:bg-slate-50 md:grid-cols-[1fr_auto_auto]" key={item.id} to={`/operations/cases/${item.id}`}>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${severityClass[item.severity]}`}>{severityLabel(item.severity)}</span>
                    <span className="font-medium text-slate-900">{item.title}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{queueNames[item.queue_key] ?? item.queue_key} · 第 {item.occurrence_no} 次发生</div>
                </div>
                {view === "active" ? (
                  <>
                    <div className="flex items-center gap-1 text-xs text-slate-500"><UserRound size={14} />{item.assigned_to ? "已有处理人" : "待处理"}</div>
                    <div className="text-xs text-slate-500">{item.due_at ? `截止 ${formatBeijingDateTime(item.due_at)}` : "无截止时间"}</div>
                  </>
                ) : (
                  <>
                    <div className="text-xs text-slate-500">{caseStateLabel(item.state)}</div>
                    <div className="text-xs text-slate-500">{item.resolved_at ? `完成于 ${formatBeijingDateTime(item.resolved_at)}` : "已结束"}</div>
                  </>
                )}
              </Link>
            ))}
          </div>
        ) : (
          <div className="p-10 text-center text-sm text-slate-500">{view === "active" ? "当前分类没有待处理事项。" : "暂无已完成事项。"}</div>
        )}
      </section>

    </div>
  );
}
