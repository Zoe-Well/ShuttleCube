# 智能运营系统运行手册

> 当前产品策略（2026-08-12）：第一版只面向权限相同的场馆管理人员，不向用户开放多角色配置。下文的固定角色包和成员复核流程作为后续双角色扩展的安全基础保留，不是当前版本要求用户完成的日常配置。当前决策与未来迁移方案见 [角色权限演进方案](./角色权限演进方案.md)。

本手册面向 ShuttleCube 场馆负责人和运维人员。智能运营系统默认采用“确定性能力先启用、模型单独启用、写工具最后启用”的发布顺序。任何 Gate 失败时，优先关闭更高风险能力；现有排课、收付款、课时和工资业务不应依赖 Agent 才能运行。

## 1. 默认安全状态

新建或迁移后的 Venue 应保持：

- `active_for_operations=false`：不调度智能运营扫描；
- `model_enabled=false`：不向模型供应商发送上下文；
- `write_tools_enabled=false`：不执行补排等受控业务写入；
- Membership 为 `pending_review`，直到负责人完成人员与角色复核；
- 没有 active `default_operations` Policy 时，扫描和报告返回 `policy_not_configured`。

模型关闭或供应商未配置时，确定性扫描、案件、Verifier、日／周／月报告和对账仍应工作。收入跟进分析、报告 Narrative 和对账解释显示 unavailable，不得阻止确定性结果交付。

## 2. 启用前检查顺序

### 2.1 Scope 与迁移

1. 备份 SQLite 数据文件或 PostgreSQL 数据库。
2. 执行数据库升级。
3. 确认 Organization、Venue 和所有业务事实的 Scope 回填完成。
4. 检查 orphan、cross-scope reference、scoped unique conflict 和 migration issue 均为零。
5. 在备份副本验证降级与再次升级；失败时不得启用智能运营。

### 2.2 Membership 与能力

负责人在当前 Venue 逐一复核成员。角色采用固定能力包，不接受浏览器提交自定义 capability：

- owner：全部运营管理能力；
- operations_manager：案件、跟进、审批和补排执行；
- operator：案件与跟进，不可审批或执行补排；
- finance_viewer：报告财务和工资只读，不可处理案件。

重点复核 `operations.case.assign`、`operations.approval.decide`、`operations.schedule.execute`、`operations.report.financial.read`、`operations.payroll.read` 和 `operations.model.manage`。成员禁用或角色变化后，旧审批在执行前仍会重新校验当前能力。

### 2.3 Policy

1. 创建 `default_operations` draft。
2. 核对欠费、续费、考勤宽限、补排窗口、报告阈值和 Runtime 限额。
3. 激活 draft；激活内容不可原地编辑。
4. 后续调整必须创建新版本。旧 Case、Run、ToolCall、Approval 和报告保留原 policy version；旧补排审批在 Policy 变化后失效。

## 3. 分级启用

### 3.1 只读确定性能力

先设置 `active_for_operations=true`，保持模型和写工具关闭。验证：

- 手动扫描能生成当前 Venue 的案件；
- 重复扫描不重复创建相同活动案件；
- 真实业务事实修复后 Verifier 才关闭案件；
- 日／周／月报告金额、数量、课时和利用率来自确定性快照；
- CourtBlock 正确扣减不可售容量；
- 对账只生成异常与人工修复入口，不存在自动修账工具。

### 3.2 模型能力

只有具备 `operations.model.manage` 的负责人可以为当前 Venue 设置 `model_enabled=true`。启用前确认供应商凭据由服务端环境提供，API、前端、Trace 和 Audit 均不返回凭据。

启用后抽查：模型只解释冻结上下文；报告数字来自 `metric_ref` 服务端渲染；对账可能原因标记为假设；模型失败时确定性内容不变。若出现越权引用、未引用数字、提示注入成功或供应商异常，立即关闭 `model_enabled`。

### 3.3 写工具

最后设置 `write_tools_enabled=true`。MVP 唯一 medium-risk 写闭环是已取消固定班的整班补排：

1. 候选只能由服务端使用原教练、原场地生成；
2. 人工确认学员、教练和场馆协调完成；
3. 创建冻结 ToolCall 与 Approval；
4. 具备审批和执行能力的当前成员批准；
5. Executor 再校验 Policy、版本、权限、营业时间、资源和冲突；
6. 业务写、AuditLog、Tool result 和 Verifier 在同一事务边界完成；
7. Verifier 通过后案件关闭。

