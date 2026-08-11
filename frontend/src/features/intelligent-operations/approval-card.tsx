import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";

import {
  decideOperationApproval,
  type OperationApproval,
  type OperationRun,
} from "./api";

function frozenPlan(approval: OperationApproval) {
  const value = approval.impact_snapshot.resource_plan;
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

export function ApprovalCard({
  approval,
  canDecide = true,
  run,
}: {
  approval: OperationApproval;
  canDecide?: boolean;
  run?: OperationRun;
}) {
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const plan = frozenPlan(approval);
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["operation-approvals"] }),
      client.invalidateQueries({ queryKey: ["operation-case", approval.case_id] }),
    ]);
  };
  const approve = useMutation({
    mutationFn: () => decideOperationApproval(approval, true, reason.trim()),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: () => decideOperationApproval(approval, false, reason.trim()),
    onSuccess: refresh,
  });
  const pending = approval.state === "pending";
  const decisionPending = approve.isPending || reject.isPending;
  const verificationValue = run?.checkpoint?.state?.verification;
  const verification = verificationValue && typeof verificationValue === "object"
    ? (verificationValue as Record<string, unknown>)
    : null;

  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-amber-950">
            <ShieldCheck size={18} />受控补排审批
          </h3>
          <p className="mt-1 text-xs text-amber-800">方案内容已经冻结；审批后仍会重新检查营业时间、课程版本与资源冲突。</p>
        </div>
        <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-amber-900">
          {approval.state}
        </span>
      </div>

      <p className="mt-3 text-sm">{approval.action_summary}</p>
      {plan ? (
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div className="rounded-lg bg-white p-3">
            <dt className="text-xs text-slate-500">补排时间</dt>
            <dd className="mt-1 font-medium">
              {new Date(String(plan.starts_at)).toLocaleString()} 至 {new Date(String(plan.ends_at)).toLocaleString()}
            </dd>
          </div>
          <div className="rounded-lg bg-white p-3">
            <dt className="text-xs text-slate-500">冻结资源</dt>
            <dd className="mt-1 font-medium">
              教练 {Array.isArray(plan.coach_ids) ? plan.coach_ids.length : 0} 名 · 场地 {Array.isArray(plan.court_ids) ? plan.court_ids.length : 0} 片
            </dd>
          </div>
        </dl>
      ) : null}
      <div className="mt-3 flex items-start gap-2 rounded-lg bg-white p-3 text-xs text-amber-900">
        <AlertTriangle className="mt-0.5 shrink-0" size={15} />
        <span>系统不会自动判断学员是否有空。批准前请确认学员、教练和场馆协调已经完成。本操作不修改付款、退款、考勤或课时。</span>
      </div>

      {run ? (
        <div className="mt-3 rounded-lg bg-white p-3 text-sm">
          <div className="text-xs text-slate-500">执行进度</div>
          <div className="mt-1 font-medium">{run.state}</div>
          {run.error_summary ? <p className="mt-1 text-xs text-red-600">{run.error_summary}</p> : null}
          {verification ? (
            <p className="mt-1 text-xs text-emerald-700">
              确定性复核：{String(verification.outcome ?? "未知")} · {String(verification.reason_code ?? "—")}
            </p>
          ) : null}
        </div>
      ) : null}

      {pending && canDecide ? (
        <div className="mt-3 space-y-2">
          <input
            className="field w-full"
            placeholder="填写批准或拒绝原因"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-primary"
              disabled={!reason.trim() || decisionPending}
              onClick={() => approve.mutate()}
            >
              <CheckCircle2 size={15} />批准并进入受控执行
            </button>
            <button
              className="btn"
              disabled={!reason.trim() || decisionPending}
              onClick={() => reject.mutate()}
            >
              <XCircle size={15} />拒绝方案
            </button>
          </div>
        </div>
      ) : pending ? (
        <p className="mt-3 text-xs text-amber-900">等待具备审批权限的管理人员处理。</p>
      ) : approval.decision_reason ? (
        <p className="mt-3 text-xs text-slate-600">处理意见：{approval.decision_reason}</p>
      ) : null}
      {approve.error ? <p className="mt-2 text-sm text-red-600">{approve.error.message}</p> : null}
      {reject.error ? <p className="mt-2 text-sm text-red-600">{reject.error.message}</p> : null}
    </section>
  );
}
