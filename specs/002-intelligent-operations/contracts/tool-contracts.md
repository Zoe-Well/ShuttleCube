# Tool Contracts: 智能运营系统

## 1. 目的与适用边界

本文冻结 Phase 1—3 的业务 Tool 契约。Tool 是 ShuttleCube 应用层的受控 Query／Command，不是模型 Provider 的插件，也不是任意数据库、文件、网络或代码执行接口。OpenAI function calling 只负责让模型从允许的只读 Tool 子集中选择；实际 Registry、Scope、权限、审批、事务、幂等、审计和结果校验始终由 ShuttleCube 服务端负责。

以下规则适用于所有 Tool：

- 调用方不能传 `organization_id`、`venue_id`、`user_id`、capability 或数据库连接；这些值只能从 `RequestScope`／`OperationRun` 注入。
- Tool 输入和输出由版本化 Pydantic Schema 校验，`extra="forbid"`，未知字段拒绝。
- 模型不能调用 `dismiss_operation_case`；该动作仅可由人工 REST 操作触发。
- 金额使用 Decimal 字符串，时间使用带偏移的 ISO 8601，业务日由 `Venue.timezone` 解释。
- 自由文本、备注和联系人显示名是“不可信业务数据”，不得拼接为系统指令。
- 只返回最小必要数据；完整电话、微信、Cookie、密钥、附件正文和凭证 URL 永不进入模型 Tool 输出。
- Tool Handler 必须再次校验 Scope 和 capability，不能依赖调用前检查或前端隐藏。
- 每次模型调用前必须确认当前 Venue `model_enabled=true`；provider 凭据存在不能替代该 opt-in，关闭后新 Run 只执行确定性路径。
- REST、Tool、模型上下文、Narrative 和 Trace 必须使用同一 audience capability 投影；前台／运营只能看到获授权跟进案件的必要单笔欠费信息，不能旁路读取全馆利润、工资或结算。
- Detector 只生成 queue_key／required_capability；认领要求该 capability，向他人分配或改派要求 `operations.case.assign`。案件分配不是模型 Tool。
- 每次调用产生 `OperationEvent`；业务写还必须产生现有 `AuditLog` 或结构化 `CaseActivity`。

## 2. Registry Definition

每个代码注册项必须包含以下不可省略字段：

| 字段 | 含义 |
|---|---|
| `tool_key` | 稳定业务语义名称 |
| `tool_version` | 输入、输出或语义变化时递增 |
| `description` | 面向模型与开发者的准确用途，不包含营销文案 |
| `input_schema` / `output_schema` | 严格、版本化 Schema |
| `implementation` | 应用层 Query／Command handler |
| `risk_level` | `read`、`low`、`medium` 或 `high` |
| `required_capability` | 服务端 capability key |
| `approval_policy` | `none`、`explicit_confirmation`、`mandatory_approval` 或 `human_only` |
| `idempotency_scope` | `none` 或 `(venue_id, tool_key, idempotency_key)` |
| `timeout_seconds` | 单次执行上限 |
| `redaction_policy` | Tool 特定脱敏器版本 |
| `verifier` | 结果和闭环的确定性验证器 |
| `enabled_flag` | Venue feature flag；默认关闭写 Tool |

数据库只保存调用时冻结的上述版本、输入 hash、影响快照和结果，不允许通过 UI 动态创建或修改 Tool。

## 3. 统一调用上下文

Runtime 在调用 Handler 时传入内部上下文；此对象不属于模型输入 Schema：

```text
ToolExecutionContext
  organization_id: UUID
  venue_id: UUID
  actor_user_id: UUID | null
  membership_id: UUID | null
  capabilities: frozenset[str]
  case_id: UUID | null
  run_id: UUID
  trace_id: UUID
  request_id: str | null
  policy_key: str
  policy_version: int
  toolset_version: str
  idempotency_key: str | null
  deadline_at: datetime
```

`actor_user_id` 对模型发起的只读调用可为空；任何写 Tool 都必须是实际确认、批准或执行的用户，不能为空，也不能使用“AI 用户”。

