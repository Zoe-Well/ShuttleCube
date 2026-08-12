import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, CalendarClock, CircleDollarSign, MessageSquareText } from "lucide-react";
import { useMemo, useState } from "react";

import { beijingDateTimeInputToIso, formatBeijingDateTime, toBeijingDateTimeInput } from "@/lib/beijing-time";

import {
  analyzeOperationCase,
  type OperationCase,
  recordFollowupActivity,
  useFollowupContext,
  useOperationRun,
} from "./api";
import { outcomeLabel, runStateLabel } from "./terminology";

const supportedCases = new Set([
  "receivable_followup",
  "fixed_class_renewal",
  "private_package_renewal",
]);

function localDateTime(offsetHours = 0) {
  return toBeijingDateTimeInput(new Date(Date.now() + offsetHours * 60 * 60 * 1000));
}

export function RevenueRetentionPanel({ item }: { item: OperationCase }) {
  const client = useQueryClient();
  const context = useFollowupContext(supportedCases.has(item.case_type) ? item.id : undefined);
  const [analysisRunId, setAnalysisRunId] = useState<string | null>(null);
  const analysisRun = useOperationRun(analysisRunId);
  const [outcome, setOutcome] = useState<
    | "reached"
    | "no_answer"
    | "promised_payment"
    | "paid_elsewhere"
    | "renewed"
    | "no_intent"
    | "follow_later"
    | "disputed"
    | "invalid_contact"
    | "other"
  >("reached");
  const [summary, setSummary] = useState("");
  const [nextCheckAt, setNextCheckAt] = useState(localDateTime(24));
  const analyze = useMutation({
    mutationFn: () => analyzeOperationCase(item.id),
    onSuccess: (result) => setAnalysisRunId(result.run_id),
  });
  const record = useMutation({
    mutationFn: () => {
      const contact = context.data?.contact;
      const requiresNextCheck = outcome === "follow_later" || outcome === "promised_payment";
      return recordFollowupActivity(item, {
        activity_type: "contact_result",
        channel: contact?.available ? "phone" : "none",
        contact_subject_type: contact?.subject_type,
        contact_subject_id: contact?.subject_id,
        outcome_code: outcome,
        summary: summary.trim(),
        happened_at: new Date().toISOString(),
        next_check_at: requiresNextCheck ? beijingDateTimeInputToIso(nextCheckAt) : undefined,
      });
    },
    onSuccess: () => {
      setSummary("");
      void client.invalidateQueries({ queryKey: ["operation-followup-context", item.id] });
      void client.invalidateQueries({ queryKey: ["operation-case", item.id] });
    },
  });
  const analysis = analysisRun.data?.checkpoint?.state?.analysis;
  const metrics = useMemo(() => {
    if (!context.data) return [];
    if (context.data.amounts) {
      return [
        ["应收金额", `¥${context.data.amounts.actual_receivable}`],
        ["已净收", `¥${context.data.amounts.net_received}`],
        ["待收金额", `¥${context.data.amounts.outstanding}`],
        ["账龄", `${context.data.aging_days ?? 0} 天`],
      ];
    }
    return [
      ["续费类型", context.data.renewal_type === "fixed_class" ? "固定班" : "私教课包"],
      [
        "剩余量",
        context.data.renewal_type === "fixed_class"
          ? `${context.data.remaining_scheduled_sessions ?? 0} 节待上课程`
          : `${context.data.remaining_units ?? 0} 课时`,
      ],
      ["到期时间", context.data.end_at ?? context.data.expires_on ?? "未设置"],
    ];
  }, [context.data]);

  if (!supportedCases.has(item.case_type)) return null;
  if (context.isPending) return <section className="panel p-5 text-sm text-slate-500">正在加载跟进信息…</section>;
  if (context.error || !context.data) {
    return <section className="panel p-5 text-sm text-red-600">{context.error?.message ?? "无法读取跟进信息"}</section>;
  }

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><CircleDollarSign size={18} />收入保障跟进</h2>
          <p className="mt-1 text-xs text-slate-500">金额、课时和续费信息来自业务记录；AI 只提供解释和可编辑草稿。</p>
        </div>
        <button className="btn" disabled={analyze.isPending} onClick={() => analyze.mutate()}>
          <Bot size={15} />{analyze.isPending ? "正在创建分析…" : "生成分析与沟通草稿"}
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div className="rounded-lg border bg-white p-3" key={label}>
            <div className="text-xs text-slate-500">{label}</div>
            <div className="mt-1 font-semibold">{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm">
        <div className="font-medium">联系人</div>
        <div className="mt-1 text-slate-600">
          {context.data.contact.available
            ? `${context.data.contact.display_name ?? "已授权联系人"}（系统不会向 AI 提供电话或微信号）`
            : "暂无可用联系人；系统不会编造联系方式或生成发送建议。"}
        </div>
      </div>

      {analysisRun.data ? (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50/50 p-4">
          <div className="text-sm font-medium">AI 分析 · {runStateLabel(analysisRun.data.state)}</div>
          {analysis ? (
            <div className="mt-2 space-y-2 text-sm">
              <p>{analysis.summary}</p>
              {analysis.next_actions.length ? (
                <ul className="list-disc space-y-1 pl-5">{analysis.next_actions.map((value) => <li key={value}>{value}</li>)}</ul>
              ) : null}
              {analysis.communication_draft ? (
                <div className="rounded-md bg-white p-3">
                  <div className="mb-1 text-xs font-medium text-slate-500">可编辑沟通草稿（不会自动发送）</div>
                  {analysis.communication_draft}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-600">
              {analysisRun.data.checkpoint?.state?.reason === "model_disabled"
                ? "当前场馆未开启 AI 辅助，跟进信息仍可正常使用。"
                : "分析正在处理，或 AI 服务暂时不可用。"}
            </p>
          )}
        </div>
      ) : null}

      <div className="mt-5 border-t pt-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><MessageSquareText size={16} />记录人工跟进结果</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-[180px_1fr]">
          <select className="field" value={outcome} onChange={(event) => setOutcome(event.target.value as typeof outcome)}>
            <option value="reached">已联系</option>
            <option value="no_answer">未接通</option>
            <option value="promised_payment">承诺付款</option>
            <option value="renewed">已续费</option>
            <option value="follow_later">稍后跟进</option>
            <option value="disputed">对账有异议</option>
            <option value="no_intent">暂无意向</option>
            <option value="invalid_contact">联系方式无效</option>
            <option value="other">其他</option>
          </select>
          <input className="field" maxLength={2000} placeholder="填写实际沟通结果；这不会改变付款、课时或续费事实" value={summary} onChange={(event) => setSummary(event.target.value)} />
        </div>
        {outcome === "follow_later" || outcome === "promised_payment" ? (
          <label className="mt-3 flex items-center gap-2 text-sm">
            <CalendarClock size={16} />下次检查
            <input className="field" type="datetime-local" value={nextCheckAt} onChange={(event) => setNextCheckAt(event.target.value)} />
          </label>
        ) : null}
        <button
          className="btn btn-primary mt-3"
          disabled={!summary.trim() || record.isPending || !context.data.contact.available}
          onClick={() => record.mutate()}
        >
          {record.isPending ? "正在保存…" : "确认记录跟进"}
        </button>
        {!context.data.contact.available ? <p className="mt-2 text-xs text-amber-700">缺少可用联系人时不能记录联系结果，可在原业务资料中补充联系人后重试。</p> : null}
        {record.error ? <p className="mt-2 text-sm text-red-600">{record.error.message}</p> : null}
        {analyze.error ? <p className="mt-2 text-sm text-red-600">{analyze.error.message}</p> : null}
      </div>

      {context.data.activities.length ? (
        <div className="mt-5 border-t pt-4">
          <h3 className="text-sm font-semibold">跟进记录</h3>
          <div className="mt-3 space-y-2">
            {context.data.activities.map((activity) => (
              <div className="rounded-lg bg-slate-50 p-3 text-sm" key={activity.id}>
                <div className="font-medium">{outcomeLabel(activity.outcome_code)} · {formatBeijingDateTime(activity.happened_at)}</div>
                <div className="mt-1 text-slate-600">{activity.summary}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
