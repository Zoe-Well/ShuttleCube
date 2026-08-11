# Implementation Plan: 羽毛球培训与场地经营管理（AI 扩展占位）

**Branch**: `001-badminton-operations` | **Date**: 2026-07-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-badminton-operations/spec.md`

## Summary

建设供单一羽毛球馆内部管理人员使用的桌面端 Web 系统，以统一排期和强冲突校验为业务核心，贯通固定班、报名、考勤课时、请假保留课时、权益转移、私教、散客订场、临时活动、收退款、教练结算与经营统计。当前版本以用户已确认满意的 shadcn/ui 静态页面方向为视觉基线，只提供标记为“规划中”的 AI 助手占位入口。

采用单仓库前后端分离架构：React + TypeScript 管理端使用 shadcn/ui 与 Tailwind CSS 建立自有设计系统；FastAPI 模块化单体负责业务 API、权限和事务；PostgreSQL 保存业务事实与审计记录，私有 S3 兼容存储保存付款凭证。当前版本不安装或运行 LangGraph、Celery、Redis、模型 SDK、MCP、Agent Worker、SSE Agent 事件或 AI 可观测平台。核心业务通过应用层命令和查询保持清晰边界，为未来自然语言控制和自动 Agent 复用，但本期不会执行任何 AI 自动化。

## Technical Context

**Language/Version**: 后端 Python 3.14；前端 TypeScript 5.x、React 19；Node.js 使用 Active LTS，补丁版本由锁文件固定

**Primary Dependencies**: 后端 FastAPI、Pydantic 2、SQLAlchemy 2、Psycopg 3、Alembic、Argon2；前端使用 Vite、shadcn/ui、Tailwind CSS 4、Radix UI、Lucide React、React Router 7、TanStack Query/Table、React Hook Form、Zod、FullCalendar、Apache ECharts、Motion、Day.js

**Storage**: PostgreSQL 17+ 保存业务与审计记录；私有 S3 兼容存储保存付款凭证；当前版本不需要 Redis 或 Agent 运行存储

**Testing**: 后端 pytest、HTTPX、Hypothesis；前端 Vitest、React Testing Library、MSW；OpenAPI 契约测试；Playwright 覆盖六条业务旅程和 AI 占位无副作用检查

**Target Platform**: Nginx 提供前端静态资源并反向代理 API；Linux 运行 FastAPI；支持当前主流桌面 Chromium、Edge 和 Firefox；开发环境兼容 Windows PowerShell

**Project Type**: 单仓库前后端分离 Web 应用；React 管理端 + FastAPI 模块化单体

**Performance Goals**: 95% 常用页面和排期查询在 2 秒内呈现可用结果；排期冲突检查在 2 秒内返回

**Constraints**: 单机构、四片场地、两名并发管理人员；后端是业务规则最终裁决者；当前 AI 入口必须是无网络、无模型、无后台任务、无业务写入的静态占位；业务写入必须幂等且可审计

**Scale/Scope**: 第一版覆盖 10 个经营业务领域、约 25 个核心实体、6 条业务端到端旅程和 1 条 AI 占位检查；支持至少 5,000 名联系人、250,000 条资源占用和 1,000,000 条流水/审计记录而无需改变架构

## Technology Stack Decisions

### Frontend and Design System

| Concern | Adopted choice | Notes |
|---|---|---|
| Framework | React 19 + TypeScript strict mode | 独立管理端；组件不复制后端业务规则 |
| Build and packages | Vite + pnpm workspace | 前端依赖由 `pnpm-lock.yaml` 固定 |
| UI system | shadcn/ui + Tailwind CSS 4 + Radix UI | 组件源码归项目所有；通过 CSS 变量和设计 Token 建立品牌体系 |
| Icons and motion | Lucide React + Motion | 图标统一；动画仅用于状态变化、面板和工作流反馈 |
| Routing | React Router 7 | 页面路由、权限入口和 URL 查询状态 |
| Server state | TanStack Query 5 | 请求缓存、失效和错误状态；不复制到全局 store |
| Client state | React local state；必要时再引入 Zustand | 当前无复杂跨页客户端状态，不提前增加全局 store |
| Forms | React Hook Form + Zod | 交互校验；后端 Pydantic 仍为最终边界 |
| Tables | TanStack Table + 项目级 `DataTable` | 统一分页、筛选、列设置、批量操作和空状态 |
| Schedule | FullCalendar React | 拖拽只产生变更草案；后端通过后才确认 |
| AI placeholder | 独立 `features/ai-placeholder` 静态模块 | 展示“规划中”说明；不安装 AI SDK、React Flow、Monaco 或终端组件 |
| Charts | Apache ECharts | 经营统计、收支趋势和场地利用率 |
| Date/time | Day.js | 机构时区由后端返回并统一展示 |
| API typing | OpenAPI 3.1 + openapi-typescript/openapi-fetch | 生成客户端不可手工编辑 |

### Backend and Infrastructure

| Concern | Adopted choice | Notes |
|---|---|---|
| Business API | FastAPI + Pydantic 2 | REST/JSON、Problem Details 和 OpenAPI |
| Persistence | SQLAlchemy 2 + Psycopg 3 | 显式事务、版本检查和数据库约束 |
| Database | PostgreSQL 17+ + Alembic | 业务事实、事务、版本检查和审计 |
| Authentication | Argon2 + PostgreSQL 服务端会话 + HttpOnly Cookie + CSRF | 不在 localStorage 保存长期令牌 |
| Artifact storage | 私有 S3 兼容存储 | 付款凭证图片；访问必须通过后端鉴权 |
| Application errors | Sentry | 前端和 API 异常；不替代业务审计 |
| Deployment | Docker Compose + Nginx | frontend、api、postgres、object-storage；第一版单机部署 |
| Quality | Ruff + mypy；ESLint + Prettier + TypeScript compiler | CI 阻止类型、契约和质量门槛失败 |

## Future AI Extension Boundary (Not Implemented This Release)

当前版本只实现 `frontend/src/features/ai-placeholder/` 的静态占位页面和功能配置。不会创建 Agent API、数据库表、Worker、队列、实时事件、模型网关、MCP 连接、工具注册或审批流程，也不会安装相关依赖。

未来扩展时遵循以下不变边界：Agent 只能调用现有应用层命令/查询；不得直接访问仓储；退款、课时、取消、改期、结算和作废必须人工审批；权限、冲突、金额、事务、幂等和审计仍由 FastAPI 业务后端最终裁决。未来可评估 LangGraph、Celery、Redis、SSE、模型网关和 MCP，但它们不是本期承诺或部署要求。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

项目宪章当前仍为未填写模板，没有已批准的原则、技术限制或治理条款可供执行。

- **Pre-design gate**: PASS — 以强业务约束、可追溯性、显式事务和最小当前范围为临时治理边界。
- **Simplicity gate**: PASS — 当前只部署 React、FastAPI、PostgreSQL 与对象存储；AI 仅占位，不引入 Redis、Worker 或模型运行时。
- **Testability gate**: PASS — 领域规则、契约和六条业务端到端流程均有独立测试边界，AI 占位可验证无网络和无副作用。
- **Security gate**: PASS — 会话、CSRF、权限、后端规则和审计覆盖当前业务；AI 占位没有执行能力。
- **Post-design re-check**: PASS — 当前范围与用户补充一致，未来 Agent 方案仅作为非执行性边界记录。

> 项目宪章仍为模板；正式实施前建议执行 `$speckit-constitution`，将业务一致性、审计和最小当前范围写入正式宪章。

## Project Structure

### Documentation (this feature)

```text
specs/001-badminton-operations/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── openapi.yaml
└── checklists/
    └── requirements.md
