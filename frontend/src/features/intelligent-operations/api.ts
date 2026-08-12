import { api } from "../../api/client";
import { useQuery } from "@tanstack/react-query";

export const operationsApiPath = "/operations" as const;

export type OperationsContext = {
  organization: { id: string; name: string };
  venue: { id: string; name: string };
  user_id: string;
  membership_id: string;
  capabilities: string[];
  operations_enabled: boolean;
  write_tools_enabled: boolean;
  model_enabled: boolean;
  policy_status: string;
};

export type OperationsModelSetting = {
  model_enabled: boolean;
  provider_configured: boolean;
  provider_editable: boolean;
  provider_source: "desktop" | "environment" | null;
  provider_verified_at: string | null;
  provider_key: "openai" | "deepseek" | "custom";
  provider_label: string;
  provider_base_url: string;
  provider_api_mode: "responses" | "chat_completions";
  provider_model_profile: string;
  enabled_by: string | null;
  enabled_at: string | null;
  updated_at: string;
  version: number;
};

export type OperationsRuntimeSetting = {
  operations_enabled: boolean;
  write_tools_enabled: boolean;
  updated_at: string;
  version: number;
};

export type OperationsMembership = {
  id: string;
  user_id: string;
  display_name: string;
  status: "active" | "disabled" | "pending_review";
  role_key: "owner" | "operations_manager" | "operator" | "finance_viewer";
  capabilities: string[];
  reviewed_by: string | null;
  reviewed_at: string | null;
  version: number;
};

export type OperationsPolicyConfig = {
  receivable_followup: { aging_days: number; escalation_days: number; max_attempts: number };
  renewal: {
    fixed_class_days: number;
    private_package_expiry_days: number;
    private_package_remaining_units: number;
    cadence_days: number;
  };
  attendance: { grace_hours: number };
  replacement: { window_days: number; slot_minutes: 15 | 30 | 60; resource_mode: "original_only" };
  reports: {
    min_sample_size: number;
    income_decline: string;
    refund_ratio: string;
    expense_growth: string;
    outstanding: string;
    cancellation_rate: string;
    low_utilization: string;
    coach_pending: string;
  };
  runtime: { case_sla_days: number; approval_expiry_minutes: number; retry_limit: number };
};

export type OperationsPolicy = {
  id: string;
  name: string;
  policy_key: "default_operations";
  policy_version: number;
  schema_version: "1";
  config: OperationsPolicyConfig;
  config_hash: string;
  state: "draft" | "active" | "retired";
  effective_from: string;
  effective_to: string | null;
  created_by: string;
  activated_by: string | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
};

export type OperationCase = {
  id: string;
  case_type: string;
  subject_type: string;
  subject_id: string;
  occurrence_no: number;
  severity: "info" | "low" | "medium" | "high" | "critical";
  priority_score: string;
  title: string;
  business_summary: string | null;
  state: string;
  first_detected_at: string;
  last_detected_at: string;
  next_check_at: string | null;
  due_at: string | null;
  queue_key: string;
  required_capability: string;
  assigned_to: string | null;
  assigned_at: string | null;
  assigned_by?: string | null;
  current_run_id: string | null;
  evidence: { facts?: Record<string, unknown>; business_links?: string[] };
  evidence_hash: string;
  resolved_at: string | null;
  dismissed_reason: string | null;
  policy_version?: number;
  version: number;
  activities?: FollowupActivity[];
  latest_runs?: OperationRun[];
  business_links?: Array<{ label: string; route: string }>;
};

export type OperationCasePage = {
  items: OperationCase[];
  next_cursor: string | null;
};