欠费跟进只写 CaseActivity。MVP 不注册收款、退款、续费、应收同步、课时调整、费用作废、结算作废或排期自动修复工具。

## 4. 日常观察

- 检查扫描 Run 是否长期停留在 queued/running；
- 检查 lease 到期后的接管和 retry 是否在预算内停止；
- 检查 waiting_approval 的审批是否过期或 stale；
- 检查 failed/uncertain ToolCall 是否已有 outcome reconciliation 结论；
- 检查 critical 对账案件和连续三次失败升级；
- 检查报告 Narrative 失败是否仅影响解释层；
- 定期复核 Membership、active Policy 和三个 Venue 开关。

CaseActivity、Approval、业务写 ToolCall 和 OperationCase 至少保留两年；普通模型结构化摘要默认保留 180 天。安全归档只能裁剪到期 Run checkpoint，不能删除 CaseActivity、AuditLog、Tool 业务结果、报告确定性快照或业务事实。

## 5. 故障处置

### 5.1 模型或输出异常

关闭当前 Venue 的 `model_enabled`。无需关闭确定性扫描和报告。保留 Run、错误摘要、Prompt version、model profile 和 provider request metadata，禁止把密钥或原始敏感上下文复制到工单。

桌面版 AI 凭据统一在“场馆设置 → 资源目录 → AI 服务配置”维护。OpenAI 使用 Responses API；DeepSeek 使用 Chat Completions API；自定义 OpenAI 兼容服务按保存的协议调用。连接验证成功不会自动开启 AI。排查第三方供应商故障时，可核对供应商、基础地址、协议、模型名称与验证时间，但不得读取、回显或记录 API Key。

### 5.2 写工具异常

立即关闭 `write_tools_enabled`，保留 `active_for_operations=true` 以继续只读发现。对 executing/uncertain ToolCall 不得直接重试：先按 idempotency key、replacement relation、ScheduleEntry、AuditLog 和 result reference 做 outcome reconciliation。只有证明业务未提交才允许重新提议。

### 5.3 Scope、权限或数据泄露风险

立即同时关闭 `model_enabled`、`write_tools_enabled` 和 `active_for_operations`；禁用涉事 Membership；保留日志和数据库备份。检查 Organization/Venue 条件、业务链接、Trace、报告投影和 Tool result。未证明隔离恢复前不得重新启用。

### 5.4 对账异常

从案件给出的现有业务入口核对，不运行 Agent 生成的 SQL，也不直接修改数据库。按资金与课时安全、工资结算、排期冲突、一般状态不一致的顺序处理。修复后重新运行 `reconciliation.failed` 扫描；只有兼容规则重跑通过才关闭案件。

## 6. 回滚

功能回滚优先采用开关：

1. 关闭 `write_tools_enabled`；
2. 关闭 `model_enabled`；
3. 必要时关闭 `active_for_operations`；
4. 保留业务页面和历史运营记录；
5. 数据库降级仅在已验证的备份/恢复方案下执行。

已成功执行的业务写入不得通过删除 OperationRun、ToolCall 或 Approval 回滚。应使用现有业务流程处理后续调整，并保留原 AuditLog。

## 7. 重新启用门槛

根因与影响范围明确、Scope/权限复核通过、active Policy 正确、相关确定性复核通过、写入幂等结果明确后，按“只读 → 模型 → 写工具”的顺序逐级恢复。每一级至少完成一次当前 Venue 的人工抽查，再开启下一级。

## 8. CI 与发布验证入口

日常开发优先运行高风险聚焦回归：

```powershell
pnpm test:operations:core
pnpm api:check
pnpm --dir frontend typecheck
```

计划发布时可运行当前已存在的完整后端分层验证：

```powershell
pnpm test:operations:all
```

离线 Eval、智能运营前端组件测试和完整 Playwright 场景当前按产品决定延后，因此尚未配置成可误认为已通过的命令。补齐对应测试文件后再启用这些 CI 入口。`live_model` 用例只在受控发布或夜间环境显式运行，不作为普通 PR 的唯一门禁。涉及数据库迁移、Scope、补排写入、审批或并发的变更仍必须在 SQLite 与 PostgreSQL 分别验证；未执行的层级不得记录为通过。
