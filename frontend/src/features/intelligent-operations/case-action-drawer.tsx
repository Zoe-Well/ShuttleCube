import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, PlayCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { Drawer } from "@/components/operations/drawer";
import { AttendancePanel } from "@/features/classes/attendance-panel";
import { FixedClassRenewalForm } from "@/features/classes/fixed-class-renewal-form";
import { NoEnrollmentSessionPanel } from "@/features/classes/no-enrollment-session-panel";
import { ReceivableDetail } from "@/features/finance/receivable-detail";
import { PackageRenewalForm } from "@/features/private-lessons/package-renewal-form";
import { formatBeijingDateTime, formatBeijingTime } from "@/lib/beijing-time";
import {
  type OperationCase,
  useCaseActionContext,
  verifyOperationCaseNow,
} from "./api";
import { buildCaseEvidenceItems } from "./case-evidence";
import { ReconciliationPanel } from "./reconciliation-panel";
import { ReplacementCandidates } from "./replacement-candidates";
import { RevenueRetentionPanel } from "./revenue-retention-panel";

const actionLabels: Record<string, string> = {
  attendance_overdue: "处理本节课考勤",
  receivable_followup: "处理欠费跟进",
  fixed_class_renewal: "办理固定班续期",
  private_package_renewal: "办理私教课包续费",
  class_replacement_pending: "处理课程补排",
  reconciliation_failure: "核对并处理异常",
};

const completionDescriptions: Record<string, string> = {
  attendance_overdue: "保存本节课考勤后，系统会立即核对并自动关闭事项。",
  receivable_followup: "登记实际收款后，待收金额为零时事项会自动解决；联系结果可直接记录在本窗口。",
  fixed_class_renewal: "新增后续课程后，系统会立即核对是否已完成续期。",
  private_package_renewal: "为同一学员和教练创建新课包后，系统会立即核对是否已完成续费。",
  class_replacement_pending: "选择可用时间、确认协调并通过审批后，系统执行补排并核对结果。",
  reconciliation_failure: "完成安全修正后可重新检查；只有业务数据恢复一致时事项才会解决。",
};