```

`tasks.md` 将由后续 `$speckit-tasks` 生成，本次规划不创建。

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── src/shuttlecube/
│   ├── app.py
│   ├── config.py
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── errors.py
│   │   ├── sse.py
│   │   └── v1/
│   ├── domain/
│   │   ├── identity/
│   │   ├── scheduling/
│   │   ├── classes/
│   │   ├── customers/
│   │   ├── private_lessons/
│   │   ├── venue_bookings/
│   │   ├── events/
│   │   ├── finance/
│   │   ├── payroll/
│   │   ├── audit/
│   │   └── dashboard/
│   ├── application/
│   │   ├── commands/
│   │   ├── queries/
│   │   └── transactions.py
│   └── infrastructure/
│       ├── database/
│       ├── artifacts/
│       └── security/
├── alembic/
└── tests/
    ├── unit/
    ├── integration/
    └── contract/

frontend/
├── package.json
├── components.json
├── vite.config.ts
├── src/
│   ├── app/
│   │   ├── router.tsx
│   │   ├── providers.tsx
│   │   └── theme.css
│   ├── api/
│   │   ├── generated/
│   │   └── client.ts
│   ├── components/
│   │   ├── ui/
│   │   ├── data-table/
│   │   ├── forms/
│   │   └── status/
│   ├── features/
│   │   ├── auth/
│   │   ├── schedule/
│   │   ├── classes/
│   │   ├── customers/
│   │   ├── private-lessons/
│   │   ├── venue-bookings/
│   │   ├── events/
│   │   ├── finance/
│   │   ├── payroll/
│   │   ├── ai-placeholder/
│   │   └── dashboard/
│   ├── layouts/
│   ├── pages/
│   ├── stores/
│   └── test/
└── tests/

e2e/
├── fixtures/
└── specs/

infra/
├── nginx/
├── compose/
├── postgres/
└── object-storage/

pnpm-workspace.yaml
docker-compose.yml
```

