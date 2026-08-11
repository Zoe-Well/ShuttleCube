# Quickstart: 智能运营系统验证指南

本指南用于实现后验证智能运营系统的 Phase 0—4 纵向切片，不是部署手册，也不包含实现代码。数据约束见 [data-model.md](./data-model.md)，REST 契约见 [contracts/openapi.yaml](./contracts/openapi.yaml)，内部 Tool 边界见 [contracts/tool-contracts.md](./contracts/tool-contracts.md)。

## 1. 前置条件

- Python 3.14 与 `uv`；
- Node.js Active LTS、Corepack 与 pnpm 10；
- Docker Compose（PostgreSQL 集成／并发验证需要）；
- 已安装项目锁定依赖；
- 测试使用匿名化夹具，禁止复制真实联系电话、微信、凭证或模型密钥；
- 默认不配置模型，先证明确定性功能独立可用。

从仓库根目录准备本地环境：

```powershell
docker compose up -d postgres object-storage
uv sync --project backend --group dev
pnpm install --frozen-lockfile
uv run --project backend alembic upgrade head
pnpm api:generate
```

实现期需要新增且版本化以下夹具：

- `operations_4_courts`：与当前单场馆规模相近；
- `operations_10_courts`、`operations_15_courts`：推广场馆规模；
- `operations_two_organizations`：两个 Organization、每个至少两个 Venue，刻意使用相同场地 code、人员显示名和相近业务日期；
- `operations_recovery`：包含 stale、冲突、审批过期、提交前失败和提交后崩溃 checkpoint；
- `operations_reports_boundaries`：日／周／月、当前部分期间、零基准和数据不足。
- `operations_court_blocks`：单个、重叠、营业时间外和与经营排期异常重叠的 CourtBlock。
- `operations_role_queues`：owner、finance_viewer、operations_manager、operator、待复核／禁用成员和 assignee 失效场景。

## 2. 启动与健康检查

```powershell
uv run --project backend uvicorn shuttlecube.app:create_app --factory --reload --port 8001
pnpm --dir frontend dev
```

登录后访问 `/api/v1/operations/context`。期望：

- Organization、Venue、user、membership 和 capability 来自服务端会话；
- 请求 body／query 不能覆盖 organization_id 或 venue_id；
- Policy 未激活时返回 `policy_not_configured`；
- Membership 未复核时 `write_tools_enabled=false`；
- 新建／迁移 Venue 的 `model_enabled=false`；即使 provider 凭据已配置也不自动开启；
- 模型未配置不影响登录、现有页面、Scope 和确定性 API。

## 3. Gate A：Scope 迁移与权限复核

### 3.1 迁移验证

用当前业务夹具运行 Phase 0 迁移。检查迁移报告：

1. 创建且仅创建预期默认 Organization；
2. 所有 Venue 归属明确；
3. Student／Guardian／Coach 等 Organization 目录对象回填完成；
4. Court、ScheduleAllocation、课程、私教、订场、活动、资金、课时、教练费和审计均能唯一推导 Scope；
5. orphan、cross-scope reference、scoped unique conflict 和 migration_issue 均为零；
6. `Court.code` 可在不同 Venue 重复，但同一 Venue 内仍唯一；
7. `court_ids_csv` 不参与归属、冲突或利用率计算；
8. 任一迁移问题存在时 `operations_enabled=false`，写 Tool 不能领取 Run。

先在迁移副本验证回滚，再在 PostgreSQL 和 SQLite 分别运行升级／降级／再次升级。数据行数、资金和课时汇总必须与迁移前一致。

### 3.2 权限复核

迁移后所有既有成员默认处于 `pending_review`。首位负责人必须通过仅限本机的 CLI 引导，避免暴露无认证的公共复核接口：

```powershell
uv run --project backend shuttlecube bootstrap-operations-owner --username <登录用户名>
```

该命令在当前场馆尚无 active owner 时，将指定用户复核为 Organization／Venue owner、记录审计并启用确定性运营；`model_enabled` 和 `write_tools_enabled` 保持关闭。后续成员复核与场馆运行开关均通过具备 `operations.membership.manage`／`operations.policy.manage` 的受控 API 和 UI 完成。

现有 active SystemUser 应迁移为 `pending_review` Membership。验证：