export type CaseActionContext =
  | {
      kind: "attendance";
      session: {
        id: string;
        fixed_class_id: string;
        fixed_class_name: string;
        sequence_number: number;
        scheduled_start: string;
        scheduled_end: string;
        status: string;
        attendance_finalized_at: string | null;
        version: number;
      };
      enrollments: Array<{ id: string; student_id: string; student_name: string }>;
    }
  | ({ kind: "receivable"; receivable_id: string } & FollowupContext)
  | ({
      kind: "fixed_class_renewal";
      fixed_class: { id: string; name: string; version: number; session_count: number };
      enrollments: Array<{ id: string; student_name: string; unit_price: string; status: string }>;
    } & FollowupContext)
  | ({
      kind: "private_package_renewal";
      package: {
        id: string;
        student_id: string;
        student_name: string;
        coach_id: string;
        coach_name: string;
        unit_price: string;
        valid_until: string | null;
      };
    } & FollowupContext)
  | { kind: "replacement"; facts: Record<string, unknown> }
  | ({ kind: "reconciliation" } & ReconciliationContext);

export type CaseVerificationResult = {
  state: string;
  outcome: string;
  reason_code: string;
};

export type OperationsBrief = {
  generated_at: string;
  total: number;
  groups: Array<{
    queue_key: string;
    required_capability: string;
    total: number;
    overdue: number;
    unassigned: number;
    cases: Array<{
      id: string;
      title: string;
      severity: string;
      state: string;
      due_at: string | null;
      assigned_to: string | null;
      next_action: string;
    }>;
  }>;
};

export type OperationRun = {
  id: string;
  case_id: string | null;
  run_type: string;
  workflow_key: string;
  state: string;
  error_code: string | null;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  checkpoint?: {
    workflow_step?: string;
    state?: {
      analysis?: RevenueAnalysis | null;
      reason?: string;
      [key: string]: unknown;
    };
  };
};

export type FollowupContact = {
  available: boolean;
  subject_type?: "student" | "guardian";
  subject_id?: string;
  display_name?: string;
  reason?: string;
};

export type FollowupActivity = {
  id: string;
  case_id: string;
  activity_type: string;
  channel: string;
  outcome_code: string;
  summary: string;
  happened_at: string;
  next_check_at: string | null;
  operated_by: string;
  source: string;
  created_at: string;
};

export type FollowupContext = {
  receivable_id?: string;
  renewal_type?: "fixed_class" | "private_package";
  subject_id?: string;
  amounts?: {
    actual_receivable: string;
    received: string;
    refunded: string;
    net_received: string;
    outstanding: string;
    payment_status: string;
  };
  aging_days?: number;
  end_at?: string | null;
  expires_on?: string | null;
  remaining_scheduled_sessions?: number;
  remaining_units?: number;
  contact: FollowupContact;
  activities: FollowupActivity[];
  next_allowed_followup_at?: string | null;
  renewal_facts?: Record<string, unknown>;
};

export type RevenueAnalysis = {
  summary: string;
  next_actions: string[];
  communication_draft: string | null;
  citations: Array<{ source_ref: string; claim: string }>;
  abstained: boolean;
  abstention_reason: string | null;
};

export type ReportMetric = {
  metric_ref: string;
  metric_key: string;
  scope: "period" | "as_of";
  unit: "cny" | "count" | "lesson_unit" | "hour" | "ratio";
  value: string;
  display_precision: number;
  calculated_at: string;
  data_status: "complete" | "partial" | "insufficient" | "data_quality_issue";
};

export type ReportAnomaly = {
  anomaly_id: string;
  rule_key: string;
  severity: string;
  metric_refs: string[];
  threshold: Record<string, unknown>;
  comparison: Record<string, unknown>;
  evidence: Record<string, unknown>;
  data_sufficiency: "sufficient" | "insufficient";
};

