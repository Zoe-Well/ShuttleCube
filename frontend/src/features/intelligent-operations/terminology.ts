const labels = (
  values: Record<string, string>,
  value: string | null | undefined,
  fallback = "其他",
) => (value && values[value]) || fallback;

export const severityLabel = (value: string) => labels({
  critical: "紧急",
  high: "高",
  medium: "中",
  low: "低",
  info: "提示",
}, value, "未知优先级");

export const runStateLabel = (value: string | null | undefined) => labels({
  queued: "等待处理",
  claimed: "准备处理中",
  running: "正在处理",
  waiting_approval: "等待审批",
  awaiting_approval: "等待审批",
  waiting_human: "等待人工处理",
  retry_scheduled: "等待重试",
  succeeded: "已完成",
  failed: "处理失败",
  escalated: "需要人工处理",
  cancelled: "已取消",
  uncertain: "结果待核对",
}, value, "状态未知");

export const caseStateLabel = (value: string) => labels({
  open: "待处理",
  analyzing: "正在分析",
  assigned: "已有处理人",
  in_progress: "处理中",
  action_proposed: "已有处理方案",
  executing: "正在执行",
  verifying: "正在核对结果",
  monitoring: "持续跟进中",
  waiting_human: "等待人工处理",
  waiting_approval: "等待审批",
  awaiting_approval: "等待审批",
  resolved: "已解决",
  dismissed: "已关闭",
  escalated: "需要重点处理",
}, value, "状态未知");

export const caseTypeLabel = (value: string) => labels({
  attendance_overdue: "逾期未考勤",
  class_replacement_pending: "取消课程待补排",
  receivable_followup: "欠费跟进",
  fixed_class_renewal: "固定班续费提醒",
  private_package_renewal: "私教课包续费提醒",
  reconciliation_failure: "数据核对异常",
}, value, "其他待处理事项");

export const approvalStateLabel = (value: string) => labels({
  pending: "等待审批",
  approved: "已批准",
  rejected: "已拒绝",
  expired: "已过期",
  stale: "方案已失效",
  cancelled: "已取消",
}, value, "审批状态未知");

export const outcomeLabel = (value: string) => labels({
  reached: "已联系",
  no_answer: "未接通",
  promised_payment: "承诺付款",
  paid_elsewhere: "已通过其他方式付款",
  renewed: "已续费",
  follow_later: "稍后跟进",
  disputed: "对账有异议",
  no_intent: "暂无意向",
  invalid_contact: "联系方式无效",
  other: "其他",
  passed: "核对通过",
  failed: "核对未通过",
  indeterminate: "暂时无法判断",
  resolved: "核对通过",
}, value, "其他结果");

export const workflowLabel = (value: string) => labels({
  "operations.scan.v1": "运营问题检查",
  "operations.brief.v1": "运营概览更新",
  "operations.revenue_analysis.v1": "收入跟进分析",
  "operations.replacement_candidates.v1": "查找补排时间",
  "operations.replacement_execute.v1": "课程补排执行",
  "operations.report.v1": "经营报告生成",
  "operations.report_narrative.v1": "AI 报告总结",
  "operations.reconciliation_explanation.v1": "数据异常分析",
  "operations.human_tool.v1": "人工确认操作",
}, value, "其他处理流程");

export const eventTypeLabel = (value: string) => labels({
  scan_started: "开始检查",
  case_created: "发现新的待处理事项",
  case_refreshed: "待处理事项信息已更新",
  case_verified: "已核对处理结果",
  scan_completed: "检查完成",
  business_audit_linked: "已关联业务操作记录",
}, value, "其他处理记录");

export const actorTypeLabel = (value: string) => labels({
  user: "人工操作",
  system: "系统自动处理",
  model: "AI 辅助",
}, value, "系统处理");

export const dataSufficiencyLabel = (value: string) => labels({
  sufficient: "数据充足",
  insufficient: "数据不足",
}, value, "数据状态未知");

export const recommendationPriorityLabel = (value: string) => labels({
  high: "优先处理",
  medium: "建议关注",
  low: "可择机处理",
}, value, "建议关注");

export const evidenceFactLabel = (value: string) => labels({
  reconciliation: "核对详情",
  failure_count: "连续发现次数",
  automatic_repair_available: "是否支持自动修复",
  class_session_id: "课程记录",
  fixed_class_id: "固定班记录",
  fixed_class_name: "固定班名称",
  class_name: "班级名称",
  sequence_number: "课程序号",
  scheduled_end: "原定结束时间",
  grace_hours: "考勤宽限时间（小时）",
  overdue_hours: "已逾期时间（小时）",
  attendance_finalized: "考勤是否完成",
  cancelled_session_id: "取消课程记录",
  original_start: "原定开始时间",
  original_end: "原定结束时间",
  duration_minutes: "课程时长（分钟）",
  coach_ids: "教练",
  court_ids: "场地",
  required_court_count: "所需场地数",
  student_availability_verified: "是否已确认学员时间",
  receivable_id: "应收记录",
  source_type: "业务来源类型",
  source_id: "业务来源记录",
  aging_days: "欠费天数",
  actual_receivable: "实际应收",
  received: "已收金额",
  refunded: "已退金额",
  outstanding: "待收金额",
  payment_status: "付款状态",
  latest_session_end: "最后一节课时间",
  remaining_scheduled_sessions: "剩余课程数",
  active_enrollments: "有效报名人数",
  session_count: "课程总数",
  private_package_id: "私教课包记录",
  student_id: "学员记录",
  coach_id: "教练记录",
  valid_until: "有效期至",
  remaining_units: "剩余课时",
  expiry_due: "是否临近到期",
  units_due: "是否达到余量提醒条件",
}, value, "其他信息");

export function displayOperationValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (value == null) return "—";
  if (Array.isArray(value)) return value.length ? value.map(displayOperationValue).join("、") : "无";
  if (typeof value === "object") return "详细信息请在对应业务页面中查看";
  return String(value);
}