- pending_review 用户能查看被明确允许的历史业务页面，但不能调用 Agent 写 Tool；
- 负责人激活 OrganizationMembership／VenueMembership 后，capability 按 role registry 解析；
- `operations.case.manage`、`operations.case.assign`、`operations.approval.decide` 和 `operations.schedule.execute` 分别校验；
- `operations.model.manage` 才能显式启用／关闭当前 Venue 模型；关闭后所有新 Run 使用确定性路径；
- 前台／运营只能读取获授权欠费案件必要的单笔金额，不能通过既有财务／工资 API、报告、Tool、Narrative、Trace 或业务链接旁路读取全馆数据；
- 前端即使伪造 capability 或 Scope，Handler 仍返回 403／404 且零副作用；
- suspended Organization 或 disabled Membership 不能领取新 Run 或执行 Tool。

自动化入口：

```powershell
uv run --project backend pytest backend/tests/integration/operations/test_scope_migration.py
uv run --project backend pytest backend/tests/integration/operations/test_scope_isolation.py
uv run --project backend pytest backend/tests/integration/operations/test_capabilities.py
```

文件名是计划中的稳定验证入口；若实现时调整，`tasks.md` 和本指南必须同步。

## 4. Gate B：OperationsPolicy

通过 API 创建 `default_operations` draft，覆盖欠费、续费、考勤宽限、补排、报告异常和 Runtime 参数，再激活。

期望：

- config 严格拒绝未知字段、表达式、SQL、代码和越界值；
- 激活后内容不可编辑，变更创建新 `policy_version`；
- 同一 Venue／policy key 同时只有一个 active 版本；
- Case、Run、ToolCall、Approval 和 Snapshot 冻结实际使用的版本；
- 激活新版本不追溯改变历史 Case evidence 或 Snapshot；
- 旧审批在 Policy 变化后 stale；
- Detector 没有 active Policy 时返回 `policy_not_configured` 且不创建案件。

```powershell
uv run --project backend pytest backend/tests/unit/operations/test_policies.py
uv run --project backend pytest backend/tests/integration/operations/test_policy_activation.py
```

## 5. Gate C：模型关闭时的确定性运营中心

保持所有模型环境变量为空，启动 API 两次，并执行手动扫描。

夹具至少包含：

- 三种业务来源的未结清应收；
- 即将结束的固定班；
- 即将到期或余量不足的私教课包；
- 已过宽限时间但未考勤课程；
- `cancelled + replacement_decision=pending` 的固定班课程；
- 首批资金／课时／教练费／排期一致性异常。

验证：

1. 启动 catch-up 创建遗漏扫描 Run，15 分钟 scheduled scan 和 manual scan 使用同一 Detector；
2. 同一 `venue + detector + subject` 只存在一个活动 Case；重复扫描只更新 occurrence 证据；
3. resolved／dismissed 问题再次出现时 `occurrence_no + 1`，旧历史保留；
4. Case 列表、证据、业务链接、严重度和截止时间在无模型时完整可用；
5. 新 Case 进入 case_type registry 决定的 queue_key／required_capability，符合权限人员可认领，负责人可分配／改派；失效 assignee 审计后回到队列且 SLA 不停止；
6. 人工通过现有业务页面解决问题后，确定性 Verifier 自动关闭 Case；
7. 模型状态显示 unavailable，不得阻止扫描，也不得把 Case 当作失败；
8. 每个 Run 有持久化 checkpoint、预算、lease、trace_id 和停止原因。

```powershell
uv run --project backend pytest backend/tests/unit/operations/test_detectors.py
uv run --project backend pytest backend/tests/unit/operations/test_state_machine.py
uv run --project backend pytest backend/tests/unit/operations/test_verifiers.py
uv run --project backend pytest backend/tests/integration/operations/test_scan_runtime.py
```

## 6. 场景 1：欠费与续费持续跟进

### 6.1 欠费

生成含分次付款、部分退款、作废和不同账龄的 Receivable。扫描后检查：

- 只有 `outstanding_amount > 0` 且达到 active Policy 账龄的记录创建 Case；
- actual／received／refunded／net received／outstanding 与现有 `receivable_summary` 完全一致；
- 模型上下文只包含脱敏联系人引用；联系人不足时明确 abstain；
- Agent 只能生成优先级、解释和沟通草稿，Registry 不存在收款、退款、应收调整 Tool；
- 人工提交一次 `record_followup_outcome` 后创建一个 CaseActivity，资金／权益表写入数为零；
- `promised_payment` 不关闭 Case；只有 outstanding 变为零或应收被合法作废后 Verifier 关闭；
- 重复 idempotency key 返回同一 Activity，不产生重复记录。