## 4. Tool Result Envelope

所有 Tool 返回统一 Envelope；业务 payload 位于 `data`：

```json
{
  "schema_version": "1",
  "tool_key": "get_case_evidence",
  "tool_version": "1",
  "status": "succeeded",
  "generated_at": "2026-08-09T08:00:00Z",
  "evidence_hash": "sha256:...",
  "source_refs": [
    {"source_type": "receivable", "source_id": "...", "source_version": 3}
  ],
  "data_status": "complete",
  "warnings": [],
  "data": {},
  "result_reference": null
}
```

约束：

- `status` 为 `succeeded | rejected | failed | uncertain`；模型超时不改变已成功业务结果。
- `data_status` 为 `complete | partial | insufficient | data_quality_issue`。
- `evidence_hash` 对规范化后的 Scope、Schema／Tool／Policy 版本、source refs 和 data 计算，不包含显示顺序或模型文本。
- `source_refs` 只使用受控实体类型和 ID，不暴露表名、SQL、路径或任意 URL。
- 写 Tool 成功时 `result_reference` 必须指向可查询的业务事实；失败或拒绝时 `data` 不得伪装成部分成功。
- `uncertain` 只用于无法判断事务是否提交的恢复边界。Runtime 必须先执行 outcome reconciliation，不得盲目重试。

## 5. 错误契约

Tool 错误由 Handler 返回结构化错误并映射到 OperationToolCall／Run 状态；不得把堆栈、SQL 或密钥交给模型。

| code | 分类 | Retry | 处理 |
|---|---|---:|---|
| `scope_not_found` | 安全 | 否 | 对跨 Scope ID 表现为不存在；记录安全审计 |
| `capability_denied` | 权限 | 否 | 停止并等待有权限人员 |
| `policy_not_configured` | 配置 | 否 | 不创建新 Case／Proposal |
| `policy_stale` | 并发 | 否 | ToolCall／Approval 标为 stale，重新生成 |
| `subject_stale` | 并发 | 否 | 重新读取业务事实和候选 |
| `approval_required` | 流程 | 否 | Run 进入 `waiting_approval` |
| `approval_expired` | 流程 | 否 | Approval 标为 expired，重新提议 |
| `approval_stale` | 流程 | 否 | 影响、输入或权限变化，禁止执行 |
| `invalid_input` | 契约 | 否 | 安全停止并记录 Schema 错误 |
| `data_insufficient` | 业务 | 否 | 返回 abstention 和缺失项 |
| `no_legal_candidate` | 业务 | 否 | Case 进入 `waiting_human` 或 monitoring |
| `conflict_detected` | 业务并发 | 否 | 资源方案 stale，重新生成候选 |
| `idempotency_conflict` | 幂等 | 否 | 相同 key 不同输入，拒绝 |
| `timeout_before_commit` | 临时 | 是 | 按 Run retry policy 重试 |
| `outcome_uncertain` | 恢复 | 否 | reconciliation 后才决定 succeeded／retry／escalated |
| `model_unavailable` | 模型 | 有限 | 保留确定性内容，Narrative 标记 unavailable |
| `internal_error` | 系统 | 有限 | 脱敏后重试；超限 escalated |

## 6. MVP Registry

| Tool | v | 风险 | capability | 审批 | 模型可选 |
|---|---:|---|---|---|---:|
| `get_case_evidence` | 1 | read | `operations.case.read` | none | 是 |
| `get_receivable_followup_context` | 1 | read | `operations.receivable.followup.read` | none | 是 |
| `get_renewal_followup_context` | 1 | read | `operations.case.read` | none | 是 |
| `list_replacement_candidates` | 1 | read | `operations.case.read` | none | 否，由 Workflow 确定性调用；模型只排序返回值 |
| `get_reconciliation_result` | 1 | read | `operations.case.read` | none | 是 |
| `get_operations_report_snapshot` | 1 | read | `operations.report.read` | none | 否，由报告 Workflow 注入 |
| `record_followup_outcome` | 1 | low | `operations.case.manage` | explicit_confirmation | 否，由人工表单触发 |
| `dismiss_operation_case` | 1 | low | `operations.case.manage` | human_only | 否 |
| `schedule_cancelled_class_replacement` | 1 | medium | `operations.schedule.execute` | mandatory_approval | 否，由批准后的 Executor 调用 |