**Structure Decision**: 单仓库前后端分离，FastAPI 采用领域、应用用例和基础设施分层，React 按业务功能切片；shadcn 基础组件保存在 `components/ui`，项目级复合组件独立封装，双方以当前业务 OpenAPI 为契约。`ai-placeholder` 只包含静态说明和功能配置，不依赖业务 API。

## Delivery Phases

1. **平台基础**: 前后端骨架、shadcn 设计 Token、OpenAPI 客户端、登录、会话、审计、PostgreSQL、对象存储与错误监控。
2. **排期与基础资料**: 用户、教练、场地、学员、营业时间、统一资源占用、冲突校验和 FullCalendar。
3. **固定班与权益**: 班级、课程实例、报名、考勤、课时流水、请假保留课时、权益转移和机构取消后的整班补排。
4. **其他经营业务**: 私教、散客订场、价格模板、临时活动、收退款、支出和凭证。
5. **教练结算与经营统计**: 教练费用、结算、工作台、场地利用率和经营报表。
6. **AI 扩展占位与质量**: “规划中”入口、未来能力说明、扩展边界文档，以及性能、安全、六条业务端到端验收和占位无副作用检查。

每个阶段必须形成可运行的纵向切片：先固定契约，再实现后端状态与测试，生成前端类型，最后完成 UI 与端到端验证。未来 AI 扩展不得在本期任务中引入运行依赖；当前业务应用层边界和审计必须保持可复用。

## Windows Single-machine Desktop Deployment

The application also supports a Windows single-machine distribution. The React build is served by a FastAPI process bound only to `127.0.0.1` and displayed through pywebview. The packaged application uses SQLite plus local private artifact storage under `%LOCALAPPDATA%\ShuttleCube\Data`; it does not require an external server, Python installation, PostgreSQL, Docker, or internet access at runtime. PostgreSQL and S3-compatible storage remain the server-mode deployment choice.

Desktop transfer folders contain a consistent SQLite snapshot, local attachments, a format/schema manifest, and SHA-256 checksums. Import is a full replacement applied before application startup, with an automatic pre-import backup and database migrations. Device secrets, cached sessions, logs, and runtime locks are not transferred.

## Complexity Tracking

| Added complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| 独立 React 管理端 | 排期、复杂表单、统计和未来扩展需要稳定的组件、路由与类型体系 | 服务端模板难以满足已确认的静态页面体验和复杂交互 |
| 私有对象存储 | 付款凭证需要鉴权、校验和独立备份 | 数据库存二进制会放大备份体积并混合业务与文件生命周期 |

当前不采用 Agent Worker、LangGraph、Celery、Redis、SSE、模型 SDK、MCP、AI 可观测平台、业务微服务、Kafka、Kubernetes、任意代码执行或第二业务数据库。未来 Agent 技术选型在真正进入范围时重新验证。
