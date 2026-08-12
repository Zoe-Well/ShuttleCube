import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock3, Link2, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { formatBeijingDateTime } from "@/lib/beijing-time";

import {
  assignOperationCase,
  claimOperationCase,
  dismissOperationCase,
  listOperationsMemberships,
  useOperationCase,
  useOperationRun,
  useOperationRunEvents,
  useOperationsContext,
} from "./api";
import { hasOperationsCapability } from "./access-control";
import { CaseActionDrawer } from "./case-action-drawer";
import { CaseEvidenceSummary } from "./case-evidence-summary";
import {
  actorTypeLabel,
  caseStateLabel,
  caseTypeLabel,
  eventTypeLabel,
  outcomeLabel,
  runStateLabel,
  workflowLabel,
} from "./terminology";

export function OperationCaseDetailPage() {
  const { caseId } = useParams();
  const client = useQueryClient();
  const [dismissReason, setDismissReason] = useState("");
  const [assignee, setAssignee] = useState("");
  const [assignReason, setAssignReason] = useState("");
  const query = useOperationCase(caseId);
  const context = useOperationsContext();
  const canAssign = Boolean(
    context.data && hasOperationsCapability(context.data, "operations.case.assign"),
  );
  const canManage = Boolean(
    context.data && hasOperationsCapability(context.data, "operations.case.manage"),
  );
  const memberships = useQuery({
    queryKey: ["operations-memberships"],
    queryFn: listOperationsMemberships,
    enabled: canAssign,
  });
  const run = useOperationRun(query.data?.current_run_id);
  const events = useOperationRunEvents(canManage ? query.data?.current_run_id : undefined);
  const refresh = () => client.invalidateQueries({ queryKey: ["operation-case", caseId] });
  const claim = useMutation({ mutationFn: claimOperationCase, onSuccess: refresh });
  const assign = useMutation({
    mutationFn: () => assignOperationCase(query.data!, assignee, assignReason.trim()),
    onSuccess: () => {
      setAssignReason("");
      void refresh();
    },
  });
  const dismiss = useMutation({
    mutationFn: ({ reason }: { reason: string }) => dismissOperationCase(query.data!, reason),
    onSuccess: () => {
      setDismissReason("");
      void refresh();
    },
  });

  if (query.isPending) return <div className="panel p-8 text-sm text-slate-500">正在加载待处理事项…</div>;
  if (query.error || !query.data) return <div className="panel p-8 text-sm text-red-600">{query.error?.message ?? "待处理事项不存在"}</div>;
  const item = query.data;
  const isClosed = ["resolved", "dismissed"].includes(item.state);
  const eligibleMembers = memberships.data?.filter(
    (member) => member.status === "active" && member.capabilities.includes(item.required_capability),
  ) ?? [];
  const showProgress = Boolean(run.data && [
    "queued", "claimed", "running", "retry_scheduled", "waiting_approval", "awaiting_approval",
    "waiting_human", "failed", "escalated", "uncertain",
  ].includes(run.data.state));
  const businessLinks = item.business_links?.length
    ? item.business_links
    : (item.evidence.business_links ?? []).map((route) => ({ label: "查看业务记录", route }));
  return (
    <div className="space-y-5">
      <Link className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900" to="/operations"><ArrowLeft size={15} />返回运营中心</Link>
      <header className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs text-slate-500">{caseTypeLabel(item.case_type)} · 第 {item.occurrence_no} 次发现</div>
            <h1 className="mt-1 text-xl font-semibold">{item.title}</h1>
            {item.business_summary ? <p className="mt-2 max-w-3xl text-sm text-slate-600">{item.business_summary}</p> : null}
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
              <span className="flex items-center gap-1"><Clock3 size={14} />发现于 {formatBeijingDateTime(item.first_detected_at)}</span>
              {!isClosed ? <span className="flex items-center gap-1"><UserRound size={14} />{item.assigned_to ? "已有处理人" : "尚无处理人"}</span> : null}
              <span className="flex items-center gap-1"><CheckCircle2 size={14} />状态：{caseStateLabel(item.state)}</span>
            </div>
          </div>
          {!item.assigned_to && !isClosed ? (
            <button className="btn btn-primary" disabled={claim.isPending} onClick={() => claim.mutate(item)}>由我处理</button>
          ) : null}
        </div>
      </header>

      {canAssign && !isClosed && eligibleMembers.length > 1 ? (
        <section className="panel p-5">
          <h2 className="font-semibold">分配处理人</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            <select className="field min-w-64" value={assignee} onChange={(event) => setAssignee(event.target.value)}>
              <option value="">选择处理人</option>
              {eligibleMembers.map((member) => (
                <option key={member.id} value={member.id}>{member.display_name}</option>
              ))}
            </select>
            <input className="field min-w-64" placeholder="填写分配原因" value={assignReason} onChange={(event) => setAssignReason(event.target.value)} />
            <button className="btn" disabled={!assignee || !assignReason.trim() || assign.isPending} onClick={() => assign.mutate()}>确认分配</button>
          </div>
        </section>
      ) : null}

      <CaseEvidenceSummary item={item} />

      {!isClosed ? <CaseActionDrawer item={item} canManage={canManage} /> : null}

      {(isClosed || !canManage) && businessLinks.length ? (
        <section className="panel p-5">
          <h2 className="font-semibold">相关业务记录</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {businessLinks.map((link) => <Link className="btn" key={link.route} to={link.route}><Link2 size={14} />{link.label}</Link>)}
          </div>
        </section>
      ) : null}

      {isClosed ? (
        <section className="panel p-5">
          <h2 className="font-semibold">处理结果</h2>
          <div className="mt-3 text-sm font-medium">{caseStateLabel(item.state)}</div>
          {item.resolved_at ? <p className="mt-1 text-xs text-slate-500">完成时间：{formatBeijingDateTime(item.resolved_at)}</p> : null}
          {item.dismissed_reason ? <p className="mt-2 text-sm text-slate-700">关闭原因：{item.dismissed_reason}</p> : null}
          <p className="mt-3 text-xs text-slate-500">历史事项仅供查询，不能继续修改或执行操作。</p>
        </section>
      ) : null}

      {isClosed && item.activities?.length ? (
        <section className="panel p-5">
          <h2 className="font-semibold">人工处理记录</h2>
          <div className="mt-3 space-y-2">
            {item.activities.map((activity) => (
              <div className="rounded-lg bg-slate-50 p-3 text-sm" key={activity.id}>
                <div className="font-medium">{outcomeLabel(activity.outcome_code)} · {formatBeijingDateTime(activity.happened_at)}</div>
                <div className="mt-1 text-slate-600">{activity.summary}</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {showProgress && run.data ? (
        <section className="panel p-5">
          <h2 className="font-semibold">最近处理进度</h2>
          <div className="mt-3 text-sm">{workflowLabel(run.data.workflow_key)} · {runStateLabel(run.data.state)}</div>
          {run.data.error_summary ? <p className="mt-2 text-xs text-red-600">{run.data.error_summary}</p> : null}
        </section>
      ) : null}

      {canManage && events.data?.length ? (
        <details className="panel p-5">
          <summary className="cursor-pointer text-sm font-medium">查看系统记录</summary>
          <div className="mt-4 space-y-3 border-l pl-4">
            {events.data.map((event) => (
              <div className="relative" key={event.id}>
                <span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-emerald-500" />
                <div className="text-sm font-medium">{eventTypeLabel(event.event_type)}</div>
                <div className="mt-0.5 text-xs text-slate-500">{formatBeijingDateTime(event.occurred_at)} · {actorTypeLabel(event.actor_type)}</div>
                {event.payload.outcome ? <div className="mt-1 text-xs">核对结果：{outcomeLabel(String(event.payload.outcome))}</div> : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {!isClosed ? (
        <section className="panel p-5">
          <h2 className="font-semibold">关闭此事项</h2>
          <p className="mt-1 text-xs text-slate-500">仅在确认该提醒不需要继续处理时使用；真实问题消失后系统会按业务事实自动关闭。</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <input className="field min-w-72 flex-1" placeholder="填写关闭原因" value={dismissReason} onChange={(event) => setDismissReason(event.target.value)} />
            <button className="btn" disabled={!dismissReason.trim() || dismiss.isPending} onClick={() => dismiss.mutate({ reason: dismissReason.trim() })}>确认关闭</button>
          </div>
        </section>
      ) : null}
      {claim.error ? <p className="text-sm text-red-600">{claim.error.message}</p> : null}
      {assign.error ? <p className="text-sm text-red-600">{assign.error.message}</p> : null}
      {dismiss.error ? <p className="text-sm text-red-600">{dismiss.error.message}</p> : null}
    </div>
  );
}