模型每一步只能看到当前 Workflow 明确允许的只读子集。即使 Registry 中存在写 Tool，也不能把它们声明给模型 Provider。

模型 Tool 投影还有一个前置 gate：当前 Venue 必须显式启用模型，且 Workflow 目标受众具备 Tool 所需 capability。系统调度 Run 不能以“系统身份”绕过财务字段投影；需要生成不同受众简报时应分别构建最小上下文。

## 7. Read Tool Schemas

### 7.1 `get_case_evidence` v1

用途：读取当前 occurrence 的规范化 Detector 证据，不重新定义异常。

Input：

```json
{
  "case_id": "uuid",
  "occurrence_no": 1
}
```

- `case_id` 必须属于执行 Scope；否则返回 `scope_not_found`。
- `occurrence_no` 可省略，省略时读取当前 occurrence。

Data：

```json
{
  "case_type": "receivable_followup",
  "subject_type": "receivable",
  "subject_id": "uuid",
  "detector_key": "receivable_aging",
  "detector_version": "1",
  "policy_version": 3,
  "severity_baseline": "medium",
  "facts": {},
  "business_links": [{"label": "查看应收", "route": "/finance/receivables/..."}]
}
```

Verifier：证据 hash 与 Case 当前 `evidence_hash` 一致；source refs 全部属于 Scope。

### 7.2 `get_receivable_followup_context` v1

用途：为欠费诊断和沟通草稿提供确定性金额、账龄、业务来源、联系人充分性和跟进历史。

Input：

```json
{"case_id": "uuid"}
```

Data 必含：

```json
{
  "receivable_id": "uuid",
  "business_source": {"source_type": "enrollment", "source_id": "uuid", "display_name": "脱敏显示名"},
  "amounts": {
    "actual_receivable": "1200.00",
    "received": "600.00",
    "refunded": "0.00",
    "net_received": "600.00",
    "outstanding": "600.00",
    "payment_status": "partial"
  },
  "aging_days": 30,
  "contact": {"available": true, "subject_type": "guardian", "subject_id": "uuid", "display_name": "王**"},
  "activities": [],
  "next_allowed_followup_at": "2026-08-10T01:00:00Z"
}
```

约束：

- 所有金额复用 `receivable_summary` 及其当前确定性规则；模型不得重算。
- 不返回电话号码、微信号或凭证；`contact.available=false` 时模型必须 abstain，不得编造渠道。
- `promised_payment` 等 Activity 仅作跟进背景，不代表已收款。

Verifier：重新查询相同应收并验证 outstanding／payment_status；outstanding 为零时应触发 Case Verifier，而不是继续生成催缴建议。

### 7.3 `get_renewal_followup_context` v1

用途：读取固定班结束或私教课包到期／余量不足的续费证据。

Input：

```json
{"case_id": "uuid"}
```

Data 为 tagged union：

```json
{
  "renewal_type": "fixed_class",
  "subject_id": "uuid",
  "end_at": "2026-08-31T13:00:00+08:00",
  "remaining_scheduled_sessions": 2,
  "current_receivable_status": "paid",
  "contact": {"available": true, "subject_type": "guardian", "subject_id": "uuid", "display_name": "李**"},
  "activities": [],
  "renewal_facts": {"new_session_ids": [], "renewal_audit_refs": []}
}
```

或：

```json
{
  "renewal_type": "private_package",
  "subject_id": "uuid",
  "expires_on": "2026-08-31",
  "remaining_units": 2,
  "current_receivable_status": "paid",
  "contact": {"available": false},
  "activities": [],
  "renewal_facts": {"replacement_package_ids": []}
}
```

约束：不得根据 notes 推测续费意愿；不得承诺价格、创建续期、课包、应收或权益。

Verifier：固定班只根据新增 ClassSession／续期业务审计等真实事实关闭；私教只根据新课包等真实事实关闭；“已联系”不等于续费。