export type OperationsReportSnapshot = {
  id: string;
  run_id: string;
  period_type: "day" | "week" | "month";
  period_start: string;
  period_end: string;
  effective_end: string;
  period_state: "complete" | "in_progress";
  generated_at: string;
  business_timezone: string;
  comparison_status: string;
  evidence_hash: string;
  narrative_state: string;
  metrics: ReportMetric[];
  breakdowns: {
    court_capacity?: {
      method: string;
      totals: Record<string, string>;
      per_court: Array<Record<string, string | string[]>>;
      data_quality: string[];
    };
    comparison_metrics?: ReportMetric[];
    [key: string]: unknown;
  };
  anomalies: ReportAnomaly[];
  narrative: {
    state: string;
    summary: string | null;
    anomaly_explanations: Array<{ text: string }>;
    recommendations: Array<{ text: string; priority: string }>;
    caveats: Array<{ code: string; message: string }>;
    projection_reason?: string;
  };
  access_projection: {
    financial_metrics_included: boolean;
    payroll_metrics_included: boolean;
    omitted_sections: string[];
  };
};

export type ReportSummaryPage = {
  items: Array<Pick<OperationsReportSnapshot, "id" | "run_id" | "period_type" | "period_start" | "period_end" | "effective_end" | "period_state" | "generated_at" | "narrative_state" | "evidence_hash">>;
  next_cursor: string | null;
};

export type OperationEvent = {
  id: string;
  sequence: number;
  event_type: string;
  actor_type: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  occurred_at: string;
};

export type ReplacementResourcePlan = {
  resource_plan_id: string;
  session_id: string;
  session_version: number;
  resource_policy_version: number;
  starts_at: string;
  ends_at: string;
  coach_ids: string[];
  court_ids: string[];
  required_court_count: number;
  conflict_checked_at: string;
  evidence_hash: string;
  expires_at: string;
  student_availability_verified: false;
  ranking_explanation: string | null;
};

export type ReplacementCandidateResult = {
  schema_version: string;
  generated_at: string;
  evidence_hash: string;
  policy_version: number;
  candidates: ReplacementResourcePlan[];
  caveats: string[];
  rejected_counts_by_reason?: Record<string, number>;
};

export type OperationApproval = {
  id: string;
  tool_call_id: string;
  case_id: string | null;
  policy_version: number;
  approval_policy: "explicit_confirmation" | "mandatory_approval";
  risk_level: "low" | "medium" | "high";
  action_summary: string;
  impact_snapshot: Record<string, unknown>;
  input_hash: string;
  subject_versions: Record<string, number>;
  required_capability: string;
  state: "pending" | "approved" | "rejected" | "expired" | "stale" | "cancelled";
  expires_at: string;
  decided_by: string | null;
  decision_reason: string | null;
  decided_at: string | null;
  version: number;
  created_at: string;
};

export type ReplacementProposal = {
  tool_call_id: string;
  state: "awaiting_approval";
  approval: OperationApproval;
};

export type ApprovalDecisionResult = {
  approval: OperationApproval;
  execution_run: {
    id: string;
    case_id: string | null;
    run_type: string;
    workflow_key: string;
    state: string;
    created_at: string;
  } | null;
};

export type ReconciliationInvariant = {
  key: string;
  expected: string;
  actual: string;
  passed: boolean;
};

export type ReconciliationContext = {
  case_id: string;
  case_state: string;
  failure_count: number;
  automatic_repair_available: false;
  deterministic_impact_order: Array<{ key: string; value: unknown }>;
  result: {
    issue_id: string;
    rule_key: string;
    rule_version: number;
    compatible_from_version: number;
    result: "failed" | "passed" | "indeterminate";
    severity: "low" | "medium" | "high" | "critical";
    subject_type: string;
    subject_id: string;
    affected_refs: Array<{ kind: string; id: string; version: number | null }>;
    invariants: ReconciliationInvariant[];
    impact: {
      affected_amount: string;
      affected_lesson_units: number;
      affected_schedules: number;
      downstream_records: number;
    };
    repair_entry_points: Array<{ label: string; route: string }>;
    automatic_repair_available: false;
  };
};

export function getOperationsContext(): Promise<OperationsContext> {
  return api<OperationsContext>(`${operationsApiPath}/context`);
}

