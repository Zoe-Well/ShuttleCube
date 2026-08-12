# Phase 0 Research: 智能运营系统

## 1. 架构形态

**Decision**: 保持 React + FastAPI + SQLAlchemy 的模块化单体，Agent Runtime 与业务服务同进程、同数据库起步；通过内部 Executor 接口保留未来独立进程可能性。

**Rationale**: 当前规模是单场馆 4—15 片场地和少量内部人员。排期、课时、资金、审批、ToolCall 和审计需要强事务或可验证的 outcome reconciliation，同一模块化单体最容易保持一致性。

**Alternatives considered**: 微服务增加分布式事务；Celery／Redis 增加部署和恢复面；Temporal／LangGraph 对当前少量固定工作流收益不足；FastAPI BackgroundTasks 不提供持久恢复。

## 2. 商业化数据作用域

**Decision**: 引入 `Organization → Venue`，第一版每个部署只激活一个 Venue，但 Request、Query、Command、Operation 实体、报告、审计和模型上下文全部显式绑定 Scope。

**Rationale**: 当前仅 Court 有 venue_id，多个查询读取第一条 Venue。若先实现 Agent 再补 Scope，会同时重写报表、Detector、Tool、权限和 Trace，且存在跨球馆数据泄露风险。

**Alternatives considered**: 永久保持每客户独立数据库会限制集中 SaaS；现在实现完整多租户 UI 和计费超出范围；只在 Agent 表增加 venue_id 不能保证业务证据隔离。

## 3. Scope 迁移策略

**Decision**: 分阶段迁移：创建默认 Organization → 关联现有 Venue → 为目录和业务事实增加 nullable Scope → 确定性回填与数量校验 → 调整 scoped unique indexes → 改为非空 → 切换应用 Query。迁移期间 Agent feature flag 关闭。

**Rationale**: SQLite 桌面数据必须可就地升级，PostgreSQL 服务端也不能在回填未验证时暴露 Agent。分阶段迁移允许输出孤立记录和冲突报告，不通过静默默认值掩盖问题。

**Alternatives considered**: 一次性非空迁移难以诊断 legacy 数据；只在运行时 join 推断 Venue 会延续隐式作用域；数据库级 RLS 不能覆盖 SQLite，首版不作为唯一安全边界。

## 4. 用户成员关系与能力

**Decision**: 新增 OrganizationMembership 和 VenueMembership；`role_key` 映射到版本控制的 capability registry。现有 active SystemUser 迁移为待复核成员，负责人确认前 Agent 写 Tool 禁用。

**Rationale**: 当前 SystemUser 没有 owner／admin 角色，不能假设某账号天然具备审批权限。代码注册 capability 比数据库自由编辑权限更容易测试和审计。

**Alternatives considered**: 给所有现有用户自动全权风险过高；只在前端隐藏按钮不构成授权；第一版引入复杂 ABAC／IAM 不必要。

## 5. 场馆运营策略

**Decision**: 使用不可变、按 Venue 版本化的 `OperationsPolicy` JSON 配置，由严格 Pydantic Schema 解析；不实现通用规则 DSL。未配置或未激活的规则保持禁用。

**Rationale**: 欠费账龄、续费窗口、考勤宽限、补排窗口和异常阈值会随球馆变化，但规则结构仍是有限、已知的确定性参数。每个 Case、Run、Approval 和 Snapshot 冻结 policy_version 可重现历史。

**Alternatives considered**: 硬编码全局常量会导致客户分支；动态脚本／规则引擎扩大攻击面；LLM 自行决定阈值不可测试。

## 6. Case、Activity 与 Trace

**Decision**: OperationCase 保存持续问题；CaseActivity 保存人员真实跟进；OperationEvent 只保存追加型 Runtime Trace。三者通过 case_id／run_id／trace_id 关联，不互相替代。

**Rationale**: “已联系、暂不续费、承诺付款、下周再联系”会用于责任和转化统计，是业务事实而非模型日志。Trace 的保留、脱敏和演进需求不同。

**Alternatives considered**: 全部写入 OperationEvent 会让报表依赖运行日志；完整 CRM 超出范围；把跟进摘要写进 Receivable 或 Enrollment 会污染原业务聚合。

## 7. OperationCase 去重与 occurrence