### 7.4 `list_replacement_candidates` v1

用途：从营业时间、slot、原资源和冲突规则中确定性生成合法 `resource_plan`。

Input：

```json
{
  "case_id": "uuid",
  "window_start": "2026-08-10T00:00:00+08:00",
  "window_end": "2026-08-24T00:00:00+08:00",
  "max_candidates": 20,
  "expected_case_version": 4
}
```

约束：

- 窗口不能超过 active Policy 的 `replacement.window_days`；最多返回 50 项。
- MVP `resource_mode=original_only`；原教练和原场地来自 ScheduleAllocation，不来自 CSV。
- Runtime／LLM 不能传 coach_ids、court_ids、时长或 policy_version。
- 有效 CourtBlock 是候选冲突，即使经营报告不把它计作使用时长也不得忽略。
- 候选必须明确 `student_availability_verified=false`。

Data：与 [OpenAPI `ReplacementResourcePlan`](./openapi.yaml) 一致，另含 `rejected_counts_by_reason`，但不返回每个非法组合的原始明细。

Verifier：对每个 plan 重跑 Venue Scope、营业时间、session version、原资源一致性和 `find_conflicts`；任何失败都不能进入结果。

### 7.5 `get_reconciliation_result` v1

用途：读取已经由版本化确定性规则判定的对账结果，供模型解释影响和建议人工修复顺序。

Input：

```json
{"case_id": "uuid"}
```

Data：

```json
{
  "rule_key": "lesson_ledger_chain",
  "rule_version": "1",
  "result": "failed",
  "severity": "high",
  "affected_refs": [],
  "invariants": [{"key": "balance_chain", "expected": "...", "actual": "...", "passed": false}],
  "repair_entry_points": [{"label": "查看课时流水", "route": "/students/..."}],
  "automatic_repair_available": false
}
```

约束：模型不能改变 `result`、severity 基线或 invariant；MVP 不存在自动修复 Tool。

Verifier：相同或更高兼容规则版本重跑通过才允许关闭。规则语义不兼容时创建新 occurrence，不能静默解释为修复。

### 7.6 `get_operations_report_snapshot` v1

用途：向报告 Narrative Workflow 提供不可变、脱敏的确定性 Snapshot。

Input：

```json
{"report_snapshot_id": "uuid"}
```

Data 包含：期间元数据、`metric_version`、`anomaly_rule_version`、按受众 capability 投影后的 metrics、breakdowns、anomalies、data quality caveats 和允许的 source refs；不包含原始明细行或 PII。场地指标区分 commercial_usage_hours、base_business_hours、court_block_unavailable_hours、available_hours 和 raw/display utilization；CourtBlock 按营业时间重叠并集扣减分母且不计经营使用。

约束：

- Narrative Run 的 `input_hash` 必须绑定 snapshot ID 与 evidence hash。
- 模型只返回 `text_template + metric_refs + anomaly_ids`；服务端根据 metric_ref 插入格式化数字，拒绝未引用数字。
- Narrative 不能新增异常命中、改变阈值或建议直接改价、改排期、改资金、改课时。

Verifier：所有 metric_ref／anomaly_id 存在；服务端渲染后数字与 Snapshot 一致。失败只更新 narrative_state，不改变 Snapshot。

## 8. Write Tool Schemas

### 8.1 `record_followup_outcome` v1

风险：low。只能由人工编辑并显式提交，不声明给模型。

Input：

```json
{
  "case_id": "uuid",
  "activity_type": "contact_result",
  "channel": "phone",
  "contact_subject_type": "guardian",
  "contact_subject_id": "uuid",
  "outcome_code": "follow_later",
  "summary": "家长希望周五再联系",
  "happened_at": "2026-08-09T10:30:00+08:00",
  "next_check_at": "2026-08-14T09:00:00+08:00",
  "expected_case_version": 4
}
```

Preconditions：