export function useOperationsContext() {
  return useQuery({ queryKey: ["operations-context"], queryFn: getOperationsContext });
}

export function useOperationCases(filters: { queue?: string; states?: string[] } = {}) {
  const parameters = new URLSearchParams();
  if (filters.queue) parameters.set("queue_key", filters.queue);
  filters.states?.forEach((state) => parameters.append("state", state));
  const query = parameters.toString();
  return useQuery({
    queryKey: ["operations-cases", filters],
    queryFn: () => api<OperationCasePage>(`${operationsApiPath}/cases${query ? `?${query}` : ""}`),
    select: (data) => data.items,
  });
}

export function useOperationCase(caseId?: string) {
  return useQuery({
    queryKey: ["operation-case", caseId],
    queryFn: () => api<OperationCase>(`${operationsApiPath}/cases/${caseId}`),
    enabled: Boolean(caseId),
  });
}

export function useCaseActionContext(caseId?: string, enabled = true) {
  return useQuery({
    queryKey: ["operation-case-action-context", caseId],
    queryFn: () => api<CaseActionContext>(`${operationsApiPath}/cases/${caseId}/action-context`),
    enabled: Boolean(caseId) && enabled,
  });
}

export function verifyOperationCaseNow(caseId: string): Promise<CaseVerificationResult> {
  return api<CaseVerificationResult>(`${operationsApiPath}/cases/${caseId}:verify`, {
    method: "POST",
  });
}

export function useOperationsBrief() {
  return useQuery({
    queryKey: ["operations-brief"],
    queryFn: () => api<OperationsBrief>(`${operationsApiPath}/brief`),
  });
}

