import type { OperationCase } from "./api";
import { formatBeijingDateTime } from "@/lib/beijing-time";

export type EvidenceItem = { label: string; value: string };
type Field = { key: string; label: string; format?: (value: unknown) => string };

const dateTime = (value: unknown) => {
  if (typeof value !== "string" || !value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : formatBeijingDateTime(parsed);
};
const yesNo = (value: unknown) => value === true ? "是" : value === false ? "否" : "—";
const count = (value: unknown) => Array.isArray(value) ? String(value.length) : String(value ?? "—");
const money = (value: unknown) => {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(amount)
    : String(value ?? "—");
};
const sourceType = (value: unknown) => ({
  enrollment: "固定班报名",
  private_lesson_package: "私教课包",
  venue_booking: "场地预订",
  event: "活动",
}[String(value)] ?? "其他业务");
const paymentStatus = (value: unknown) => ({
  open: "待付款",
  partial: "部分付款",
  settled: "已结清",
  cancelled: "已取消",
  refunded: "已退款",
}[String(value)] ?? "状态未知");

const fieldsByCaseType: Record<string, Field[]> = {
  attendance_overdue: [
    { key: "fixed_class_name", label: "固定班" },
    { key: "sequence_number", label: "课程序号" },
    { key: "scheduled_end", label: "原定结束时间", format: dateTime },
    { key: "overdue_hours", label: "已逾期（小时）" },
    { key: "attendance_finalized", label: "考勤已完成", format: yesNo },
    { key: "active_enrollment_count", label: "当前报名人数" },
    { key: "grace_hours", label: "考勤宽限时间（小时）" },
  ],
  class_replacement_pending: [
    { key: "fixed_class_name", label: "固定班" },
    { key: "original_start", label: "原开始时间", format: dateTime },
    { key: "original_end", label: "原结束时间", format: dateTime },
    { key: "duration_minutes", label: "课程时长（分钟）" },
    { key: "required_court_count", label: "所需场地数" },
    { key: "coach_ids", label: "教练数量", format: count },
    { key: "court_ids", label: "场地数量", format: count },
    { key: "student_availability_verified", label: "已确认学员时间", format: yesNo },
  ],
  receivable_followup: [
    { key: "source_type", label: "业务来源", format: sourceType },
    { key: "aging_days", label: "欠费天数" },
    { key: "actual_receivable", label: "应收金额", format: money },
    { key: "received", label: "已收金额", format: money },
    { key: "refunded", label: "退款金额", format: money },
    { key: "outstanding", label: "待收金额", format: money },
    { key: "payment_status", label: "付款状态", format: paymentStatus },
  ],
  fixed_class_renewal: [
    { key: "class_name", label: "班级名称" },
    { key: "fixed_class_name", label: "班级名称" },
    { key: "latest_session_end", label: "最后一节课时间", format: dateTime },
    { key: "remaining_scheduled_sessions", label: "剩余课程数" },
    { key: "active_enrollments", label: "有效报名人数" },
    { key: "session_count", label: "课程总数" },
  ],
  private_package_renewal: [
    { key: "valid_until", label: "有效期至", format: dateTime },
    { key: "remaining_units", label: "剩余课时" },
    { key: "expiry_due", label: "临近到期", format: yesNo },
    { key: "units_due", label: "达到余课提醒条件", format: yesNo },
  ],
};

export function buildCaseEvidenceItems(item: OperationCase): EvidenceItem[] {
  const facts = item.evidence.facts ?? {};
  if (item.case_type === "reconciliation_failure") {
    const reconciliation = facts.reconciliation;
    const result = reconciliation && typeof reconciliation === "object"
      ? reconciliation as Record<string, unknown>
      : {};
    const impactValue = result.impact;
    const impact = impactValue && typeof impactValue === "object"
      ? impactValue as Record<string, unknown>
      : {};
    return [
      { label: "影响金额", value: money(impact.affected_amount) },
      { label: "影响课时", value: String(impact.affected_lesson_units ?? "—") },
      { label: "影响排期", value: String(impact.affected_schedules ?? "—") },
      { label: "关联记录数", value: String(impact.downstream_records ?? "—") },
      { label: "连续发现次数", value: String(facts.failure_count ?? "—") },
    ];
  }
  const seen = new Set<string>();
  return (fieldsByCaseType[item.case_type] ?? []).flatMap((field) => {
    if (!(field.key in facts) || facts[field.key] == null || seen.has(field.label)) return [];
    seen.add(field.label);
    const value = facts[field.key];
    return [{ label: field.label, value: field.format ? field.format(value) : String(value) }];
  });
}
