# Data Model: 智能运营系统

## Modeling Conventions

- 全部新实体使用现有 UUID string ID、UTC 时间点和 SQLAlchemy version 乐观锁约定。
- `organization_id` 和 `venue_id` 是安全作用域，不是展示筛选条件；请求、查询、Tool 和 Runtime 必须先校验 Scope。
- 金额使用 `Numeric(12,2)`／Decimal；比例保存 Decimal 字符串或明确精度的数值，模型不得使用浮点重算。
- 可审计 payload 使用 JSON，但写入前必须通过版本化 Pydantic Schema；未知字段拒绝。
- 业务记录取消、作废和状态变化不物理删除；OperationEvent、CaseActivity、ToolCall、Approval 和报告版本保留历史。
- 时段采用 `[starts_at, ends_at)`；业务日、自然周和自然月由对应 Venue.timezone 解释。
- 任何跨 Scope 外键或业务引用均无效；即使 ID 存在，也对当前请求表现为不存在。

## 1. Organization and Access Scope

### Organization

独立经营主体，也是未来 SaaS 数据隔离的上层边界。

**Fields**: `id`, `name`, `status(active|suspended)`, `created_at`, `updated_at`, `version`.

**Constraints**:

- 第一版每个部署创建一个默认 Organization。
- suspended Organization 不能领取新 Run 或执行 Tool，但历史数据可按授权只读。

### Venue（existing, extended）

**Added fields**: `organization_id`, `active_for_operations`, `model_enabled(default false)`, `model_enabled_by?`, `model_enabled_at?`.

**Constraints**:

- `organization_id` 非空并指向 Organization。
- 第一版一个部署只允许一个 `active_for_operations=true` 的 Venue；不提供切换 UI。
- 新建与迁移 Venue 的 `model_enabled` 一律为 false；provider 凭据存在不得改变该值。只有具备 `operations.model.manage` 的 active 成员可修改，并写 AuditLog。
- 时区和营业时间仍由 Venue 保存，所有业务 Query 必须按传入 venue_id 读取，不得取第一条记录。

### AI provider credential（installation setting, not a database entity）

- `model_enabled` 是每个 Venue 独立的 AI 服务开关；API Key 验证或保存成功不得自动修改该开关。
- Windows 桌面版将 AI API Key 以当前 Windows 用户范围的 DPAPI 密文保存在安装数据目录；供应商、基础地址、协议、模型名称和验证时间作为非敏感元数据保存。明文不得写入数据库、日志、Trace、AuditLog 或 API 响应。
- 服务端／浏览器部署只从部署环境读取凭据，管理页面仅显示是否已配置，不提供录入、替换或删除入口。
- 桌面版先验证新 Key，再替换已有密文；验证失败必须保留原有可用 Key。移除桌面 Key 时，同时关闭当前 Venue 的 `model_enabled`。
- 运行时统一通过凭据解析器读取桌面密文或部署环境，不将凭据传入业务数据模型、Agent Context 或 Tool 输入。

### OrganizationMembership

**Fields**: `id`, `organization_id`, `user_id`, `status(pending_review|active|disabled)`, `organization_role(owner|admin|member)`, `reviewed_by?`, `reviewed_at?`, `created_at`, `updated_at`, `version`.

**Constraints**:

- `(organization_id, user_id)` 唯一。
- pending_review 用户不能使用任何 Agent 写 Tool。
- 当前 active SystemUser 迁移为默认 Organization 的 pending_review 成员。

### VenueMembership

**Fields**: `id`, `organization_membership_id`, `organization_id`, `venue_id`, `role_key(owner|operations_manager|operator|finance_viewer)`, `status(pending_review|active|disabled)`, `created_at`, `updated_at`, `version`.

**Derived capabilities**: 由版本控制的 capability registry 根据 role_key 解析；数据库不保存可执行脚本或任意权限表达式。Registry 至少区分 `operations.receivable.followup.read`、`operations.report.read`、`operations.report.financial.read`、`operations.payroll.read`、`operations.case.assign`、`operations.model.manage`、审批和排期执行。

**Constraints**:

- `(venue_id, organization_membership_id)` 唯一。
- Venue 必须属于同一 Organization。
- `operations.schedule.execute` 与 `operations.approval.decide` 必须显式存在才能执行补排。
- `finance_viewer` 的财务／工资读取不隐含排期、审批或模型配置；operator／operations_manager 的单笔欠费跟进读取不允许访问全馆利润、工资或结算。

### RequestScope（value object, not a table）

**Fields**: `organization_id`, `venue_id`, `user_id`, `membership_id`, `capabilities`, `resolved_at`.

**Creation**: 只由认证会话和 active Membership 解析；不从请求 body、模型输出或业务备注构造。

## 2. Existing Business Scope Migration

以下是 Scope 所有权，不改变原业务事实口径。

| Scope | Existing aggregates |
|---|---|
| Organization | Student、Guardian、StudentGuardian、WalkInCustomer、CoachProfile、CoachRate、Attachment owner directory |
| Venue operational roots | Court、VenuePriceRule、FixedClass、ClassSession、Enrollment、PrivateLessonPackage、PrivateLesson、VenueBooking、TemporaryEvent、CourtBlock、ScheduleEntry、ScheduleAllocation |
| Venue finance/payroll | Receivable、Payment、Refund、Expense、OtherIncome、CoachFee、PayrollSettlement、LessonUnitLedger、AttendanceRecord |
| Venue security/audit | AuditLog、IdempotencyRecord、所有 Operation 实体 |

**Migration rules**:

1. 创建默认 Organization 并关联现有 Venue。
2. 通过现有强关系和 ScheduleAllocation 推导 organization_id／venue_id；无法唯一推导的行进入 migration_issue 并阻断 Agent feature flag。
3. 对高频、财务、安全和 Operation 表直接保存 Scope；子表即使可从父表推导，也在写入时验证一致。
4. Court code 唯一约束改为 `(venue_id, code)`；业务 source 唯一、fingerprint、idempotency 和报告唯一性全部纳入 Scope。
5. VenueBooking／TemporaryEvent 的 `court_ids_csv` 仅保留兼容显示；场地归属、冲突、候选和利用率只读取 ScheduleAllocation。
6. 回填数量、孤立记录、跨 Scope 关系和 scoped unique 冲突全部为零后，Scope 字段改为非空。

## 3. OperationsPolicy

按 Venue 生效的不可变确定性运营策略版本。

**Fields**:

- `id`, `organization_id`, `venue_id`, `name`;
- `policy_key`（MVP 固定 `default_operations`）, `policy_version`;
- `schema_version`, `config` JSON, `config_hash`;
- `state(draft|active|retired)`, `effective_from`, `effective_to?`;
- `created_by`, `activated_by?`, `activated_at?`, `created_at`.

**Typed config**:

- `receivable_followup`: aging_days、escalation_days、max_attempts；
- `renewal`: fixed_class_days、private_package_expiry_days、private_package_remaining_units、cadence_days；
- `attendance`: grace_hours；
- `replacement`: window_days、slot_minutes、resource_mode(original_only)`；
- `reports`: min_sample_size、income_decline、refund_ratio、expense_growth、outstanding、cancellation_rate、low_utilization、coach_pending；
- `runtime`: case_sla_days、approval_expiry_minutes、retry_limit。

**Constraints**:

- `(venue_id, policy_key, policy_version)` 唯一。
- config 必须通过对应 schema_version；不允许任意表达式、SQL 或代码。
- draft 可重命名、编辑或删除，并通过乐观版本号避免覆盖并发修改；active／retired 不可编辑或删除，修改时复制为新 draft。
- 任意版本均可查看完整配置并复制为带名称的新 draft；创建、编辑、复制、删除和激活全部写 AuditLog。
- 只能从 draft 激活；激活事务必须先将旧 active 标记为 retired 并刷新数据库，再将目标 draft 标记为 active。
- 同一 policy_key 在同一时点只能有一个 active 版本，由应用事务和数据库查询校验共同保证。
- 未配置规则返回 `policy_not_configured`，不创建案件。

## 4. OperationCase

一个 scoped detector／subject 的持续运营问题。

**Fields**:

- `id`, `organization_id`, `venue_id`;
- `case_type`, `subject_type`, `subject_id`, `case_key`;
- `detector_key`, `detector_version`, `policy_key`, `policy_version`;
- `occurrence_no`, `fingerprint`, `evidence_hash`;
- `severity`, `priority_score`, `title`, `business_summary`;
- `state`, `first_detected_at`, `last_detected_at`, `next_check_at?`, `due_at?`;
- `queue_key`, `required_capability`, `assigned_to?`, `assigned_at?`, `assigned_by?`, `created_by_type(system|user)`, `current_run_id?`;
- `resolved_at?`, `resolution_code?`, `version`, `created_at`, `updated_at`.

**Constraints and indexes**:

- `(venue_id, detector_key, subject_type, subject_id)` 唯一；重现问题增加 occurrence_no，不新增活动重复 Case。
- `case_key = hash(organization_id, venue_id, detector_key, subject_type, subject_id)`，不可由模型提供。
- `queue_key` 与 `required_capability` 由版本控制的 case_type registry 决定；LLM 不能选择队列或人员。
- 新案件默认未分配；只有具备 required_capability 的 active Venue 成员可认领，只有具备 `operations.case.assign` 的成员可向其他合格成员分配或改派。
- assignee 被禁用、离开 Venue 或失去 required_capability 时清空分配并回到原队列；未认领不暂停 SLA。
- 认领、分配、改派和退回队列写现有 AuditLog，保存 actor、前后 assignee、原因和时间；OperationEvent 不能替代该责任审计。
- indexes: `(venue_id, queue_key, state, severity, due_at)`, `(venue_id, assigned_to, state)`, `(venue_id, next_check_at)`.
- Detector 只能更新证据、优先级和调度字段；Case state 由状态机转换。

**State transitions**:

```text
open -> analyzing -> action_proposed -> waiting_approval -> executing -> verifying
open|analyzing|action_proposed|verifying -> monitoring
任意非终态 -> waiting_human | escalated
verifying -> resolved
open|waiting_human|monitoring -> dismissed (human reason required)
resolved|dismissed -> open (occurrence_no + 1 and new deterministic evidence)
```

## 5. CaseActivity

人工运营跟进事实，与模型 Trace 分离。

**Fields**:

- `id`, `organization_id`, `venue_id`, `case_id`, `case_occurrence_no`;
- `activity_type(contact_attempt|contact_result|promise|note|status_decision)`;
- `channel(phone|wechat|in_person|other|none)`;
- `contact_subject_type?`, `contact_subject_id?`;
- `outcome_code(reached|no_answer|promised_payment|paid_elsewhere|renewed|no_intent|follow_later|disputed|invalid_contact|other)`;
- `summary`, `happened_at`, `next_check_at?`;
- `operated_by`, `source(manual|run)`, `run_id?`, `created_at`.

**Constraints**:

- 只保存联系人引用和必要脱敏名称，不复制完整电话／微信号。
- `summary` 长度受限并按不可信文本处理。
- promised_payment／reached 不关闭案件；欠费和续费 Verifier 仍读取业务事实。
- `(case_id, created_at)` 和 `(venue_id, operated_by, happened_at)` indexes 支持时间线与工作量查询。

## 6. OperationRun

一次可恢复的分析、计划、报告、执行或复核。

**Fields**:

- `id`, `organization_id`, `venue_id`, `case_id?`, `parent_run_id?`;
- `run_type(scan|brief|case_analysis|report|report_narrative|tool_execution|verification)`;
- `trigger_type(startup|scheduled|manual|retry|approval)`;
- `workflow_key`, `workflow_version`, `policy_key`, `policy_version`;
- `prompt_version?`, `toolset_version`, `model_profile?`;
- `input_refs` JSON, `input_hash`, `checkpoint` JSON;
- `state`, `attempt`, `next_attempt_at?`;
- budgets: `max_steps`, `max_model_calls`, `max_tool_calls`, `max_write_calls`, `deadline_at`;
- counters and `token_usage_summary` JSON;
- `lease_owner?`, `lease_expires_at?`, `error_code?`, `error_summary?`;
- `started_at?`, `finished_at?`, `created_at`, `updated_at`, `version`.

**Constraints**:

- ReportSnapshot 通过 run_id 单向指向生成 Run；Run 不保存 report_snapshot_id。
- report_narrative retry 使用 parent_run_id，input_refs 必须引用原 Snapshot。
- lease 领取使用 state + lease_expires_at + version 条件更新；等待审批时释放 lease。

**State transitions**:

```text
queued -> running
running -> waiting_approval | waiting_human | retry_scheduled
waiting_approval -> queued | cancelled | escalated
retry_scheduled -> queued
running -> succeeded | failed | escalated | cancelled
```

## 7. OperationEvent

**Fields**: `id`, `organization_id`, `venue_id`, `case_id?`, `run_id`, `sequence`, `event_type`, `actor_type(system|user|model|tool)`, `actor_id?`, `trace_id`, `request_id?`, `payload_redacted` JSON, `payload_hash`, `occurred_at`.

**Constraints**:

- `(run_id, sequence)` 唯一且追加后不可更新／删除。
- payload 不保存完整联系方式、凭证 URL、Cookie、密钥或附件正文。
- 业务写必须另有 AuditLog；CaseActivity 必须另有结构化记录。

## 8. OperationToolCall

**Fields**:

- `id`, `organization_id`, `venue_id`, `run_id`, `case_id?`;
- `policy_key`, `policy_version`, `tool_key`, `tool_version`, `risk_level`;
- `normalized_input` JSON, `input_hash`, `impact_snapshot` JSON;
- `subject_versions` JSON, `required_capability`;
- `state(proposed|awaiting_confirmation|awaiting_approval|approved|executing|succeeded|failed|uncertain|cancelled|stale)`;
- `idempotency_key`, `result_reference?`, `result_summary?`, `error_code?`, `attempt`;
- `started_at?`, `finished_at?`, `created_at`, `updated_at`, `version`.

**Constraints**:

- `(venue_id, tool_key, idempotency_key)` 唯一。
- normalized_input 不包含 organization_id／venue_id；Scope 由 Run 注入。
- succeeded ToolCall 不重执行；executing 中断先 outcome reconciliation。
- input、Scope、Policy、权限、影响或 subject version 改变时原 ToolCall stale。

## 9. OperationApproval

**Fields**:

- `id`, `organization_id`, `venue_id`, `tool_call_id`, `case_id?`;
- `policy_key`, `policy_version`, `requested_by`;
- `approval_policy`, `risk_level`, `action_summary`, `impact_snapshot` JSON;
- `input_hash`, `subject_versions` JSON, `required_capability`;
- `state(pending|approved|rejected|expired|stale|cancelled)`;
- `expires_at`, `decided_by?`, `decision_reason?`, `decided_at?`, `version`, `created_at`.

**Constraints**:

- 一个 ToolCall 同时至多一个 pending Approval。
- 参数修改取消旧 ToolCall／Approval 并创建新提议。
- 批准者在执行时仍必须属于相同 Scope 并具备 capability。

## 10. OperationsReportSnapshot

指定日／周／月确定性报告及可选 Narrative。

**Fields**:

- `id`, `organization_id`, `venue_id`, `run_id`;
- `period_type(day|week|month)`, `period_start`, `period_end`, `effective_end`;
- `business_timezone`, `period_state(complete|in_progress)`, `generated_at`, `generated_by`;
- `comparison_start?`, `comparison_end?`, `comparison_status`;
- `policy_key`, `policy_version`, `metric_version`, `anomaly_rule_version`;
- `metrics` JSON, `breakdowns` JSON, `anomalies` JSON, `source_refs` JSON, `evidence_hash`;
- `narrative_state(not_requested|queued|available|unavailable|failed)`;
- `summary?`, `anomaly_explanations?`, `recommendations?`, `caveats?` JSON;
- `narrative_run_id?`, `model_profile?`, `prompt_version?`, `created_at`.

**Metric item**:

- `metric_ref`, `metric_key`, `scope(period|as_of)`, `unit(cny|count|lesson_unit|hour|ratio)`;
- `value` as Decimal／integer string, `display_precision`, `calculated_at`, `source_refs`, `data_status`.

**Utilization metrics**:

- `commercial_usage_hours`, `base_business_hours`, `court_block_unavailable_hours`, `available_hours`, `raw_utilization`, `display_utilization`, `outside_business_hours`, `data_quality_status`.
- raw_utilization 不截断；display_utilization 可限制到 UI 区间但不可覆盖原值。

**Anomaly item**:

- `anomaly_id`, `rule_key`, `severity`, `metric_refs`, `threshold`, `comparison`, `evidence`, `data_sufficiency`.

**Constraints**:

- metrics／breakdowns／anomalies 保存后不可修改。
- 相同 Venue／期间重新生成产生新 Snapshot；旧 Snapshot 不覆盖。
- Narrative 的数字必须引用 metric_ref 并由服务端渲染／校验。
- 模型失败不改变 Snapshot 成功状态。
- Snapshot 可以保存完整确定性指标，但 API、Tool、Narrative 输入和 Trace 展示必须按目标用户 capability 投影；未经授权的 metric、anomaly、breakdown 和 source ref 不得旁路泄露。
- CourtBlock 只按与营业时间重叠的对应场地时间并集扣减 available_hours，不计 commercial_usage_hours；营业时间外 Block 不影响分母。Block 与经营排期异常重叠产生 data-quality evidence，不能重复扣减掩盖冲突。

## 11. ReplacementResourcePlan

确定性候选资源方案。MVP 可存为 Tool Evidence JSON，不要求独立表；一旦用于 Approval，必须冻结在 ToolCall impact_snapshot。

**Fields**: `resource_plan_id`, `organization_id`, `venue_id`, `session_id`, `session_version`, `resource_policy_version`, `starts_at`, `ends_at`, `coach_ids`, `court_ids`, `required_court_count`, `conflict_checked_at`, `evidence_hash`, `expires_at`.

**Constraints**:

- MVP `resource_mode=original_only`，coach_ids／court_ids 与原 ScheduleAllocation 完全一致。
- Agent 只能排序返回的 resource_plan_id，不能修改资源或时间。
- Proposal 只能引用已生成 plan ID；人工或模型提交候选外的新时段／资源必须拒绝并退出 Agent 流程。
- 过期、冲突变化、Policy 或 session version 变化时 plan stale。

## 12. Detector Evidence Contract

每个 Detector 输出：

- `schema_version`, `organization_id`, `venue_id`;
- `detector_key`, `detector_version`, `policy_version`;
- `subject_type`, `subject_id`, `case_key`;
- `severity_baseline`, `facts`, `source_refs`, `business_links`;
- `generated_at`, `evidence_hash`, `fingerprint`.

LLM 只接收脱敏后的 facts 和允许的 source_refs；Detector 原始 Query 行不进入 Prompt。

## 13. Relationships

```text
Organization 1 ── * Venue
Organization 1 ── * OrganizationMembership * ── 1 SystemUser
Venue 1 ── * VenueMembership
Venue 1 ── * OperationsPolicy
Venue 1 ── * OperationCase 1 ── * CaseActivity
OperationCase 1 ── * OperationRun
OperationRun 1 ── * OperationEvent
OperationRun 1 ── * OperationToolCall 1 ── 0..1 OperationApproval
OperationRun 1 ── 0..* OperationsReportSnapshot
OperationToolCall ── references ── Existing Business Aggregates
```

## 14. Retention and Deletion

- OperationCase、CaseActivity、Approval 和业务写 ToolCall 至少保留 2 年。
- 模型输入／输出只保存脱敏结构化结果和 hash；普通摘要默认 180 天，可缩短。
- 删除或归档 OperationRun 不得删除 AuditLog、CaseActivity、ToolCall 业务结果或报告确定性 Snapshot。
- Organization／Venue suspended 不触发级联删除；商业数据删除需另立数据治理方案。

## 15. Migration Verification

迁移完成必须输出并验证：

- 每张表迁移前后行数；
- null／未知 organization_id、venue_id 数量为 0；
- 跨 Scope 外键和业务引用数量为 0；
- scoped unique 冲突数量为 0；
- ScheduleAllocation 与 court_ids_csv 不一致明细已标记且 Agent 查询只采用 Allocation；
- Membership 待复核用户清单；
- 当前 Venue 初始 OperationsPolicy 状态；
- SQLite 导出／恢复和 PostgreSQL Alembic upgrade／downgrade 验证结果。
