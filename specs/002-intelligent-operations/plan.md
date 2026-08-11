# Implementation Plan: 智能运营系统

**Branch**: `002-intelligent-operations` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-intelligent-operations/spec.md`

## Summary

在现有 ShuttleCube 模块化单体中增加案件驱动的智能运营系统：先建立 Organization／Venue 数据作用域、服务端 capability、版本化 OperationsPolicy 和结构化 CaseActivity，再实现确定性 Detector、Verifier、经营报告 Snapshot、普通 Python 状态机、数据库 checkpoint／lease、受控 Tool Registry、审批和 Trace。LLM 不直接访问数据库，只消费脱敏后的结构化 Tool 结果；金额、课时、排期合法性、报告指标、异常和案件关闭全部由确定性程序负责。

Clarification 后的固定边界是：外部模型按 Venue 默认关闭并由负责人显式启用；前台／运营只能看到当前跟进案件必要的单笔欠费信息，不能通过报告、Narrative 或 Trace 获取全馆财务／工资；Detector 只把案件放入确定性 capability 队列，具体人员由认领或具备 `operations.case.assign` 的负责人分配；补排 Agent 只能选择已生成并冻结的 resource_plan；CourtBlock 作为不可售容量从利用率分母扣除，不计经营使用。

首个模型适配器采用 OpenAI Python SDK 的 Responses API，通过项目内 `ModelClient` Port 隔离 provider。计划／诊断和报告 Narrative 使用严格 JSON Schema／Pydantic Structured Outputs；需要模型选择只读 Tool 时使用 strict function calling。业务 Tool 仍由 ShuttleCube Registry、Scope、Policy、权限和审批执行，不采用 OpenAI Agents SDK、LangGraph、MCP、Celery、Redis、Temporal、向量数据库或独立 AI Gateway。

## Technical Context

**Language/Version**: Python 3.14；TypeScript 5.8；React 19；Node.js Active LTS

**Primary Dependencies**: FastAPI 0.116+、Pydantic 2、SQLAlchemy 2、Alembic、Psycopg 3、OpenAI Python SDK；React Router 7、TanStack Query、Zod、shadcn/ui、Tailwind CSS 4

**Storage**: PostgreSQL 17+ 服务端；SQLite 桌面版；现有私有 S3／本地附件存储继续使用但不向模型暴露原始附件

**Testing**: pytest、Hypothesis、FastAPI TestClient、Testcontainers PostgreSQL；Vitest、React Testing Library；Playwright；OpenAPI 客户端漂移检查；离线模型 Stub Eval 与独立真实模型 Eval

**Target Platform**: Linux Docker Compose 服务端；Windows 单机桌面版；当前桌面 Chromium／Edge／Firefox 管理界面

**Project Type**: 单仓库前后端分离 Web 应用，同时支持本地桌面封装；FastAPI 模块化单体 + React 管理端

**Performance Goals**: 当前规模案件列表和确定性证据 2 秒内可用；当前规模报告 3 秒内；15 片场地夹具下 14 天补排候选 3 秒内、确定性月报 5 秒内、启动 catch-up 60 秒内；模型内容异步后补

**Constraints**: 首版每个部署只启用一个 Venue，但所有数据和运行显式携带 Organization／Venue Scope；模型按 Venue 默认关闭且 provider 凭据不能自动开启；固定角色包和 capability 对 REST、Tool、模型上下文、Narrative 与 Trace 使用同一字段投影；SQLite 与 PostgreSQL 行为一致；模型完全禁用时确定性功能仍可用；无任意 SQL／HTTP／文件 Tool；高风险业务写不进入 MVP Registry；所有副作用可审计、可幂等恢复

**Scale/Scope**: 单场馆 4—15 片场地、少量内部人员；至少 5,000 名联系人、250,000 条资源占用、1,000,000 条流水／审计；两个 Organization、多 Venue 仅用于隔离测试，不提供首版跨场馆 UI

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

项目 constitution 仍是未批准模板，没有可执行的正式原则。以下 gate 来自 `AGENTS.md`、现有架构和本 Spec，作为本计划的临时强制边界：

- **Real-code gate — PASS**: 计划复用现有 Commands、Queries、ScheduleAllocation、AuditLog、会话、CSRF、Alembic 和测试体系；不把 specs/001 的未实现 Agent 草案当作现状。
- **Deterministic-authority gate — PASS**: 金额、课时、状态、冲突、指标、异常、Policy 和 Verifier 全部由普通业务代码裁决；模型仅解释、排序、规划和生成草稿。
- **Scope and security gate — PASS**: Phase 0 先完成 Organization／Venue Scope 和 capability；跨 Scope 请求安全失败；写 Tool 在 Scope、权限、版本、审批和影响重新校验后才可执行。
- **Simplicity gate — PASS**: 继续使用模块化单体、现有数据库和轮询；不引入多 Agent、队列、工作流平台、向量库或 AI Gateway。
- **Recovery gate — PASS**: Run、ToolCall、Approval、lease、checkpoint 和幂等结果持久化；未知提交结果先 outcome reconciliation，禁止盲目重试。
- **Test gate — PASS**: 作用域、资金／课时、写 Tool、审批、恢复和状态机均有 SQLite／PostgreSQL 自动化测试；真实模型回归与 PR 离线 CI 分离。
- **Documentation gate — PASS**: 数据模型、REST 契约、Tool 契约和验证指南在实施前冻结，后续公共接口或 Agent 边界变化必须同步文档。

### Post-design re-check

Phase 1 设计没有突破上述 gate。新增表仍在同一数据库；唯一外部依赖是可关闭、可替换的模型 adapter；REST、Tool、状态和数据模型均有确定性测试边界。正式编码前仍建议单独批准项目 constitution，但其模板状态不阻断本计划。

## Architecture and Delivery Strategy

### 1. Scope-first migration

先创建默认 Organization，把现有 Venue、目录和业务事实回填到该 Scope，再将 Agent 使用的 Query／Command 改为强制接收 `RequestScope`。所有迁移完成和隔离测试通过前，`operations_enabled` 与 Agent 写 Tool 保持关闭。服务端会话解析 Scope 和固定角色 capability；前端和 LLM 不能传入或覆盖 organization_id／venue_id。Venue 的 `model_enabled` 默认 false，只能由 `operations.model.manage` 明确变更；现有 finance、payroll、report API 也必须使用相同最小权限，不能只保护 Agent 页面。

### 2. Deterministic operations kernel

在 `application/operations/` 建立 Detectors、Evidence Queries、Policy loader、State Machine、Candidate Generator、Report Builder 和 Verifiers。它们不依赖模型，可以由 API、Runner 和测试直接调用。每个 Detector 输出标准 Evidence、fingerprint、policy_version、source_refs、queue_key 和 required_capability；LLM 不选择具体员工。经营报告将 CourtBlock 识别为不可售容量，按对应场地和时间并集扣减分母，但仍作为补排冲突。

### 3. Persistent runtime harness

使用普通 Python 显式状态机和数据库 checkpoint。FastAPI lifespan 启动轻量 polling Runner；Runner 每次短事务领取一个带 Scope 的 lease，模型调用和等待审批不占数据库事务。通过内部 `OperationsExecutor` 接口隔离运行位置，未来如需独立进程只移动 Executor，不改变数据库状态模型。

### 4. Model and Tool boundary

`ModelClient` 只在当前 Venue 已显式启用时接受脱敏、尺寸受限且按目标受众 capability 投影的 Pydantic 输入，并返回严格结构化结果。OpenAI adapter 使用 Responses API：报告和最终诊断采用 `text.format` Structured Outputs；需要模型选择已注册只读 Tool 时采用 strict function calling。模型看到的是 Registry 投影，不得到 ORM、数据库连接、任意 URL、文件、凭证或动态工具。

### 5. Controlled side effects

MVP 只有 `record_followup_outcome`（CaseActivity）和 `schedule_cancelled_class_replacement` 两个写边界。CaseActivity 需要人员显式确认；补排必须从服务端生成的未过期 resource_plan 创建不可变 ToolCall 与 Approval，不接受人工或模型提交任意新时段，并在执行前重新验证 Scope、capability、policy_version、input_hash、subject_versions、资源方案和审批有效期。

### 6. UI and polling

新增 `/operations` 功能切片，提供每日简报、角色队列、认领／分配、案件详情、结构化跟进、报告、审批卡和 Trace 时间线。运行状态使用 TanStack Query 轮询；确定性内容先显示，模型 Narrative 后补。现有 `/reports` 可保留并跳转到新的确定性 Snapshot 报告视图；所有页面和 API 使用同一 capability 投影，避免 UI 隐藏但 API 泄露。

## Implementation Phases

### Phase 0 — Commercialization foundation

1. Organization、Venue 所有权、Membership、固定角色 capability、字段投影和默认关闭的 per-Venue 模型开关。
2. 业务聚合 Scope 回填、唯一约束调整、`select(Venue).limit(1)` 消除。
3. OperationsPolicy 版本、负责人确认与 feature flag。
4. CaseActivity、Operation 基础表和迁移／恢复测试。
5. 经营使用、CourtBlock 不可售容量、原始／展示利用率和营业时间外占用的确定性报告口径。

### Phase 1 — Deterministic operations center

1. 六类初始 Detector、Case 去重／occurrence、确定性责任队列／认领／分配、State Machine 和 Verifier。
2. 每日简报、手动扫描、15 分钟扫描和启动 catch-up。
3. 日／周／月 OperationsReportSnapshot、对比窗口、异常规则和 metric_ref。
4. 案件／报告 REST API 和 React 只读工作区。

### Phase 2 — Read-only intelligence and revenue retention

1. ModelClient、OpenAI adapter、Prompt／Schema 版本和模型降级。
2. 欠费／续费证据、计划、沟通草稿和 CaseActivity。
3. 报告 Narrative、数值引用渲染和拒绝／错误处理。
4. Trace、用量、离线 Eval 和独立真实模型回归。

### Phase 3 — Approved replacement execution

1. 版本化 resource_plan 和 deterministic candidate generator；Agent 流程只接受已生成候选。
2. Tool Registry、ToolCall、Approval、幂等结果和 lease 恢复。
3. 复用 `schedule_cancelled_session_replacement`，MVP 仍限制原教练／原场地。
4. stale、并发冲突、提交后崩溃、Verifier 和端到端审批闭环。

### Phase 4 — Hardening and rollout

1. 两 Organization、多 Venue 和 4／10／15 场地回归。
2. PostgreSQL 并发、SQLite 重启、性能、保留和迁移回滚验证。
3. 安全 Eval、Prompt／Tool 版本门禁和逐场馆 feature flag 灰度。
4. 只有真实运行证据证明需要 24×7 或吞吐扩展时，另立计划评估独立 Worker。

## Project Structure

### Documentation (this feature)

```text
specs/002-intelligent-operations/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   └── tool-contracts.md
└── tasks.md                 # 由 /speckit-tasks 生成，本计划不创建
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/        # Scope、Policy、Operation runtime 分阶段迁移
├── src/shuttlecube/
│   ├── api/
│   │   ├── dependencies.py  # RequestScope / capability dependencies
│   │   └── v1/
│   │       └── operations.py
│   ├── application/
│   │   └── operations/
│   │       ├── candidates.py
│   │       ├── access.py
│   │       ├── assignments.py
│   │       ├── detectors.py
│   │       ├── evidence.py
│   │       ├── model_client.py
│   │       ├── policies.py
│   │       ├── reports.py
│   │       ├── runtime.py
│   │       ├── state_machine.py
│   │       ├── tools.py
│   │       └── verifiers.py
│   ├── domain/
│   │   ├── identity/        # Organization / Membership / Venue scope
│   │   └── operations/
│   │       ├── models.py
│   │       ├── policy_models.py
│   │       └── schemas.py
│   └── infrastructure/
│       └── ai/
│           └── openai_client.py
└── tests/
    ├── unit/operations/
    ├── integration/operations/
    ├── contract/test_operations_contract.py
    ├── eval/operations/
    └── fixtures/operations/