1. actor 具备 `operations.case.manage` 且 Membership active；
2. case／contact subject 属于相同 Scope；
3. case occurrence 和 version 未变化；
4. outcome 与 next_check_at 组合合法；
5. 用户通过 UI 明确确认，不接受模型自动确认标志。

Side effects：一个 `CaseActivity`、一个 redacted `OperationEvent`；如状态机需要，更新 Case 的 `next_check_at`／monitoring。不得写 Payment、Refund、Receivable、Enrollment、PrivateLessonPackage 或 LessonUnitLedger。

Idempotency：必填；相同 key 与相同 input hash 返回同一 Activity；不同 input hash 返回 `idempotency_conflict`。

Verifier：Activity 可按 ID 和 Scope 查询，Case 状态与 outcome 规则一致，受保护业务表写入数为零。

### 8.2 `dismiss_operation_case` v1

风险：low，`human_only`。REST handler 可复用内部 Command，但 Tool 永不暴露给模型。

Input：

```json
{"case_id": "uuid", "reason": "客户明确不续费", "expected_case_version": 4}
```

Preconditions：actor 具备 `operations.case.manage`，理由 1—500 字，当前状态允许 `dismissed`。系统检测到的问题不能因空原因或模型建议直接消失。

Side effects：Case 转 `dismissed`，写 CaseActivity／OperationEvent；不修改源业务事实。

Verifier：状态机转换合法，resolution code、人员、原因、occurrence 和时间均可审计。

### 8.3 `schedule_cancelled_class_replacement` v1

风险：medium，强制不可变 Approval，不声明给模型。

Normalized input：

```json
{
  "case_id": "uuid",
  "resource_plan_id": "uuid",
  "cancelled_session_id": "uuid",
  "cancelled_session_version": 3,
  "starts_at": "2026-08-16T10:00:00+08:00",
  "ends_at": "2026-08-16T11:00:00+08:00",
  "coach_ids": ["uuid"],
  "court_ids": ["uuid"],
  "resource_policy_version": 2,
  "coordination_confirmed": true
}
```

上述 input 由服务端从冻结 `ReplacementResourcePlan` 规范化，前端只提交 `resource_plan_id` 和人员协调确认；Scope、资源、时间、Policy 与版本不能由模型或浏览器改写。候选外的新时段不得在 Agent 流程内即时重建 plan；应重新生成候选或退出到现有人工业务页面。

Approval 必须冻结：`tool_key/version`、risk、required capability、policy version、input hash、subject versions、资源／时间影响、学生可用性未由系统验证的显著提示和过期时间。

Execution preconditions：

1. ToolCall 和 Approval 同 Scope，状态分别为 approved／approved；
2. 批准者当前仍具备 `operations.approval.decide`，执行责任人具备 `operations.schedule.execute`；可为同一管理人员；
3. Approval 未过期，input hash、Policy、tool version 和 subject versions 未变化；
4. 原 session 仍为 `cancelled + replacement_decision=pending`；
5. plan 未过期，MVP 资源仍与原 ScheduleAllocation 一致；
6. 再次执行营业时间和冲突校验；
7. `coordination_confirmed=true` 来自人员明确确认。

Side effects：复用现有 `schedule_cancelled_session_replacement` 应用服务，创建一节 replacement ClassSession、ScheduleEntry／ScheduleAllocation、replacement 关联、现有业务 AuditLog，并在同一事务保存 ToolCall 结果映射；不改考勤、课时、资金或原取消原因。

Idempotency：`(venue_id, tool_key, idempotency_key)` 唯一。成功后重复调用返回同一 replacement session ID。若在提交后崩溃，先按 idempotency 结果、replacement relation 和业务审计 reconciliation；只有证明未提交才可重试。

Success data：

```json
{
  "cancelled_session_id": "uuid",
  "replacement_session_id": "uuid",
  "schedule_entry_id": "uuid",
  "allocation_ids": ["uuid"],
  "verified_at": "2026-08-09T11:00:00Z"
}
```

Verifier：replacement relation 存在且唯一；时间、教练、场地与 plan 一致；ScheduleEntry／Allocation 可查且无冲突；ToolCall result_reference、AuditLog、trace_id 和实际 actor 一致。通过后 Case 才能 `resolved`；不通过进入 `waiting_human` 或 `escalated`，不能由模型宣布完成。