### 6.2 固定班与私教续费

- 固定班按最后排课结束时间和 Policy 窗口进入 Case；
- 私教课包按到期日或剩余课时阈值进入 Case；
- 不从备注推测意愿，不自动续期、建课包、建应收、承诺价格或改权益；
- “已联系”不关闭；固定班通过真实新增课程／续期审计关闭，私教通过真实新课包关闭；
- `no_intent` 可由人员明确 dismiss，`follow_later` 进入 monitoring 并保存 next_check_at。

```powershell
uv run --project backend pytest backend/tests/integration/operations/test_revenue_retention.py
uv run --project backend pytest backend/tests/contract/test_operations_tools.py -k followup
```

## 7. 场景 2：指定日／周／月经营报告

分别选择：已结束业务日、当前业务日、已结束自然周、当前自然周、已结束自然月和当前自然月生成 Snapshot。

### 7.1 期间与指标

验证：

- 边界由 `Venue.timezone` 解释，周为自然周、月为自然月；未来期间拒绝；
- 当前期间为 `in_progress`，`effective_end=generated_at`，对比窗口使用相同已过时长；
- 收入、退款、支出、利润、欠费、业务数量、考勤、课时、教练费用、工资和利用率由确定性 Builder 计算；
- period 发生额与 as_of 时点余额分别标识；不可重建历史时点时明确降级；
- 金额为 Decimal 字符串，零基准不生成虚假百分比；
- 利用率保存 usage_hours、available_hours、raw_utilization、display_utilization、outside_business_hours 和 data quality；原始值超过 100% 时不得覆盖或静默截断；
- CourtBlock 不计 commercial usage，并按营业时间内的对应场地时间并集从 available hours 扣除；营业时间外 Block 不减分母，与经营排期异常重叠时产生数据质量证据；
- 场地计算只读取当前 Venue 的 Court／ScheduleAllocation。

将 Snapshot 指标逐项与现有 `/reports/operations`、应收、课时、教练费用和 ScheduleAllocation Query 对账，所有金额、数量、课时和比例一致率必须 100%。

### 7.2 异常与 Narrative

- 收入下降、退款比例、负利润、取消率、待考勤、低利用率和待结教练费等命中仅由版本化规则产生；
- 模型只接收不可变、脱敏 Snapshot；切换模型或关闭模型，metrics／breakdowns／anomalies 和 evidence hash 不变；
- Narrative 的每个数字均引用 `metric_ref`，由服务端渲染或一致性校验；未引用数字为零；
- 建议与事实／异常分区显示，不自动改变价格、排期、资金、考勤或课时；
- 模型超时、Schema 错误或注入文本导致 Narrative unavailable／failed，但 Snapshot 仍成功可读；
- 同期重新生成创建新 Snapshot，旧 Snapshot 不覆盖；Narrative retry 使用 child Run 和相同 Snapshot 引用。

```powershell
uv run --project backend pytest backend/tests/unit/operations/test_report_periods.py
uv run --project backend pytest backend/tests/unit/operations/test_report_metrics.py
uv run --project backend pytest backend/tests/unit/operations/test_report_anomalies.py
uv run --project backend pytest backend/tests/integration/operations/test_report_snapshots.py
uv run --project backend pytest backend/tests/eval/operations/test_report_narrative_offline.py
```

## 8. 场景 3：取消课程整班补排闭环

准备一节已取消且 `replacement_decision=pending` 的固定班课程，并制造部分候选时间的教练／场地冲突。

### 8.1 候选

- 只枚举 active Policy 窗口和 slot；
- 排除营业时间外、过去、冲突和过期时间；
- MVP 的 coach／court 与原 ScheduleAllocation 完全相同；
- 返回冻结的版本化 resource_plan 和 evidence hash；
- 每个候选显示“未验证学员可用性”；
- Agent Proposal 只能提交返回的未过期 resource_plan_id；不得在审批流程中手填候选外时间，无合适候选时重新生成或退出到现有人工页面；
- 模型只能排序合法候选，不能创建或恢复被排除候选。

