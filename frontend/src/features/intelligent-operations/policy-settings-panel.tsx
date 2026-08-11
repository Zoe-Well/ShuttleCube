import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent, ReactNode } from "react";

import { hasOperationsCapability } from "./access-control";
import {
  activateOperationsPolicy,
  createOperationsPolicyDraft,
  listOperationsPolicies,
  type OperationsContext,
  type OperationsPolicyConfig,
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

function Field({ name, label, value, step = "1" }: { name: string; label: string; value: number | string; step?: string }) {
  return (
    <label className="text-xs font-medium">
      {label}
      <input className="field mt-1" defaultValue={value} min="0" name={name} required step={step} type="number" />
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

export function PolicySettingsPanel({ context }: { context: OperationsContext }) {
  const client = useQueryClient();
  const canManage = hasOperationsCapability(context, "operations.policy.manage");
  const policies = useQuery({
    queryKey: ["operations-policies"],
    queryFn: listOperationsPolicies,
    enabled: canManage,
  });
  const createDraft = useMutation({
    mutationFn: createOperationsPolicyDraft,
    onSuccess: () => client.invalidateQueries({ queryKey: ["operations-policies"] }),
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
    createDraft.mutate(configFrom(new FormData(event.currentTarget)));
  };

  return (
    <section className="panel p-5" aria-labelledby="operations-policy-title">
      <h2 id="operations-policy-title" className="font-semibold">运营规则</h2>
      <p className="mt-1 text-xs text-slate-500">新规则先保存为草稿，确认后再激活；历史版本不会被覆盖。</p>
      <form className="mt-4 space-y-4" onSubmit={submit}>
        <Group title="欠费与续费">
          <Field name="aging_days" label="欠费触发天数" value={defaults.receivable_followup.aging_days} />
          <Field name="escalation_days" label="欠费升级天数" value={defaults.receivable_followup.escalation_days} />
          <Field name="max_attempts" label="最多跟进次数" value={defaults.receivable_followup.max_attempts} />
          <Field name="fixed_class_days" label="固定班续费提前天数" value={defaults.renewal.fixed_class_days} />
          <Field name="private_package_expiry_days" label="私教到期提前天数" value={defaults.renewal.private_package_expiry_days} />
          <Field name="private_package_remaining_units" label="私教余量阈值" value={defaults.renewal.private_package_remaining_units} />
          <Field name="cadence_days" label="跟进间隔天数" value={defaults.renewal.cadence_days} />
        </Group>
        <Group title="考勤、补排与运行">
          <Field name="grace_hours" label="考勤宽限小时" value={defaults.attendance.grace_hours} />
          <Field name="window_days" label="补排候选窗口天数" value={defaults.replacement.window_days} />
          <Field name="slot_minutes" label="补排时间粒度（分钟）" value={defaults.replacement.slot_minutes} />
          <Field name="case_sla_days" label="案件处理时限（天）" value={defaults.runtime.case_sla_days} />
          <Field name="approval_expiry_minutes" label="审批有效期（分钟）" value={defaults.runtime.approval_expiry_minutes} />
          <Field name="retry_limit" label="运行重试次数" value={defaults.runtime.retry_limit} />
        </Group>
        <Group title="经营报告异常阈值">
          <Field name="min_sample_size" label="最小样本量" value={defaults.reports.min_sample_size} />
          <Field name="income_decline" label="收入下降比例" value={defaults.reports.income_decline} step="0.01" />
          <Field name="refund_ratio" label="退款率" value={defaults.reports.refund_ratio} step="0.01" />
          <Field name="expense_growth" label="支出增长比例" value={defaults.reports.expense_growth} step="0.01" />
          <Field name="outstanding" label="欠费金额阈值" value={defaults.reports.outstanding} step="0.01" />
          <Field name="cancellation_rate" label="取消率" value={defaults.reports.cancellation_rate} step="0.01" />
          <Field name="low_utilization" label="低利用率" value={defaults.reports.low_utilization} step="0.01" />
          <Field name="coach_pending" label="待结教练费阈值" value={defaults.reports.coach_pending} step="0.01" />
        </Group>
        <button className="btn btn-primary" disabled={createDraft.isPending}>保存为新草稿</button>
      </form>
      {createDraft.error ? <p className="mt-2 text-xs text-red-600">{createDraft.error.message}</p> : null}
      <div className="mt-6 space-y-2">
        {policies.data?.map((policy) => (
          <div className="flex items-center justify-between rounded-lg border p-3" key={policy.id}>
            <div>
              <div className="text-sm font-medium">版本 {policy.policy_version}</div>
              <div className="text-xs text-slate-500">{policy.state === "active" ? "当前生效" : policy.state === "draft" ? "草稿" : "历史版本"}</div>
            </div>
            {policy.state === "draft" ? (
              <button className="btn" disabled={activate.isPending} onClick={() => activate.mutate(policy.id)} type="button">激活此版本</button>
            ) : null}
          </div>
        ))}
      </div>
      {policies.error ? <p className="mt-2 text-xs text-red-600">{policies.error.message}</p> : null}
      {activate.error ? <p className="mt-2 text-xs text-red-600">{activate.error.message}</p> : null}
    </section>
  );
}
