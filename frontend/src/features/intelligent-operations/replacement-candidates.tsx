import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarPlus, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import { hasOperationsCapability } from "./access-control";
import { ApprovalCard } from "./approval-card";
import {
  generateReplacementCandidates,
  type OperationApproval,
  type OperationCase,
  proposeReplacement,
  type ReplacementCandidateResult,
  useOperationApprovals,
  useOperationRun,
  useOperationsContext,
} from "./api";

function localInput(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function initialWindow() {
  const start = new Date(Date.now() + 24 * 60 * 60 * 1000);
  start.setMinutes(0, 0, 0);
  return {
    start: localInput(start),
    end: localInput(new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000)),
  };
}

export function ReplacementCandidates({ item }: { item: OperationCase }) {
  const client = useQueryClient();
  const defaults = useMemo(initialWindow, []);
  const [windowStart, setWindowStart] = useState(defaults.start);
  const [windowEnd, setWindowEnd] = useState(defaults.end);
  const [result, setResult] = useState<ReplacementCandidateResult | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [proposalApproval, setProposalApproval] = useState<OperationApproval | null>(null);
  const context = useOperationsContext();
  const canDecide = Boolean(
    context.data && hasOperationsCapability(context.data, "operations.approval.decide"),
  );
  const approvals = useOperationApprovals(
    ["pending", "approved", "rejected", "expired", "stale"],
    canDecide,
  );
  const existingApproval = approvals.data?.find((approval) => approval.case_id === item.id);
  const visibleApproval = proposalApproval ?? existingApproval;
  const executionRun = useOperationRun(visibleApproval ? item.current_run_id : undefined);
  const generate = useMutation({
    mutationFn: () =>
      generateReplacementCandidates(item, {
        window_start: new Date(windowStart).toISOString(),
        window_end: new Date(windowEnd).toISOString(),
        max_candidates: 20,
      }),
    onSuccess: async (data) => {
      setResult(data);
      setSelectedPlanId(data.candidates[0]?.resource_plan_id ?? "");
      await client.invalidateQueries({ queryKey: ["operation-case", item.id] });
    },
  });
  const propose = useMutation({
    mutationFn: () => proposeReplacement(item, selectedPlanId),
    onSuccess: async (data) => {
      setProposalApproval(data.approval);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["operation-case", item.id] }),
        client.invalidateQueries({ queryKey: ["operation-approvals"] }),
      ]);
    },
  });

  if (item.case_type !== "class_replacement_pending") return null;

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><CalendarPlus size={18} />课程补排协调</h2>
          <p className="mt-1 text-xs text-slate-500">系统只使用原教练和原场地生成无冲突候选；不会自动判断学员是否有空。</p>
        </div>
      </div>

      {!visibleApproval && !["resolved", "dismissed"].includes(item.state) ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-slate-600">
              候选开始时间
              <input className="field mt-1 w-full" type="datetime-local" value={windowStart} onChange={(event) => setWindowStart(event.target.value)} />
            </label>
            <label className="text-xs text-slate-600">
              候选结束时间
              <input className="field mt-1 w-full" type="datetime-local" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} />
            </label>
          </div>
          <button className="btn mt-3" disabled={generate.isPending || !windowStart || !windowEnd} onClick={() => generate.mutate()}>
            <RefreshCw className={generate.isPending ? "animate-spin" : ""} size={15} />
            {generate.isPending ? "正在检查资源…" : "生成合法候选"}
          </button>
        </>
      ) : null}

      {result ? (
        <div className="mt-4 space-y-3">
          {result.candidates.length ? result.candidates.map((plan) => (
            <label className={`block cursor-pointer rounded-xl border p-4 ${selectedPlanId === plan.resource_plan_id ? "border-emerald-500 bg-emerald-50" : "bg-white"}`} key={plan.resource_plan_id}>
              <div className="flex items-start gap-3">
                <input className="mt-1" type="radio" name="replacement-plan" checked={selectedPlanId === plan.resource_plan_id} onChange={() => setSelectedPlanId(plan.resource_plan_id)} />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{new Date(plan.starts_at).toLocaleString()} 至 {new Date(plan.ends_at).toLocaleTimeString()}</div>
                  <div className="mt-1 text-xs text-slate-500">原教练 {plan.coach_ids.length} 名 · 原场地 {plan.court_ids.length} 片 · 有效至 {new Date(plan.expires_at).toLocaleString()}</div>
                  {plan.ranking_explanation ? <p className="mt-2 text-xs text-slate-600">{plan.ranking_explanation}</p> : null}
                </div>
              </div>
            </label>
          )) : (
            <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">当前窗口没有合法候选，请调整时间范围或回到人工排课页面处理。</div>
          )}
          {result.caveats.map((caveat) => (
            <p className="flex items-start gap-2 text-xs text-amber-700" key={caveat}><AlertTriangle className="mt-0.5 shrink-0" size={14} />{caveat}</p>
          ))}
          {selectedPlanId ? (
            <button className="btn btn-primary" disabled={propose.isPending} onClick={() => propose.mutate()}>
              已完成人员协调，提交审批
            </button>
          ) : null}
        </div>
      ) : null}

      {visibleApproval ? <div className="mt-4"><ApprovalCard approval={visibleApproval} canDecide={canDecide} run={executionRun.data} /></div> : null}
      {generate.error ? <p className="mt-2 text-sm text-red-600">{generate.error.message}</p> : null}
      {propose.error ? <p className="mt-2 text-sm text-red-600">{propose.error.message}</p> : null}
      {approvals.error && canDecide ? <p className="mt-2 text-sm text-red-600">{approvals.error.message}</p> : null}
    </section>
  );
}
