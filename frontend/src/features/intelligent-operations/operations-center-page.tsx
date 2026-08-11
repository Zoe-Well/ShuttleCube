import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, RefreshCw, UserRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { hasOperationsCapability } from "./access-control";
import {
  startOperationsScan,
  useOperationCases,
  useOperationsBrief,
  useOperationsContext,
} from "./api";
import { OperationsSettingsPanel } from "./operations-settings-panel";
import { PolicySettingsPanel } from "./policy-settings-panel";

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
  const [queue, setQueue] = useState<string>();
  const context = useOperationsContext();
  const cases = useOperationCases({ queue });
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
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">智能运营中心</h1>
          <p className="mt-1 text-sm text-slate-500">主动发现问题、分配责任并跟踪到真实业务事实关闭。</p>
        </div>
        {canScan ? (
          <button
            className="btn btn-primary"
            disabled={scan.isPending}
            onClick={() => scan.mutate(null)}
          >
            <RefreshCw className={scan.isPending ? "animate-spin" : ""} size={15} />
            立即扫描
          </button>
        ) : null}
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="panel p-4">
          <div className="text-xs text-slate-500">当前待处理</div>
          <div className="mt-2 text-2xl font-semibold">{brief.data?.total ?? 0}</div>
        </div>
        <div className="panel p-4">
          <div className="text-xs text-slate-500">超期案件</div>
          <div className="mt-2 text-2xl font-semibold text-orange-600">
            {brief.data?.groups.reduce((sum, group) => sum + group.overdue, 0) ?? 0}
          </div>
        </div>
        <div className="panel p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500"><Bot size={14} />模型解释</div>
          <div className="mt-2 flex items-center gap-2 text-sm font-medium">
            {context.data.model_enabled ? <CheckCircle2 className="text-emerald-600" size={17} /> : <AlertTriangle className="text-amber-600" size={17} />}
            {context.data.model_enabled ? "已启用" : "未启用；确定性功能正常"}
          </div>
        </div>
      </div>

      <section className="panel overflow-hidden">
        <div className="flex flex-wrap gap-2 border-b p-4">
          <button className={`btn ${queue ? "" : "btn-primary"}`} onClick={() => setQueue(undefined)}>全部</button>
          {brief.data?.groups.map((group) => (
            <button className={`btn ${queue === group.queue_key ? "btn-primary" : ""}`} key={group.queue_key} onClick={() => setQueue(group.queue_key)}>
              {queueNames[group.queue_key] ?? group.queue_key} · {group.total}
            </button>
          ))}
        </div>
        {cases.data?.length ? (
          <div className="divide-y">
            {cases.data.map((item) => (
              <Link className="grid gap-3 p-4 transition hover:bg-slate-50 md:grid-cols-[1fr_auto_auto]" key={item.id} to={`/operations/cases/${item.id}`}>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${severityClass[item.severity]}`}>{item.severity}</span>
                    <span className="font-medium text-slate-900">{item.title}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{queueNames[item.queue_key] ?? item.queue_key} · 第 {item.occurrence_no} 次发生</div>
                </div>
                <div className="flex items-center gap-1 text-xs text-slate-500"><UserRound size={14} />{item.assigned_to ? "已分配" : "待认领"}</div>
                <div className="text-xs text-slate-500">{item.due_at ? `截止 ${new Date(item.due_at).toLocaleString()}` : "无截止时间"}</div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="p-10 text-center text-sm text-slate-500">当前队列没有待处理案件。</div>
        )}
      </section>

      {hasOperationsCapability(context.data, "operations.model.manage") || hasOperationsCapability(context.data, "operations.membership.manage") ? (
        <OperationsSettingsPanel context={context.data} />
      ) : null}
      <PolicySettingsPanel context={context.data} />
    </div>
  );
}
