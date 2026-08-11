import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock3, Link2, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

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
import { ReplacementCandidates } from "./replacement-candidates";
import { ReconciliationPanel } from "./reconciliation-panel";
import { RevenueRetentionPanel } from "./revenue-retention-panel";

function displayValue(value: unknown) {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (value == null) return "—";
  return String(value);
}

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
  const memberships = useQuery({
    queryKey: ["operations-memberships"],
    queryFn: listOperationsMemberships,
    enabled: canAssign,
  });
  const run = useOperationRun(query.data?.current_run_id);
  const events = useOperationRunEvents(query.data?.current_run_id);
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

  if (query.isPending) return <div className="panel p-8 text-sm text-slate-500">正在加载案件…</div>;
  if (query.error || !query.data) return <div className="panel p-8 text-sm text-red-600">{query.error?.message ?? "案件不存在"}</div>;
  const item = query.data;
  const facts = item.evidence.facts ?? {};
  return (
    <div className="space-y-5">
      <Link className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900" to="/operations"><ArrowLeft size={15} />返回运营中心</Link>
      <header className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs text-slate-500">{item.case_type} · 第 {item.occurrence_no} 次发生</div>
            <h1 className="mt-1 text-xl font-semibold">{item.title}</h1>
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
              <span className="flex items-center gap-1"><Clock3 size={14} />发现于 {new Date(item.first_detected_at).toLocaleString()}</span>
              <span className="flex items-center gap-1"><UserRound size={14} />{item.assigned_to ? "已分配" : "尚未认领"}</span>
              <span className="flex items-center gap-1"><CheckCircle2 size={14} />状态：{item.state}</span>
            </div>
          </div>
          {!item.assigned_to && !["resolved", "dismissed"].includes(item.state) ? (
            <button className="btn btn-primary" disabled={claim.isPending} onClick={() => claim.mutate(item)}>认领案件</button>
          ) : null}
        </div>
      </header>

      {canAssign && !["resolved", "dismissed"].includes(item.state) ? (
        <section className="panel p-5">
          <h2 className="font-semibold">分配负责人</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            <select className="field min-w-64" value={assignee} onChange={(event) => setAssignee(event.target.value)}>
              <option value="">选择具备所需权限的成员</option>
              {memberships.data?.filter((member) => member.status === "active" && member.capabilities.includes(item.required_capability)).map((member) => (
                <option key={member.id} value={member.id}>{member.display_name}</option>
              ))}
            </select>
            <input className="field min-w-64" placeholder="填写分配原因" value={assignReason} onChange={(event) => setAssignReason(event.target.value)} />
            <button className="btn" disabled={!assignee || !assignReason.trim() || assign.isPending} onClick={() => assign.mutate()}>确认分配</button>
          </div>
        </section>
      ) : null}

      <section className="panel p-5">
        <h2 className="font-semibold">确定性证据</h2>
        <p className="mt-1 text-xs text-slate-500">以下事实由业务程序读取和计算，不由模型判断。</p>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {Object.entries(facts).map(([key, value]) => (
            <div className="rounded-lg bg-slate-50 p-3" key={key}>
              <dt className="text-xs text-slate-500">{key}</dt>
              <dd className="mt-1 break-words text-sm font-medium">{displayValue(value)}</dd>
            </div>
          ))}
        </dl>
        {item.evidence.business_links?.length ? (
          <div className="mt-4 flex gap-2">
            {item.evidence.business_links.map((route) => <Link className="btn" key={route} to={route}><Link2 size={14} />查看业务记录</Link>)}
          </div>
        ) : null}
      </section>

      <RevenueRetentionPanel item={item} />
      <ReplacementCandidates item={item} />
      <ReconciliationPanel item={item} />

      {run.data ? (
        <section className="panel p-5">
          <h2 className="font-semibold">最近运行</h2>
          <div className="mt-3 text-sm">{run.data.workflow_key} · {run.data.state}</div>
          {run.data.error_summary ? <p className="mt-2 text-xs text-red-600">{run.data.error_summary}</p> : null}
        </section>
      ) : null}

      {events.data?.length ? (
        <section className="panel p-5">
          <h2 className="font-semibold">处理与复核时间线</h2>
          <div className="mt-4 space-y-3 border-l pl-4">
            {events.data.map((event) => (
              <div className="relative" key={event.id}>
                <span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-emerald-500" />
                <div className="text-sm font-medium">{event.event_type}</div>
                <div className="mt-0.5 text-xs text-slate-500">{new Date(event.occurred_at).toLocaleString()} · {event.actor_type}</div>
                {event.payload.outcome ? <div className="mt-1 text-xs">复核结果：{displayValue(event.payload.outcome)}</div> : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {! ["resolved", "dismissed"].includes(item.state) ? (
        <section className="panel p-5">
          <h2 className="font-semibold">人工关闭</h2>
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