**Decision**: 一个 scoped detector_key + subject_type + subject_id 对应一个 Case；问题重现时增加 occurrence_no 并追加关闭／重开事件，不创建活动重复行。fingerprint 只标识当前证据版本。

**Rationale**: 该方案在 PostgreSQL 和 SQLite 都能使用普通唯一约束，避免跨数据库 partial unique index 差异，同时保留完整历史。

**Alternatives considered**: 每次 occurrence 新建 Case 需要活动行部分唯一约束；只以 fingerprint 唯一会在证据变化时产生重复案件。

## 8. Runtime 与主动调度

**Decision**: 普通 Python 状态机 + 数据库 checkpoint／lease；FastAPI lifespan 启动轮询 Runner，使用短事务条件领取。等待审批和模型调用不持有数据库事务。

**Rationale**: 当前负载低，数据库已经是事实源；lease 能覆盖桌面重启和服务端多进程。Executor Port 使未来独立 Worker 无需改变状态模型。

**Alternatives considered**: 纯内存 asyncio task 无法恢复；系统 cron 不适合桌面；消息队列在当前吞吐下没有证明必要。

## 9. Tool 与业务调用边界

**Decision**: Tool Registry 保存在代码中，Handler 直接调用应用层 Query／Command；模型永远不接触 Session、Repository、SQL、任意 HTTP、文件或动态插件。

**Rationale**: 现有业务规则和审计已经集中在 Commands／Queries，复用该层可以保证人工 UI 与 Agent 受到相同约束。Tool Schema、风险、capability、审批、幂等和脱敏均可版本化测试。

**Alternatives considered**: MCP 对首版内部调用没有收益；内部 HTTP 增加身份和事务复杂度；自然语言转 SQL 无法满足隔离和写入安全要求。

## 10. 首个模型 Provider

**Decision**: 定义项目内 `ModelClient` Protocol，首个 adapter 使用 OpenAI Python SDK + Responses API，默认模型 profile 从配置读取，首个受支持 profile 选择 `gpt-5.6`；模型未配置时使用 DisabledModelClient，测试使用 StubModelClient。