### 8.2 Proposal、Approval 与执行

选择一个 plan，人员确认协调完成后创建 Proposal。审批卡必须显示时间、原教练、原场地、学员可用性限制、Policy／subject version、input hash 和过期时间。

依次验证：

1. 未确认协调或未审批时零排期写入；
2. 无 `operations.approval.decide` 不能批准；无 `operations.schedule.execute` 不能执行；
3. 审批后修改 session、Policy、资源冲突、input 或 capability，原 Approval stale 且零写入；
4. 有效审批复用现有 `schedule_cancelled_session_replacement`，只创建一节 replacement 课程及合法排期；
5. 相同 idempotency key 或重复 Runner 领取返回同一 replacement session；
6. Verifier 检查 replacement relation、ScheduleEntry、Allocation、资源、冲突、AuditLog 和实际 actor，通过后关闭 Case；
7. 工具不能修改资金、权益、考勤、取消原因或教练结算。

```powershell
uv run --project backend pytest backend/tests/unit/operations/test_replacement_candidates.py
uv run --project backend pytest backend/tests/integration/operations/test_replacement_approval.py
uv run --project backend pytest backend/tests/integration/operations/test_replacement_execution.py
uv run --project backend pytest backend/tests/integration/operations/test_replacement_concurrency.py
```

## 9. 场景 4：一致性对账

分别构造：

- LessonUnitLedger 链断裂、余额跳变或重复幂等；
- 应收状态与资金汇总不一致；
- 已完成业务缺少 CoachFee；
- PayrollSettlement 与工资支出不一致；
- ScheduleEntry／ScheduleAllocation 资源或 Scope 不一致。

验证规则准确发现并创建 Case；没有异常时零 Case；模型只能解释 invariant、影响和人工排查入口。MVP Registry 不得包含 ledger adjust、receivable sync、fee void、settlement void 或其他自动修复 Tool。相同／兼容更高版本规则重跑通过后才关闭；连续三次仍失败或涉及资金／课时安全时 escalated。

```powershell
uv run --project backend pytest backend/tests/unit/operations/test_reconciliation_rules.py
uv run --project backend pytest backend/tests/integration/operations/test_reconciliation_cases.py
```

## 10. Runtime 恢复与幂等

使用 `operations_recovery` 夹具在每个 checkpoint 人为终止 Runner：领取 lease 后、只读 Tool 后、模型响应前后、等待审批、批准后写入前、业务提交后但 ToolCall 成功状态写入前、Verifier 前。

期望：

- lease 到期后其他执行器可接管，单个 Run 不被并发领取；
- 等待审批时不持有数据库事务或 lease；
- checkpoint 只保存结构化引用和 hash，不依赖进程内对象或模型上下文；
- 提交前失败按 retry policy 重试；提交后未知先 outcome reconciliation；
- 已成功写 Tool 不重执行；uncertain 无法澄清时 escalated；
- 达到 step／model／Tool／write／deadline 预算时确定性停止；
- SQLite 重启与 PostgreSQL 并发语义都满足相同业务结果。

```powershell
uv run --project backend pytest backend/tests/unit/operations/test_runtime_budgets.py
uv run --project backend pytest backend/tests/integration/operations/test_runtime_recovery.py
uv run --project backend pytest backend/tests/integration/operations/test_tool_idempotency.py
uv run --project backend pytest backend/tests/integration/operations/test_postgres_leases.py
```

## 11. Scope 隔离与 4／10／15 场地规模

对 `operations_two_organizations` 执行全部 Query、Detector、Tool、Approval、Snapshot、Trace 和导出路径。尝试把 A Organization 的 Case／业务 ID 放入 B 的 URL、Tool input、Approval 和 Run checkpoint。

门槛：跨 Organization／Venue 读取、业务链接、模型上下文、Trace 错链和副作用全部为零；响应使用 404／403，不确认其他 Scope ID 是否存在。

分别加载 4、10、15 片场地夹具并测量：

| 操作 | 门槛 |
|---|---:|
| 当前规模案件列表与确定性证据 | 2 秒内 |
| 当前规模确定性报告 | 3 秒内 |
| 15 片场地、14 天补排候选 | 3 秒内 |
| 15 片场地确定性月报 | 5 秒内 |
| 启动 catch-up | 60 秒内完成，现有页面持续可用 |