export function CaseActionDrawer({
  item,
  canManage,
}: {
  item: OperationCase;
  canManage: boolean;
}) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const context = useCaseActionContext(item.id, open);
  const verify = useMutation({
    mutationFn: () => verifyOperationCaseNow(item.id),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["operation-case", item.id] }),
        client.invalidateQueries({ queryKey: ["operations-cases"] }),
        client.invalidateQueries({ queryKey: ["operations-brief"] }),
        client.invalidateQueries({ queryKey: ["operation-case-action-context", item.id] }),
      ]);
    },
  });
  const evidence = buildCaseEvidenceItems(item).slice(0, 6);
  const links = item.business_links?.length
    ? item.business_links
    : (item.evidence.business_links ?? []).map((route) => ({ label: "查看完整业务资料", route }));
  const finishAction = () => verify.mutate();
  const hasNoEnrollment = item.case_type === "attendance_overdue"
    && Number(item.evidence.facts?.active_enrollment_count) === 0;
  const actionLabel = hasNoEnrollment
    ? "处理零学员课程"
    : actionLabels[item.case_type];
  const completionDescription = hasNoEnrollment
    ? "确认本节没有实际开课后，将其标记为未开课，系统会释放排期并自动关闭事项。"
    : completionDescriptions[item.case_type];

  if (!canManage || !actionLabels[item.case_type]) return null;
  return (
    <>
      <section className="panel border-emerald-200 bg-emerald-50/30 p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 font-semibold"><PlayCircle size={18} />下一步处理</h2>
            <p className="mt-1 text-sm text-slate-600">{completionDescription}</p>
          </div>
          <button className="btn btn-primary" onClick={() => setOpen(true)}>{actionLabel}</button>
        </div>
      </section>
      <Drawer
        open={open}
        wide
        title={actionLabel}
        description={item.title}
        onClose={() => setOpen(false)}
      >
        <div className="mb-5 rounded-xl border border-emerald-100 bg-emerald-50/50 p-4">
          <div className="text-xs font-semibold text-emerald-800">当前案件</div>
          {item.business_summary ? <p className="mt-1 text-sm text-slate-700">{item.business_summary}</p> : null}
          {evidence.length ? (
            <dl className="mt-3 grid gap-2 sm:grid-cols-2">
              {evidence.map((entry) => (
                <div className="rounded-md bg-white/80 p-2" key={entry.label}>
                  <dt className="text-[11px] text-slate-500">{entry.label}</dt>
                  <dd className="mt-0.5 text-sm font-medium">{entry.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          <p className="mt-3 text-xs text-emerald-800">完成标准：{completionDescription}</p>
        </div>

        {context.isPending ? <p className="text-sm text-slate-500">正在准备当前事项的处理信息…</p> : null}
        {context.error ? <p className="text-sm text-red-600">{context.error.message}</p> : null}
        {context.data?.kind === "attendance" ? (
          <div className="space-y-4">
            <div className="rounded-lg bg-slate-50 p-4 text-sm">
              <strong>{context.data.session.fixed_class_name} · 第 {context.data.session.sequence_number} 节</strong>
              <p className="mt-1 text-slate-600">
                {formatBeijingDateTime(context.data.session.scheduled_start)} 至 {formatBeijingTime(context.data.session.scheduled_end)}
              </p>
            </div>
            {context.data.enrollments.length ? (
              <AttendancePanel sessionId={context.data.session.id} enrollments={context.data.enrollments} onDone={finishAction} />
            ) : (
              <NoEnrollmentSessionPanel
                sessionId={context.data.session.id}
                version={context.data.session.version}
                onDone={finishAction}
              />
            )}
          </div>
        ) : null}
        {context.data?.kind === "receivable" ? (
          <div className="space-y-5">
            <RevenueRetentionPanel item={item} />
            <ReceivableDetail receivableId={context.data.receivable_id} collectionOnly onChanged={finishAction} />
          </div>
        ) : null}
        {context.data?.kind === "fixed_class_renewal" ? (
          <div className="space-y-5">
            <RevenueRetentionPanel item={item} />
            <section className="rounded-xl border p-4">
              <h3 className="font-semibold">为 {context.data.fixed_class.name} 办理续期</h3>
              <p className="mb-4 mt-1 text-xs text-slate-500">新增课程计划，并选择需要同步增加课时和应收的学员。</p>
              <FixedClassRenewalForm
                classId={context.data.fixed_class.id}
                version={context.data.fixed_class.version}
                enrollments={context.data.enrollments}
                onDone={finishAction}
              />
            </section>
          </div>
        ) : null}
        {context.data?.kind === "private_package_renewal" ? (
          <div className="space-y-5">
            <RevenueRetentionPanel item={item} />
            <section className="rounded-xl border p-4">
              <h3 className="font-semibold">创建续费课包</h3>
              <p className="mb-4 mt-1 text-xs text-slate-500">当前案件的学员和教练已经带入，只需确认新课包内容。</p>
              <PackageRenewalForm
                studentId={context.data.package.student_id}
                studentName={context.data.package.student_name}
                coachId={context.data.package.coach_id}
                coachName={context.data.package.coach_name}
                defaultUnitPrice={Number(context.data.package.unit_price)}
                onDone={finishAction}
              />
            </section>
          </div>
        ) : null}
        {context.data?.kind === "replacement" ? <ReplacementCandidates item={item} /> : null}
        {context.data?.kind === "reconciliation" ? <ReconciliationPanel item={item} /> : null}

        {verify.isPending ? <p className="mt-4 text-sm text-slate-500">操作已保存，正在重新核对案件…</p> : null}
        {verify.data ? (
          <p className="mt-4 flex items-center gap-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
            <CheckCircle2 size={16} />核对完成：{verify.data.state === "resolved" ? "事项已解决" : "仍需继续处理"}
          </p>
        ) : null}
        {verify.error ? <p className="mt-4 text-sm text-red-600">重新核对失败：{verify.error.message}</p> : null}

        {links.length ? (
          <details className="mt-6 border-t pt-4">
            <summary className="cursor-pointer text-xs text-slate-500">需要更多资料？</summary>
            <div className="mt-3 flex flex-wrap gap-2">
              {links.map((link) => <Link className="btn" key={link.route} to={link.route}><ExternalLink size={14} />{link.label}</Link>)}
            </div>
          </details>
        ) : null}
      </Drawer>
    </>
  );
}