frontend/
└── src/features/intelligent-operations/
    ├── api.ts
    ├── operations-center-page.tsx
    ├── case-detail-page.tsx
    ├── report-page.tsx
    ├── components/
    └── *.test.tsx

e2e/specs/
└── 04-intelligent-operations.spec.ts
```

**Structure Decision**: 保持现有前后端目录和模块化单体。Agent Runtime 属于 `application/operations`，ORM 事实属于 `domain/operations`，provider adapter 属于 `infrastructure/ai`；禁止在前端、Prompt 或 provider adapter 中复制业务规则。

## Migration and Rollout Gates

1. **Migration gate**: 默认 Organization／Venue 回填数量与原表数量一致；孤立或冲突记录生成迁移报告并阻断写 Tool。
2. **Permission gate**: 现有 active SystemUser 先进入待复核 Membership；负责人确认前所有 Agent 写 Tool disabled；前台角色无法通过既有 API、Tool、Narrative 或 Trace 获取全馆财务／工资。
3. **Policy gate**: 对应 Detector 没有 active policy_version 时返回 `policy_not_configured`，不创建案件。
4. **Deterministic gate**: 模型关闭时 Scope、扫描、Case、Verifier 和报告全部通过。
5. **AI gate**: 离线安全 Eval 达标后仍需负责人按 Venue 显式启用只读模型功能；provider 凭据不自动启用；真实模型失败不影响确定性内容。
6. **Write gate**: 补排 Tool 的 PostgreSQL 并发、SQLite 重启、幂等和 Approval 测试全部通过后才启用。
7. **Rollout gate**: model 与 write-tool feature flag 分别按 Venue 打开；任何跨 Scope、字段泄露、安全或重复副作用回归立即关闭对应能力。

## Complexity Tracking

无 constitution 违规需要例外。新增 Organization／Venue Scope 和持久化 Runtime 是 Spec 明确要求且用于避免商业化返工；没有引入新的部署服务或分布式基础设施。
