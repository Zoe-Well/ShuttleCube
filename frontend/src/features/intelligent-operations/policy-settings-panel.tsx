import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";

import { formatBeijingDateTime } from "@/lib/beijing-time";

import { hasOperationsCapability } from "./access-control";
import {
  activateOperationsPolicy,
  copyOperationsPolicyDraft,
  createOperationsPolicyDraft,
  deleteOperationsPolicyDraft,
  listOperationsPolicies,
  type OperationsContext,
  type OperationsPolicy,
  type OperationsPolicyConfig,
  updateOperationsPolicyDraft,
} from "./api";

const defaults: OperationsPolicyConfig = {
  receivable_followup: { aging_days: 7, escalation_days: 30, max_attempts: 5 },
  renewal: {
    fixed_class_days: 30,
    private_package_expiry_days: 30,
    private_package_remaining_units: 2,
    cadence_days: 7,
  },
  attendance: { grace_hours: 12 },
  replacement: { window_days: 14, slot_minutes: 30, resource_mode: "original_only" },
  reports: {
    min_sample_size: 5,
    income_decline: "0.20",
    refund_ratio: "0.10",
    expense_growth: "0.20",
    outstanding: "5000.00",
    cancellation_rate: "0.10",
    low_utilization: "0.30",
    coach_pending: "5000.00",
  },
  runtime: { case_sla_days: 3, approval_expiry_minutes: 60, retry_limit: 2 },
};

function Field({
  name,
  label,
  value,
  description,
  step = "1",
}: {
  name: string;
  label: string;
  value: number | string;
  description: string;
  step?: string;
}) {
  return (
    <label className="text-xs font-medium">
      {label}
      <input className="field mt-1" defaultValue={value} min="0" name={name} required step={step} type="number" />
      <span className="mt-1 block font-normal leading-4 text-slate-500">{description} 推荐值：{value}</span>
    </label>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="rounded-lg border p-3">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </fieldset>
  );
}

const number = (data: FormData, key: string) => Number(data.get(key));
const decimal = (data: FormData, key: string) => String(data.get(key));

function configFrom(data: FormData): OperationsPolicyConfig {
  return {
    receivable_followup: {
      aging_days: number(data, "aging_days"),
      escalation_days: number(data, "escalation_days"),
      max_attempts: number(data, "max_attempts"),
    },
    renewal: {
      fixed_class_days: number(data, "fixed_class_days"),
      private_package_expiry_days: number(data, "private_package_expiry_days"),
      private_package_remaining_units: number(data, "private_package_remaining_units"),
      cadence_days: number(data, "cadence_days"),
    },
    attendance: { grace_hours: number(data, "grace_hours") },
    replacement: {
      window_days: number(data, "window_days"),
      slot_minutes: number(data, "slot_minutes") as 15 | 30 | 60,
      resource_mode: "original_only",
    },
    reports: {
      min_sample_size: number(data, "min_sample_size"),
      income_decline: decimal(data, "income_decline"),
      refund_ratio: decimal(data, "refund_ratio"),
      expense_growth: decimal(data, "expense_growth"),
      outstanding: decimal(data, "outstanding"),
      cancellation_rate: decimal(data, "cancellation_rate"),
      low_utilization: decimal(data, "low_utilization"),
      coach_pending: decimal(data, "coach_pending"),
    },
    runtime: {
      case_sla_days: number(data, "case_sla_days"),
      approval_expiry_minutes: number(data, "approval_expiry_minutes"),
      retry_limit: number(data, "retry_limit"),
    },
  };
}

const stateLabel = (state: OperationsPolicy["state"]) =>
  state === "active" ? "当前生效" : state === "draft" ? "草稿" : "历史版本";