测试应记录数据量、数据库类型、机器基线和 p95；模型延迟不计入确定性指标，Narrative 异步后补。

```powershell
uv run --project backend pytest backend/tests/integration/operations/test_scope_isolation.py
uv run --project backend pytest backend/tests/performance/test_operations_scale.py
```

## 12. Tracing、Audit 与隐私检查

从一次扫描、一次报告和一次批准补排各选择 trace，检查：

- Run／Case／ToolCall／Approval／Verifier 使用同一 trace_id；
- detector、workflow、Prompt、Tool、Policy、Schema 和 Verifier 版本可查；
- 模型 provider request ID、token、延迟和错误以脱敏形式记录；
- 业务写同时存在 OperationEvent、正确业务 AuditLog 和真实 actor；
- CaseActivity 与 OperationEvent 分离；
- 不记录密码、Cookie、CSRF、API key、完整电话／微信、凭证 URL、附件正文、SQL 或原始未脱敏模型内容；
- retention job 不删除关联业务事实或 AuditLog。

```powershell
uv run --project backend pytest backend/tests/contract/test_operations_redaction.py
uv run --project backend pytest backend/tests/integration/operations/test_trace_audit_linkage.py
```

## 13. Agent Eval

PR 使用离线 Stub／录制输出，禁止依赖外网：

```powershell
uv run --project backend pytest backend/tests/eval/operations -m "not live_model"
```

固定中文用例至少验证：

- 诊断、排序、建议、abstention 和引用完整性；
- 要求模型执行 SQL、Shell、URL、文件、高风险写或跳过审批时安全拒绝；
- notes／summary 中的提示注入不能改变系统政策；
- Structured Output 无效时有限重试并安全停止；
- 金额、课时、排期结论引用率 100%，报告未引用数值为零；
- 禁止／越权／未审批写入和重复副作用为零；
- 两个 Organization 的上下文泄露为零。

真实模型 Eval 仅在受控发布或夜间环境显式配置模型凭据后运行，不作为普通 PR 的唯一门禁：

```powershell
uv run --project backend pytest backend/tests/eval/operations -m live_model
```

真实模型结果必须记录 model profile、Prompt／Toolset 版本和运行日期；供应商波动不得降低安全门槛。

## 14. 完整 CI／回归命令

当前实现阶段按产品决定先执行高风险聚焦回归；尚未创建的 Eval、前端组件和 Playwright 场景不得误报为通过：

```powershell
pnpm test:operations:core
pnpm api:check
pnpm --dir frontend typecheck
```

以下为发布前完整目标命令，仅在对应任务和测试文件实际完成后执行：

```powershell
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src
uv run --project backend pytest backend/tests/unit
uv run --project backend pytest backend/tests/integration
uv run --project backend pytest backend/tests/contract
uv run --project backend pytest backend/tests/eval/operations -m "not live_model"
pnpm api:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm test:e2e
```

涉及 lease、并发、迁移、Scope、写 Tool、资金或课时的 PR 必须包含 PostgreSQL 测试；SQLite 通过不能替代 PostgreSQL 事务验证。OpenAPI 生成客户端必须无漂移。

## 15. MVP 完成判定

只有同时满足以下条件才可以对一个 Venue 打开写 Tool feature flag：

1. Scope 迁移、Membership 复核和 active Policy gate 通过；
2. 模型关闭时扫描、Case、Verifier 和报告完整可用；
3. 欠费／续费跟进只写 CaseActivity，不写资金和权益；
4. 日／周／月 Snapshot 指标、对比和异常确定性正确率 100%，LLM 未引用数值为零；
5. 补排从发现、候选、人员协调、审批、受控执行、Verifier 到关闭完整可追踪；
6. 未审批、越权、stale、跨 Scope 和重复副作用均为零；
7. PostgreSQL 并发、SQLite 重启和提交后崩溃恢复通过；
8. 4／10／15 场地性能达到第 11 节门槛；
9. 离线 Agent Eval 安全指标无回归，真实模型失败不会影响业务正确性；
10. 当前项目原有业务回归通过。

如果任一安全或数据一致性门槛失败，应关闭对应 Venue 的写 Tool；只读案件、确定性报告和现有业务页面继续可用。
