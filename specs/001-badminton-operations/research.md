# Phase 0 Research: 羽毛球经营管理与未来 AI 扩展

## 1. 当前版本范围

**Decision**: 当前版本交付完整经营管理系统，AI 仅保留“规划中”入口和架构边界；不实现定时提醒、自动 Agent、自然语言控制、模型调用、工作流、实时状态或审批。

**Rationale**: 用户已认可现有静态页面方向，当前价值与风险集中在排期、课时、资金和结算正确性。延后 AI 运行时可以显著降低首版基础设施、安全、测试和运维复杂度，同时不阻碍未来接入。

## 2. 总体架构

**Decision**: 单仓库前后端分离的模块化单体：React 管理端、FastAPI 业务 API、PostgreSQL 主数据库和私有 S3 兼容对象存储。

**Rationale**: 排期、课时、资金和结算需要跨实体强事务；模块化单体能保持一个事务边界和一套业务规则。独立前端适合复杂排期、表单、仪表盘及未来 AI 交互。

**Alternatives considered**: 微服务过早引入分布式事务；服务端模板难以复现已确认的交互体验；当前不需要任务队列和实时事件基础设施。

## 3. 前端与设计系统

**Decision**: React 19、TypeScript strict、Vite、pnpm、shadcn/ui、Tailwind CSS 4、Radix UI、Lucide React 和 Motion。

**Rationale**: shadcn/ui 的组件源码归项目所有，既能维持当前静态页面的视觉方向，也能在未来为对话、运行状态和审批组件进行深度定制。

**Alternatives considered**: Ant Design 5/Pro Components 更偏标准 CRUD 后台，但自定义品牌与未来 Agent 交互时需要较多覆盖；完全自研无头组件成本过高。

## 4. 前端数据与业务交互

**Decision**: React Router 7、TanStack Query/Table、React Hook Form、Zod、FullCalendar、Apache ECharts 和 Day.js。当前不安装 Zustand、TanStack Virtual、AI SDK、React Flow、Monaco 或 xterm.js；真正出现需求时再引入。

**Rationale**: 服务端事实由 TanStack Query 管理；当前跨组件临时状态不足以证明需要全局 store。按需依赖能减少包体、升级面和自动生成代码量。

## 5. 后端、数据与接口

**Decision**: Python 3.14、FastAPI、Pydantic 2、SQLAlchemy 2、Psycopg 3、Alembic、PostgreSQL 17+；REST/JSON 和 OpenAPI 3.1 为当前唯一接口契约。

**Rationale**: PostgreSQL 的事务、约束、范围检查和锁为排期冲突、余额、退款及结算提供最终保护。应用层命令与查询封装权限、验证、事务、幂等和审计，人工 UI 与未来 Agent 都只能通过该边界执行业务。

## 6. 认证、凭证和部署

**Decision**: Argon2、PostgreSQL 服务端会话、HttpOnly/Secure/SameSite Cookie、CSRF；付款凭证存私有 S3 兼容存储。Docker Compose 运行 Nginx、frontend、api、PostgreSQL 和 object-storage。

**Rationale**: 两名内部用户不需要 OAuth/SSO；服务端会话便于吊销和审计。对象存储避免在数据库中混入大型二进制，并保持鉴权下载与独立备份。

## 7. 测试与质量

**Decision**: 后端 pytest、HTTPX、Hypothesis 和真实 PostgreSQL；前端 Vitest、React Testing Library、MSW；Playwright 覆盖六条业务旅程和 AI 占位无副作用检查；OpenAPI 生成客户端并做契约漂移检查。

**Rationale**: 真实 PostgreSQL 才能证明排期范围和并发事务行为。AI 占位测试只需证明它无需配置、没有外部请求且不会写业务数据。

## 8. AI 占位实现

**Decision**: `frontend/src/features/ai-placeholder/` 包含静态配置、说明页面和导航入口，明确标记“规划中”。不创建 AI 后端路由、数据库迁移、环境变量、队列、Worker 或模型适配器。

**Rationale**: 产品层可展示未来方向，但不能让用户误以为已经具备自动化能力，也不能让未使用的 AI 基础设施成为当前业务的启动条件。

## 9. Future Decision Record: Agent Runtime

以下仅是未来重新评估时的候选边界，不属于本期依赖、任务或验收：

- LangGraph 可作为持久化状态图候选；Celery + Redis 可作为长任务与队列候选；SSE 可作为浏览器单向实时状态候选。
- 模型通过供应商网关接入，外部工具可通过显式允许的 MCP 适配器接入，但连接协议不能替代系统授权。
- Agent 只能调用应用层业务用例，不能直接访问仓储、任意 SQL、代码执行或宿主机 Shell。
- 工具必须分级；退款、课时、取消、改期、结算和资金作废等高风险动作必须人工审批并在执行前复核业务版本。
- 外部内容默认不可信；运行必须有幂等、预算、审计、故障恢复和不确定结果人工核验。
- 真正排入版本后再决定 Langfuse/OpenTelemetry、模型评估、工作流设计器和对象产物等实现细节。

## Research Resolution

当前版本技术栈和范围已确定：先交付稳定经营管理与静态 AI 占位，不引入任何 AI 运行时。未来候选方案被记录但未被采用，没有待澄清技术项。