**Rationale**: OpenAI 官方 Structured Outputs 文档说明 Responses API 可按 JSON Schema 约束输出，Python SDK 可直接用 Pydantic 解析；连接应用工具时使用 function calling，生成结构化用户响应时使用 `text.format`。官方文档当前建议新项目从 gpt-5.6 开始。该能力符合计划、报告和拒绝状态的严格 Schema 需求。[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

**Evolution after desktop validation**: 桌面用户需要自行选择供应商，因此在同一 `ModelClient` 边界内增加 DeepSeek Chat Completions 和自定义 OpenAI 兼容协议。继续复用 OpenAI Python SDK 的兼容客户端，不增加独立 AI Gateway；两类协议都必须在本地执行 Pydantic 输出校验。

**Alternatives considered**: OpenAI Agents SDK 会复制本项目已有 Runtime／Tool／审批状态；直接拼 HTTP 会重复 SDK 的连接、超时和错误处理；只修改验证接口会导致 DeepSeek 保存成功但实际工作流仍调用 Responses API，因此验证和运行适配必须同时切换。

## 11. Structured Outputs 与 Tool calling

**Decision**: 报告 Narrative 和最终计划使用 Pydantic-backed Structured Outputs；模型需要选择只读 Tool 时使用 strict function calling。所有字段 required，optional 值以 nullable 表达，对象禁止额外字段；结果仍经过本地 Pydantic 与引用校验。

**Rationale**: Schema adherence 只能解决结构问题，不能保证业务事实正确。因此 metric_ref、anomaly_id、source_ref、tool_key、ID Scope 和数值仍由确定性程序二次验证和渲染。

**Alternatives considered**: JSON mode 只保证合法 JSON；自由文本解析不可靠；把 Tool 结果直接拼接成系统指令会增加提示注入风险。

## 12. 报告 Snapshot 与利用率

**Decision**: 现有 `get_operations_report` 作为基础，但新 ReportBuilder 必须显式 Scope、区分 period／as_of、保存 metric_ref，并保留 raw utilization、display utilization、营业时间外占用和数据质量异常。Snapshot 的确定性 payload 保存后不可改。

**Rationale**: 当前查询混合期间发生指标与查询时点余额，并把利用率截断到 100%。新模型必须保留真实口径，避免模型或 UI 掩盖数据异常。

**Alternatives considered**: 直接让 LLM读取当前报表 JSON 会丢失口径和引用；覆盖旧 Snapshot 会破坏审计；为历史时点余额补造数据不可接受。

## 13. 补排资源方案

**Decision**: Candidate Generator 输出不可变 `resource_plan_id` 和 resource_policy_version。MVP Policy 仍只产生原教练 + 原场地，Tool 复用现有 `schedule_cancelled_session_replacement`；未来其他合法场地必须由新确定性服务和新 Tool 版本支持。

**Rationale**: 当前 Command 会复用原排期全部资源，不能假设已有换场能力。现在版本化方案 Schema 可避免未来 10—15 片场地优化时重做 Agent 协议。

**Alternatives considered**: 让模型自选场地违反冲突边界；现在扩展换场业务超出本 MVP；永久写死原场地会降低未来可用性。

## 14. 事务、幂等与未知结果

**Decision**: ToolCall 在 `(venue_id, tool_key, idempotency_key)` 唯一。业务写和 Tool 结果优先同事务提交；无法同事务时保存可查询业务关联并在恢复时先 outcome reconciliation。`executing` 中断不得直接重试。

**Rationale**: 现有若干 Command 自行 commit，补排只有 state + version 防重。Runtime 必须能区分“未执行、已成功、结果未知”，否则重启会产生重复课程。

**Alternatives considered**: 仅依赖浏览器防双击或进程锁不能跨重启；对未知结果自动重试不安全；分布式事务不必要。

## 15. API 与前端进度

**Decision**: 内部 REST/JSON + TanStack Query 轮询。确定性扫描、Case、Activity、Report、Policy、Approval 暴露版本化 API；模型运行通过 Run 状态轮询，不实现 SSE／WebSocket。

**Rationale**: 运行量小、审批等待长，轮询最符合现有前端架构。REST Contract 可继续生成 TypeScript 类型并做漂移检查。

**Alternatives considered**: SSE 增加桌面代理和断线回放实现；WebSocket 双向能力无需求；前端本地状态不能作为 Runtime checkpoint。

## 16. Tracing、Audit 与保留

**Decision**: OperationEvent 记录脱敏 Trace，CaseActivity 记录人工运营事实，AuditLog 记录业务事实变化；共享 trace_id／request_id。默认不长期保存原始 Prompt／Response，只保存 hash、结构化结果、错误和用量。

**Rationale**: 可追溯性必须覆盖“为什么建议、谁批准、执行了什么、如何验证”，同时最小化联系人和凭证进入模型日志的风险。

**Alternatives considered**: 只用应用日志无法查询业务闭环；只用 AuditLog 无法解释模型和 Runtime；保存所有原文增加隐私和保留风险。

## 17. Eval 与 CI

**Decision**: 分为规则、Tool Contract、Runtime Integration、Agent Scenario、业务 E2E、Scope Isolation 和真实模型回归。PR CI 使用 Stub／录制结果；真实模型 Eval 独立运行。两个 Organization、多 Venue、4／10／15 场地为固定夹具。

**Rationale**: 资金、课时、隔离、审批和副作用必须 100% 确定；模型质量可统计评估但失败必须安全停止。外部 provider 波动不能让普通 PR 不稳定。

**Alternatives considered**: 只做 Prompt 示例无法验证状态和副作用；所有 CI 调真实模型成本高且不稳定；只测 SQLite 无法证明 PostgreSQL lease 和并发。

## 18. Infrastructure deferral

**Decision**: 不引入 Redis、Celery、Kafka、Kubernetes、Temporal、LangGraph、MCP、向量数据库或独立 AI Gateway。通过 Executor、ModelClient 和 Tool Registry Port 保留替换边界。

**Rationale**: 15 片场地不会形成分布式吞吐需求。未来扩展通常只需要移动 Executor 或新增 ModelClient adapter，不需要改变 Case／Run／Tool／Approval 数据模型。

**Alternatives considered**: 预建企业级基础设施会增加部署、桌面兼容、CI 和故障恢复成本，却不能提高当前业务正确性。

## Research Resolution

所有 Technical Context 已确定，没有 `NEEDS CLARIFICATION`。商业化基础限定为 Scope、Policy、Membership 和隔离，不包含首版多场馆 UI／集团报表／SaaS 计费；模型 provider、Runtime、API、数据和测试边界均已形成可实施决策。