export function useOperationRun(runId?: string | null) {
  return useQuery({
    queryKey: ["operation-run", runId],
    queryFn: () => api<OperationRun>(`${operationsApiPath}/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data && ["succeeded", "failed", "escalated", "cancelled"].includes(query.state.data.state)
        ? false
        : 1500,
  });
}

export function useOperationRunEvents(runId?: string | null) {
  return useQuery({
    queryKey: ["operation-run-events", runId],
    queryFn: () => api<OperationEvent[]>(`${operationsApiPath}/runs/${runId}/events`),
    enabled: Boolean(runId),
    refetchInterval: 2000,
  });
}

export function useFollowupContext(caseId?: string) {
  return useQuery({
    queryKey: ["operation-followup-context", caseId],
    queryFn: () =>
      api<FollowupContext>(`${operationsApiPath}/cases/${caseId}/followup-context`),
    enabled: Boolean(caseId),
  });
}

export function useReconciliationContext(caseId?: string) {
  return useQuery({
    queryKey: ["operation-reconciliation-context", caseId],
    queryFn: () =>
      api<ReconciliationContext>(
        `${operationsApiPath}/cases/${caseId}/reconciliation-context`,
      ),
    enabled: Boolean(caseId),
  });
}

export function generateReplacementCandidates(
  item: OperationCase,
  input: { window_start: string; window_end: string; max_candidates?: number },
): Promise<ReplacementCandidateResult> {
  return api(`${operationsApiPath}/cases/${item.id}/replacement-candidates`, {
    method: "POST",
    body: JSON.stringify({
      ...input,
      expected_case_version: item.version,
      max_candidates: input.max_candidates ?? 20,
    }),
  });
}

export function proposeReplacement(
  item: OperationCase,
  resourcePlanId: string,
): Promise<ReplacementProposal> {
  return api(`${operationsApiPath}/cases/${item.id}/replacement-proposals`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      resource_plan_id: resourcePlanId,
      coordination_confirmed: true,
      expected_case_version: item.version,
    }),
  });
}

export function useOperationApprovals(
  states: OperationApproval["state"][] = ["pending"],
  enabled = true,
) {
  const parameters = new URLSearchParams();
  states.forEach((state) => parameters.append("state", state));
  return useQuery({
    queryKey: ["operation-approvals", states],
    queryFn: () =>
      api<OperationApproval[]>(`${operationsApiPath}/approvals?${parameters.toString()}`),
    enabled,
  });
}

export function decideOperationApproval(
  approval: OperationApproval,
  approve: boolean,
  reason: string,
): Promise<ApprovalDecisionResult> {
  return api(
    `${operationsApiPath}/approvals/${approval.id}:${approve ? "approve" : "reject"}`,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({
        expected_approval_version: approval.version,
        expected_input_hash: approval.input_hash,
        reason,
      }),
    },
  );
}

export function analyzeOperationCase(caseId: string): Promise<{ run_id: string; state: string }> {
  return api(`${operationsApiPath}/cases/${caseId}:analyze`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({}),
  });
}

export function recordFollowupActivity(
  item: OperationCase,
  input: {
    activity_type: "contact_result" | "note";
    channel: "phone" | "wechat" | "in_person" | "other" | "none";
    contact_subject_type?: "student" | "guardian";
    contact_subject_id?: string;
    outcome_code:
      | "reached"
      | "no_answer"
      | "promised_payment"
      | "paid_elsewhere"
      | "renewed"
      | "no_intent"
      | "follow_later"
      | "disputed"
      | "invalid_contact"
      | "other";
    summary: string;
    happened_at: string;
    next_check_at?: string;
  },
): Promise<FollowupActivity> {
  return api(`${operationsApiPath}/cases/${item.id}/activities`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      ...input,
      contact_subject_type: input.contact_subject_type ?? null,
      contact_subject_id: input.contact_subject_id ?? null,
      next_check_at: input.next_check_at || null,
      expected_case_version: item.version,
      expected_occurrence_no: item.occurrence_no,
      confirmed_by_user: true,
    }),
  });
}

export function useOperationsReports(periodType?: "day" | "week" | "month") {
  const query = periodType ? `?period_type=${periodType}` : "";
  return useQuery({
    queryKey: ["operations-reports", periodType],
    queryFn: () => api<ReportSummaryPage>(`${operationsApiPath}/reports${query}`),
  });
}

export function useOperationsReport(reportId?: string | null) {
  return useQuery({
    queryKey: ["operations-report-snapshot", reportId],
    queryFn: () =>
      api<OperationsReportSnapshot>(`${operationsApiPath}/reports/${reportId}`),
    enabled: Boolean(reportId),
    refetchInterval: (query) =>
      query.state.data?.narrative.state === "queued" ? 1500 : false,
  });
}

export function generateOperationsReport(input: {
  period_type: "day" | "week" | "month";
  anchor_date: string;
  include_narrative: boolean;
}): Promise<{ run_id: string; state: string }> {
  return api(`${operationsApiPath}/reports`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function retryOperationsReportNarrative(
  reportId: string,
): Promise<{ run_id: string; state: string }> {
  return api(`${operationsApiPath}/reports/${reportId}/narrative:retry`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({}),
  });
}

export function startOperationsScan(
  detectorKeys: string[] | null = null,
): Promise<{ run_id: string; state: string }> {
  return api(`${operationsApiPath}/scans`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ detector_keys: detectorKeys }),
  });
}

export function claimOperationCase(value: OperationCase): Promise<OperationCase> {
  return api(`${operationsApiPath}/cases/${value.id}:claim`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ expected_case_version: value.version }),
  });
}

export function assignOperationCase(
  value: OperationCase,
  assigneeMembershipId: string,
  reason: string,
): Promise<OperationCase> {
  return api(`${operationsApiPath}/cases/${value.id}:assign`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      expected_case_version: value.version,
      assignee_membership_id: assigneeMembershipId,
      reason,
    }),
  });
}

export function dismissOperationCase(value: OperationCase, reason: string): Promise<OperationCase> {
  return api(`${operationsApiPath}/cases/${value.id}:dismiss`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ expected_case_version: value.version, reason }),
  });
}

export function getOperationsModelSetting(): Promise<OperationsModelSetting> {
  return api<OperationsModelSetting>(`${operationsApiPath}/settings/model`);
}

export function getOperationsRuntimeSetting(): Promise<OperationsRuntimeSetting> {
  return api<OperationsRuntimeSetting>(`${operationsApiPath}/settings/runtime`);
}

export function updateOperationsRuntimeSetting(input: {
  operations_enabled: boolean;
  write_tools_enabled: boolean;
  reason?: string;
  expected_version: number;
}): Promise<OperationsRuntimeSetting> {
  return api<OperationsRuntimeSetting>(`${operationsApiPath}/settings/runtime`, {
    method: "PATCH",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function updateOperationsModelSetting(input: {
  model_enabled: boolean;
  reason?: string;
  expected_version: number;
}): Promise<OperationsModelSetting> {
  return api<OperationsModelSetting>(`${operationsApiPath}/settings/model`, {
    method: "PATCH",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function configureOperationsModelCredential(
  input: {
    provider: "openai" | "deepseek" | "custom";
    base_url: string;
    api_mode: "responses" | "chat_completions";
    model_profile: string;
    api_key: string;
  },
): Promise<OperationsModelSetting> {
  return api<OperationsModelSetting>(`${operationsApiPath}/settings/model/credential`, {
    method: "PUT",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function deleteOperationsModelCredential(): Promise<OperationsModelSetting> {
  return api<OperationsModelSetting>(`${operationsApiPath}/settings/model/credential`, {
    method: "DELETE",
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
}

export function listOperationsMemberships(): Promise<OperationsMembership[]> {
  return api<OperationsMembership[]>(`${operationsApiPath}/memberships`);
}

export function updateOperationsMembership(
  membershipId: string,
  input: {
    status: "active" | "disabled";
    role_key: OperationsMembership["role_key"];
    reason: string;
    expected_version: number;
  },
): Promise<OperationsMembership> {
  return api<OperationsMembership>(`${operationsApiPath}/memberships/${membershipId}`, {
    method: "PATCH",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(input),
  });
}

export function listOperationsPolicies(): Promise<OperationsPolicy[]> {
  return api<OperationsPolicy[]>(`${operationsApiPath}/policies`);
}

export function createOperationsPolicyDraft(
  input: { name: string; config: OperationsPolicyConfig },
): Promise<OperationsPolicy> {
  return api<OperationsPolicy>(`${operationsApiPath}/policies`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ name: input.name, schema_version: "1", config: input.config }),
  });
}

export function getOperationsPolicy(policyId: string): Promise<OperationsPolicy> {
  return api<OperationsPolicy>(`${operationsApiPath}/policies/${policyId}`);
}

export function updateOperationsPolicyDraft(
  policy: OperationsPolicy,
  input: { name: string; config: OperationsPolicyConfig },
): Promise<OperationsPolicy> {
  return api<OperationsPolicy>(`${operationsApiPath}/policies/${policy.id}`, {
    method: "PATCH",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ ...input, expected_version: policy.version }),
  });
}

export function copyOperationsPolicyDraft(
  policy: OperationsPolicy,
  name: string,
): Promise<OperationsPolicy> {
  return api<OperationsPolicy>(`${operationsApiPath}/policies/${policy.id}:copy`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ name }),
  });
}

export function deleteOperationsPolicyDraft(policy: OperationsPolicy): Promise<void> {
  return api<void>(`${operationsApiPath}/policies/${policy.id}?expected_version=${policy.version}`, {
    method: "DELETE",
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
}

export function activateOperationsPolicy(policy: OperationsPolicy): Promise<OperationsPolicy> {
  return api<OperationsPolicy>(`${operationsApiPath}/policies/${policy.id}:activate`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ expected_version: policy.version }),
  });
}