## 9. Approval and Staleness Matrix

| 变化 | 旧 ToolCall | 旧 Approval | 后续动作 |
|---|---|---|---|
| 人员修改候选时间或资源 | cancelled | stale | 生成新 plan、ToolCall 和 Approval |
| session version 变化 | stale | stale | 重新读事实和冲突 |
| Policy 版本变化 | stale | stale | 按新 Policy 重新生成 |
| Tool version 变化 | stale | stale | 新 ToolCall |
| input／impact hash 变化 | stale | stale | 新 ToolCall |
| Approval 到期 | awaiting_approval | expired | 重新审批前重新校验 |
| 批准者 capability 被移除 | stale | stale | 新的有权限人员处理 |
| plan 冲突变化 | stale | stale | 重新生成候选 |
| 模型排序／解释改变 | 不变 | 不变 | 只要冻结 input 未变，无需重审批 |

## 10. Runtime Budgets and Stop Conditions

- 每个 Workflow 固定 `max_steps`、`max_model_calls`、`max_tool_calls`、`max_write_calls` 和 deadline；模型不得扩大预算。
- 报告 Narrative：最多 1 次 Snapshot Tool、2 次模型调用、0 次写调用。
- 欠费／续费分析：最多 3 次只读 Tool、2 次模型调用、0 次业务写；跟进 Activity 另由人工请求创建。
- 补排：候选生成 1 次，可选模型排序 1 次；每个批准 Proposal 最多 1 次写 Tool。
- 相同 checkpoint 没有新证据、重复 invalid output、预算耗尽、未知结果未澄清、Policy 缺失或权限不满足时必须停止。
- 暂时错误仅按 Policy 的指数退避和 `retry_limit` 重试；安全、权限、stale、无合法候选和确定性业务错误不自动重试。

## 11. Tracing and Audit Requirements

每次调用至少记录：trace／run／case／tool_call ID、Tool／Schema／Policy 版本、input／output hash、脱敏摘要、风险、capability 判定、Approval ID、idempotency key hash、尝试次数、耗时、状态和 result reference。

禁止记录：模型密钥、Cookie、CSRF token、完整电话／微信、完整附件／凭证 URL、原始文件、未脱敏 Prompt／Response、SQL 和数据库凭证。

`OperationEvent` 解释执行过程，`CaseActivity` 记录真实人工跟进，`AuditLog` 证明业务事实写入；三者必须通过 trace／request／tool_call 引用关联，但不能互相替代。

## 12. Contract Tests

每个 Tool 至少具备以下自动化契约测试：

1. 合法输入成功且 Envelope、hash、source refs 和 Schema 完整；
2. 未知字段、错误枚举、超长文本、越界日期和非定点金额被拒绝；
3. 两个 Organization／多个 Venue 的碰撞 ID 或显示名不能越 Scope 读取；
4. capability 缺失时零副作用；
5. Tool 输出不含 PII、凭证、Cookie、SQL、文件路径和未允许字段；
6. 相同 idempotency key／相同 input 返回同一结果，不同 input 拒绝；
7. Policy、subject、impact、权限或 Approval 变化导致 stale；
8. 写 Tool 提交前失败、提交后崩溃和重启恢复均不会产生重复业务事实；
9. Verifier 只读取确定性事实，不读取模型“成功”结论；
10. 禁止 Tool 名、任意 SQL／Shell／URL／文件调用和高风险业务写入均被 Registry 拒绝。
11. 当前 Venue 未 opt-in 时模型调用数为零，provider 凭据不会改变该结果。
12. 前台／运营可读取当前跟进案件必要单笔金额，但通过报告、Narrative、Trace 或其他 Tool 读取全馆财务／工资的成功次数为零。

固定 CI 门槛详见 [Spec 第 11 节](../spec.md#11-agent-eval-与-ci)，REST 展示契约见 [openapi.yaml](./openapi.yaml)，持久化字段见 [data-model.md](../data-model.md)。