function ConfigSummary({ config }: { config: OperationsPolicyConfig }) {
  const items = [
    ["欠费提醒", `${config.receivable_followup.aging_days} 天`],
    ["欠费升级", `${config.receivable_followup.escalation_days} 天`],
    ["最多联系", `${config.receivable_followup.max_attempts} 次`],
    ["固定班续费提醒", `提前 ${config.renewal.fixed_class_days} 天`],
    ["私教到期提醒", `提前 ${config.renewal.private_package_expiry_days} 天`],
    ["私教余课提醒", `${config.renewal.private_package_remaining_units} 课时`],
    ["考勤提醒", `课程结束 ${config.attendance.grace_hours} 小时后`],
    ["补排范围", `${config.replacement.window_days} 天`],
    ["事项处理时限", `${config.runtime.case_sla_days} 天`],
    ["审批有效期", `${config.runtime.approval_expiry_minutes} 分钟`],
    ["收入下降提醒", `${Number(config.reports.income_decline) * 100}%`],
    ["退款比例提醒", `${Number(config.reports.refund_ratio) * 100}%`],
    ["低利用率提醒", `${Number(config.reports.low_utilization) * 100}%`],
    ["待收金额提醒", `¥${Number(config.reports.outstanding).toFixed(2)}`],
  ];
  return (
    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
      {items.map(([label, value]) => (
        <div className="rounded-md bg-slate-50 p-2" key={label}>
          <dt className="text-slate-500">{label}</dt>
          <dd className="mt-1 font-medium text-slate-800">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

type EditorState = {
  kind: "new" | "edit";
  name: string;
  config: OperationsPolicyConfig;
  policy?: OperationsPolicy;
};

export function PolicySettingsPanel({ context }: { context: OperationsContext }) {
  const client = useQueryClient();
  const canManage = hasOperationsCapability(context, "operations.policy.manage");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const policies = useQuery({
    queryKey: ["operations-policies"],
    queryFn: listOperationsPolicies,
    enabled: canManage,
  });
  const createDraft = useMutation({
    mutationFn: createOperationsPolicyDraft,
    onSuccess: (policy) => {
      setEditor(null);
      setSelectedId(policy.id);
      void client.invalidateQueries({ queryKey: ["operations-policies"] });
    },
  });
  const updateDraft = useMutation({
    mutationFn: ({ policy, name, config }: { policy: OperationsPolicy; name: string; config: OperationsPolicyConfig }) =>
      updateOperationsPolicyDraft(policy, { name, config }),
    onSuccess: (policy) => {
      setEditor(null);
      setSelectedId(policy.id);
      void client.invalidateQueries({ queryKey: ["operations-policies"] });
    },
  });
  const copyDraft = useMutation({
    mutationFn: (policy: OperationsPolicy) => copyOperationsPolicyDraft(policy, `${policy.name} 副本`),
    onSuccess: (policy) => {
      setSelectedId(policy.id);
      setEditor({ kind: "edit", name: policy.name, config: policy.config, policy });
      void client.invalidateQueries({ queryKey: ["operations-policies"] });
    },
  });
  const removeDraft = useMutation({
    mutationFn: deleteOperationsPolicyDraft,
    onSuccess: (_, policy) => {
      if (selectedId === policy.id) setSelectedId(null);
      if (editor?.policy?.id === policy.id) setEditor(null);
      void client.invalidateQueries({ queryKey: ["operations-policies"] });
    },
  });
  const activate = useMutation({
    mutationFn: activateOperationsPolicy,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["operations-policies"] });
      void client.invalidateQueries({ queryKey: ["operations-context"] });
    },
  });
  if (!canManage) return null;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editor) return;
    const data = new FormData(event.currentTarget);
    const name = String(data.get("policy_name") ?? "").trim();
    if (!name) return;
    const config = configFrom(data);
    if (editor.kind === "edit" && editor.policy) {
      updateDraft.mutate({ policy: editor.policy, name, config });
    } else {
      createDraft.mutate({ name, config });
    }
  };

  const policyItems = policies.data ?? [];
  const active = policyItems.find((policy) => policy.state === "active");
  const mutationError = createDraft.error ?? updateDraft.error ?? copyDraft.error ?? removeDraft.error ?? activate.error;
  const isSaving = createDraft.isPending || updateDraft.isPending;

  return (
    <section className="panel p-5" aria-labelledby="operations-policy-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="operations-policy-title" className="font-semibold">运营规则</h2>
          <p className="mt-1 text-xs text-slate-500">管理提醒、升级、报告和审批规则。生效与历史版本只读，修改时会保留原版本。</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setEditor({ kind: "new", name: active ? `${active.name} 副本` : "新运营规则", config: active?.config ?? defaults })}
          type="button"
        >新建草稿</button>
      </div>

      <div className="mt-4 space-y-2">
        {policyItems.map((policy) => (
          <div className={`rounded-lg border p-3 ${policy.state === "active" ? "border-emerald-300 bg-emerald-50/50" : "border-slate-200"}`} key={policy.id}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">{policy.name}</div>
                <div className="mt-1 text-xs text-slate-500">版本 {policy.policy_version} · {stateLabel(policy.state)} · 创建于 {formatBeijingDateTime(policy.created_at)}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn" onClick={() => setSelectedId(selectedId === policy.id ? null : policy.id)} type="button">{selectedId === policy.id ? "收起" : "查看"}</button>
                {policy.state === "draft" ? <button className="btn" onClick={() => setEditor({ kind: "edit", name: policy.name, config: policy.config, policy })} type="button">编辑</button> : null}
                <button className="btn" disabled={copyDraft.isPending} onClick={() => copyDraft.mutate(policy)} type="button">复制为草稿</button>
                {policy.state === "draft" ? (
                  <>
                    <button className="btn" disabled={activate.isPending} onClick={() => window.confirm(`启用“${policy.name}”后，当前生效版本将转为历史版本。是否继续？`) && activate.mutate(policy)} type="button">激活</button>
                    <button className="btn" disabled={removeDraft.isPending} onClick={() => window.confirm(`确定删除草稿“${policy.name}”吗？此操作无法撤销。`) && removeDraft.mutate(policy)} type="button">删除</button>
                  </>
                ) : null}
              </div>
            </div>
            {selectedId === policy.id ? (
              <div className="mt-3 border-t border-slate-200 pt-3">
                <div className="text-xs text-slate-500">{policy.activated_at ? `激活时间：${formatBeijingDateTime(policy.activated_at)}` : "尚未激活"}</div>
                <ConfigSummary config={policy.config} />
              </div>
            ) : null}
          </div>
        ))}
        {!policies.isLoading && policyItems.length === 0 ? <p className="rounded-lg border border-dashed p-4 text-sm text-slate-500">还没有运营规则，请先新建草稿。</p> : null}
      </div>

      {editor ? (
        <form className="mt-6 space-y-4 border-t pt-5" key={`${editor.kind}-${editor.policy?.id ?? "new"}-${editor.policy?.version ?? 0}`} onSubmit={submit}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <label className="min-w-72 flex-1 text-xs font-medium">版本名称<input className="field mt-1" defaultValue={editor.name} maxLength={80} name="policy_name" required /></label>
            <button className="btn" onClick={() => setEditor(null)} type="button">取消编辑</button>
          </div>
          <Group title="欠费与续费">
            <Field name="aging_days" label="欠费多少天后提醒" value={editor.config.receivable_followup.aging_days} description="越小越早提醒。" />
            <Field name="escalation_days" label="欠费多少天后升级" value={editor.config.receivable_followup.escalation_days} description="达到后会提高事项优先级。" />
            <Field name="max_attempts" label="最多联系次数" value={editor.config.receivable_followup.max_attempts} description="达到后建议重点人工处理。" />
            <Field name="fixed_class_days" label="固定班提前多少天提醒续费" value={editor.config.renewal.fixed_class_days} description="越大越早开始跟进。" />
            <Field name="private_package_expiry_days" label="私教到期提前多少天提醒" value={editor.config.renewal.private_package_expiry_days} description="按课包到期日期计算。" />
            <Field name="private_package_remaining_units" label="私教剩余多少课时提醒" value={editor.config.renewal.private_package_remaining_units} description="剩余课时低于或等于该值时提醒。" />
            <Field name="cadence_days" label="两次跟进至少间隔几天" value={editor.config.renewal.cadence_days} description="避免短时间重复提醒。" />
          </Group>
          <Group title="考勤、补排与处理">
            <Field name="grace_hours" label="课程结束多少小时后提醒考勤" value={editor.config.attendance.grace_hours} description="给工作人员预留正常录入时间。" />
            <Field name="window_days" label="向后查找多少天的补排时间" value={editor.config.replacement.window_days} description="范围越大，可选时间通常越多。" />
            <Field name="slot_minutes" label="补排时间间隔（分钟）" value={editor.config.replacement.slot_minutes} description="只支持 15、30 或 60 分钟。" />
            <Field name="case_sla_days" label="事项应在几天内处理" value={editor.config.runtime.case_sla_days} description="超过后会标记为已超时。" />
            <Field name="approval_expiry_minutes" label="审批结果多少分钟内有效" value={editor.config.runtime.approval_expiry_minutes} description="过期后需重新检查并审批。" />
            <Field name="retry_limit" label="失败后最多自动重试几次" value={editor.config.runtime.retry_limit} description="超过后转为人工处理。" />
          </Group>
          <Group title="经营报告异常阈值">
            <Field name="min_sample_size" label="至少有多少条记录才判断异常" value={editor.config.reports.min_sample_size} description="避免数据太少时误报。" />
            <Field name="income_decline" label="收入下降达到多少比例时提醒" value={editor.config.reports.income_decline} description="0.20 表示 20%。" step="0.01" />
            <Field name="refund_ratio" label="退款比例达到多少时提醒" value={editor.config.reports.refund_ratio} description="0.10 表示 10%。" step="0.01" />
            <Field name="expense_growth" label="支出增长达到多少比例时提醒" value={editor.config.reports.expense_growth} description="0.20 表示 20%。" step="0.01" />
            <Field name="outstanding" label="待收金额达到多少元时提醒" value={editor.config.reports.outstanding} description="按报告生成时的待收余额判断。" step="0.01" />
            <Field name="cancellation_rate" label="取消比例达到多少时提醒" value={editor.config.reports.cancellation_rate} description="0.10 表示 10%。" step="0.01" />
            <Field name="low_utilization" label="利用率低于多少时提醒" value={editor.config.reports.low_utilization} description="0.30 表示 30%。" step="0.01" />
            <Field name="coach_pending" label="待结教练费达到多少元时提醒" value={editor.config.reports.coach_pending} description="按报告生成时的待结余额判断。" step="0.01" />
          </Group>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-primary" disabled={isSaving}>{isSaving ? "正在保存…" : editor.kind === "edit" ? "保存草稿" : "创建草稿"}</button>
            <button className="btn" type="reset">恢复打开时的设置</button>
          </div>
        </form>
      ) : null}
      {policies.error ? <p className="mt-2 text-xs text-red-600">{policies.error.message}</p> : null}
      {mutationError ? <p className="mt-2 text-xs text-red-600">{mutationError.message}</p> : null}
    </section>
  );
}
