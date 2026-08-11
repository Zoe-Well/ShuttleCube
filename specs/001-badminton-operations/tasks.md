# Tasks: 羽毛球培训与场地经营管理（AI 扩展占位）

**Input**: Design documents from `/specs/001-badminton-operations/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/openapi.yaml`, `quickstart.md`

**Tests**: 规格定义了独立验收场景和自动化质量门槛，因此任务包含后端单元/集成/契约测试、前端组件测试与 Playwright 端到端测试。每个故事先写失败测试，再实现功能。

**Scope boundary**: 当前版本不实现 Agent、模型调用、定时任务、自然语言控制、工作流、审批或实时 Agent 状态。`openapi.yaml` 中标记为 future draft 的路径和 `data-model.md` 的 Agent 附录不得生成实现或迁移；US7 只实现静态占位。

**2026-08-09 scope correction**: 学员请假改为通过“不扣课时”保留原权益余额；原班续期后继续使用余额，原班不续期时使用整体权益转移。独立补课资格、跨班目标课次安排、待补课清单和补课考勤已退出当前产品范围。下方早期补课任务仅保留为实施历史，不代表当前有效行为。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可在不同文件上并行实施，且不依赖同阶段未完成任务
- **[Story]**: 对应 `spec.md` 中的用户故事
- 每项任务都给出目标文件路径

## Phase 1: Setup（共享工程基础）

**Purpose**: 建立可构建、可测试、可部署的前后端单仓库骨架

- [X] T001 创建 pnpm workspace 与根级命令脚本，覆盖前端构建、API 生成、检查和 E2E 入口，写入 `pnpm-workspace.yaml` 和 `package.json`
- [X] T002 创建 Python 3.14 FastAPI 后端项目和依赖分组，写入 `backend/pyproject.toml`、`backend/src/shuttlecube/__init__.py` 和 `backend/src/shuttlecube/app.py`
- [X] T003 [P] 创建 React 19 + TypeScript strict + Vite 前端工程，写入 `frontend/package.json`、`frontend/tsconfig.json` 和 `frontend/vite.config.ts`
- [X] T004 [P] 初始化 shadcn/ui、Tailwind CSS 4、Radix 与路径别名，写入 `frontend/components.json`、`frontend/src/app/theme.css` 和 `frontend/src/lib/utils.ts`
- [X] T005 [P] 依据已确认的 shadcn 静态页面提取颜色、间距、圆角、阴影和字体 Token，参考 `prototypes/ui-comparison/app/shadcn/page.tsx` 与 `prototypes/ui-comparison/app/globals.css`，落到 `frontend/src/app/theme.css`
- [X] T006 [P] 配置 Ruff、mypy、ESLint、Prettier 和 TypeScript 检查，写入 `backend/pyproject.toml`、`frontend/eslint.config.js` 和 `frontend/prettier.config.js`
- [X] T007 创建本地 frontend、api、postgres、object-storage 与 Nginx 服务，写入 `docker-compose.yml`、`infra/nginx/default.conf` 和 `infra/compose/.env.example`
- [X] T008 [P] 创建后端 unit/integration/contract 和前端测试入口，写入 `backend/tests/conftest.py`、`frontend/src/test/setup.ts` 和 `playwright.config.ts`
- [X] T009 [P] 配置 OpenAPI 当前业务客户端生成并排除 `x-future-path-prefixes`，写入 `scripts/generate-api-client.mjs`、`scripts/check-api-client.mjs` 和 `frontend/src/api/generated/.gitkeep`

---

## Phase 2: Foundational（阻塞所有用户故事）

**Purpose**: 完成认证、事务、审计、错误契约、应用外壳和共享 UI

**⚠️ CRITICAL**: 本阶段完成前不得开始任何用户故事实现

- [X] T010 创建环境配置与启动校验，确保当前版本不接受或要求 Agent/模型/Redis 配置，写入 `backend/src/shuttlecube/config.py` 和 `backend/tests/unit/test_config.py`
- [X] T011 创建 SQLAlchemy 声明基类、会话工厂、UTC 时间和版本字段 mixin，写入 `backend/src/shuttlecube/infrastructure/database/base.py`、`backend/src/shuttlecube/infrastructure/database/session.py` 和 `backend/src/shuttlecube/infrastructure/database/types.py`
- [X] T012 创建 Alembic 环境与初始数据库扩展配置，写入 `backend/alembic.ini`、`backend/alembic/env.py` 和 `backend/alembic/versions/0001_platform.py`
- [X] T013 [P] 实现统一 Problem Details、Pydantic 验证、409 并发变更和请求关联 ID，写入 `backend/src/shuttlecube/api/errors.py`、`backend/src/shuttlecube/api/middleware.py` 和 `backend/tests/unit/api/test_errors.py`
- [X] T014 [P] 实现 Argon2 密码、服务端会话 Cookie 与 CSRF 校验，写入 `backend/src/shuttlecube/infrastructure/security/passwords.py`、`backend/src/shuttlecube/infrastructure/security/sessions.py` 和 `backend/src/shuttlecube/api/dependencies.py`
- [X] T015 实现 `SystemUser`、`UserSession` 与基础审计模型和首个迁移，写入 `backend/src/shuttlecube/domain/identity/models.py`、`backend/src/shuttlecube/domain/audit/models.py` 和 `backend/alembic/versions/0002_identity_audit.py`
- [X] T016 实现登录、当前会话和退出应用用例及 `/session` 接口，写入 `backend/src/shuttlecube/application/commands/session.py`、`backend/src/shuttlecube/api/v1/session.py` 和 `backend/tests/integration/test_session.py`
- [X] T017 [P] 实现幂等键、乐观版本和显式事务工具，写入 `backend/src/shuttlecube/application/idempotency.py`、`backend/src/shuttlecube/application/transactions.py` 和 `backend/tests/unit/application/test_idempotency.py`
- [X] T018 [P] 实现私有 S3 兼容对象存储适配器、校验值和鉴权下载基础，写入 `backend/src/shuttlecube/infrastructure/artifacts/s3.py`、`backend/src/shuttlecube/domain/finance/attachment_policy.py` 和 `backend/tests/integration/test_private_storage.py`
- [X] T019 组装 FastAPI app factory、健康检查和 `/api/v1` 路由，写入 `backend/src/shuttlecube/app.py`、`backend/src/shuttlecube/api/v1/router.py` 和 `backend/tests/integration/test_health.py`
- [X] T020 [P] 建立 React Query、路由、主题和错误边界 Provider，写入 `frontend/src/app/providers.tsx`、`frontend/src/app/router.tsx` 和 `frontend/src/app/error-boundary.tsx`
- [X] T021 [P] 建立 OpenAPI fetch 客户端、Cookie/CSRF 和 Problem Details 映射，写入 `frontend/src/api/client.ts`、`frontend/src/api/problem.ts` 和 `frontend/src/api/client.test.ts`
- [X] T022 [P] 按已确认的 shadcn 原型实现桌面端侧栏、顶栏、页面容器和响应式导航，写入 `frontend/src/layouts/app-shell.tsx`、`frontend/src/layouts/sidebar.tsx` 和 `frontend/src/layouts/topbar.tsx`
- [X] T023 [P] 创建共享 DataTable、表单字段、状态徽章、金额和日期组件，写入 `frontend/src/components/data-table/data-table.tsx`、`frontend/src/components/forms/form-field.tsx`、`frontend/src/components/status/status-badge.tsx`、`frontend/src/components/money.tsx` 和 `frontend/src/components/date-time.tsx`
- [X] T024 实现登录页面、会话守卫与退出交互，写入 `frontend/src/features/auth/login-page.tsx`、`frontend/src/features/auth/session-guard.tsx` 和 `frontend/src/features/auth/auth.test.tsx`
- [X] T025 [P] 创建真实 PostgreSQL 测试容器、事务清理和两个管理员 fixture，写入 `backend/tests/conftest.py`、`backend/tests/fixtures/users.py` 和 `e2e/fixtures/auth.ts`
- [X] T026 [P] 为当前业务 OpenAPI 编写解析、引用、operationId 和 future-path 排除测试，写入 `backend/tests/contract/test_openapi.py` 和 `scripts/check-api-client.mjs`
- [X] T027 创建 bootstrap-admin 与四片场地初始化 CLI 骨架，写入 `backend/src/shuttlecube/cli.py` 和 `backend/tests/integration/test_bootstrap.py`

**Checkpoint**: 登录、数据库、事务、审计基础、对象存储、共享布局和契约生成均可独立运行

---

## Phase 3: User Story 1 — 统一安排全部场地业务（Priority: P1）🎯 MVP

**Goal**: 统一展示固定班、私教、订场、活动和停场，并在保存前阻止场地、教练和学员冲突

**Independent Test**: 准备四片场地、教练和学员，创建多类排期并提交资源重叠安排；统一日历能展示全部占用，所有冲突均原子拒绝并指出对象与时间

### Tests for User Story 1

- [X] T028 [P] [US1] 编写场地、教练、学员和营业时间模型约束单元测试，写入 `backend/tests/unit/scheduling/test_directory_rules.py`
- [X] T029 [P] [US1] 编写资源时间范围冲突、批量占用和取消释放的 PostgreSQL 集成测试，写入 `backend/tests/integration/scheduling/test_conflicts.py`
- [X] T030 [P] [US1] 编写 `/courts`、`/coaches`、`/venue/settings`、`/students`、`/schedule` 和冲突检查契约测试，写入 `backend/tests/contract/test_schedule_contract.py`
- [X] T031 [P] [US1] 编写统一排期日历、筛选和冲突提示组件测试，写入 `frontend/src/features/schedule/schedule-page.test.tsx`

### Implementation for User Story 1

- [X] T032 [P] [US1] 实现场地、教练、场馆设置、学员与家长领域模型，写入 `backend/src/shuttlecube/domain/identity/coach.py`、`backend/src/shuttlecube/domain/scheduling/court.py`、`backend/src/shuttlecube/domain/customers/models.py` 和 `backend/alembic/versions/0003_directory.py`
- [X] T033 [P] [US1] 实现 `ScheduleEntry`、`ScheduleAllocation` 与 `CourtBlock` 模型和排期范围索引，写入 `backend/src/shuttlecube/domain/scheduling/models.py` 和 `backend/alembic/versions/0004_scheduling.py`
- [X] T034 [US1] 实现统一冲突检测、营业时间和容量校验服务，写入 `backend/src/shuttlecube/domain/scheduling/conflicts.py` 和 `backend/src/shuttlecube/domain/scheduling/policies.py`
- [X] T035 [US1] 实现排期创建、变更草案、取消和原子资源占用应用用例，写入 `backend/src/shuttlecube/application/commands/schedule.py` 和 `backend/src/shuttlecube/application/queries/schedule.py`
- [X] T036 [P] [US1] 实现场地、教练、场馆设置与学员目录 API，写入 `backend/src/shuttlecube/api/v1/courts.py`、`backend/src/shuttlecube/api/v1/coaches.py`、`backend/src/shuttlecube/api/v1/venue.py` 和 `backend/src/shuttlecube/api/v1/students.py`
- [X] T037 [US1] 实现统一排期查询、冲突预检和取消 API，写入 `backend/src/shuttlecube/api/v1/schedule.py`
- [X] T038 [P] [US1] 实现场地、教练、学员和营业时间管理页面，写入 `frontend/src/features/directory/courts-page.tsx`、`frontend/src/features/directory/coaches-page.tsx`、`frontend/src/features/customers/students-page.tsx` 和 `frontend/src/features/directory/venue-settings-page.tsx`
- [X] T039 [US1] 实现 FullCalendar 日/周视图、业务类型颜色、资源筛选和详情抽屉，写入 `frontend/src/features/schedule/schedule-page.tsx`、`frontend/src/features/schedule/schedule-calendar.tsx` 和 `frontend/src/features/schedule/schedule-details.tsx`
- [X] T040 [US1] 实现排期草案、冲突预检和结构化冲突修正交互，写入 `frontend/src/features/schedule/schedule-form.tsx` 和 `frontend/src/features/schedule/conflict-alert.tsx`
- [X] T041 [US1] 为排期创建、改期、取消和资料状态变化写入审计，写入 `backend/src/shuttlecube/application/audit/scheduling.py` 和 `backend/tests/integration/audit/test_schedule_audit.py`
- [X] T042 [US1] 编写统一排期冲突 Playwright 旅程，写入 `e2e/specs/01-unified-scheduling.spec.ts`

**Checkpoint**: US1 可独立作为首个 MVP 演示和验收

---

## Phase 4: User Story 2 — 运营固定培训班与课时（Priority: P1）

**Goal**: 管理固定班、报名、课程实例、考勤、课时流水、取消与补课

**Independent Test**: 创建 12 节班级并报名，完成正常考勤、请假、补课和机构取消；课程、余额、补课和教练费用可完整复核

### Tests for User Story 2

- [X] T043 [P] [US2] 编写班级生成、报名和中途报名规则单元测试，写入 `backend/tests/unit/classes/test_class_rules.py`
- [X] T044 [P] [US2] 编写考勤课时流水、取消返还和补课事务集成测试，写入 `backend/tests/integration/classes/test_attendance_ledger.py`
- [X] T045 [P] [US2] 编写班级、报名、考勤、取消替代和补课接口契约测试，写入 `backend/tests/contract/test_classes_contract.py`
- [X] T046 [P] [US2] 编写班级表单、报名和异常考勤组件测试，写入 `frontend/src/features/classes/classes.test.tsx`

### Implementation for User Story 2

- [X] T047 [P] [US2] 实现 `FixedClass`、`ClassSession` 和默认资源模型，写入 `backend/src/shuttlecube/domain/classes/class_models.py` 和 `backend/alembic/versions/0005_fixed_classes.py`
- [X] T048 [P] [US2] 实现 `Enrollment`、`LessonUnitLedger`、`AttendanceRecord` 和 `MakeupRecord`，写入 `backend/src/shuttlecube/domain/classes/enrollment_models.py` 和 `backend/alembic/versions/0006_enrollment_ledger.py`
- [X] T049 [US2] 实现按周规则批量生成课程实例和资源占用服务，写入 `backend/src/shuttlecube/domain/classes/session_generation.py`
- [X] T050 [US2] 实现班级创建、报名、中途报名和状态变更用例，写入 `backend/src/shuttlecube/application/commands/classes.py`
- [X] T051 [US2] 实现异常考勤、课时扣返、教练费用草稿与幂等最终确认用例，写入 `backend/src/shuttlecube/application/commands/attendance.py`
- [X] T052 [US2] 实现机构取消、原课历史保留、课时返还与替代课程用例，写入 `backend/src/shuttlecube/application/commands/class_cancellation.py`
- [X] T053 [US2] 实现补课资格、容量和时段校验及完成核销用例，写入 `backend/src/shuttlecube/application/commands/makeups.py`
- [X] T054 [P] [US2] 实现班级、报名和详情 API，写入 `backend/src/shuttlecube/api/v1/classes.py` 和 `backend/src/shuttlecube/api/v1/enrollments.py`
- [X] T055 [P] [US2] 实现考勤、取消替代和补课 API，写入 `backend/src/shuttlecube/api/v1/attendance.py` 和 `backend/src/shuttlecube/api/v1/makeups.py`
- [X] T056 [P] [US2] 实现班级列表、创建向导和班级详情页面，写入 `frontend/src/features/classes/classes-page.tsx`、`frontend/src/features/classes/class-form.tsx` 和 `frontend/src/features/classes/class-detail-page.tsx`
- [X] T057 [P] [US2] 实现报名抽屉、课时流水和余额展示，写入 `frontend/src/features/classes/enrollment-form.tsx` 和 `frontend/src/features/classes/lesson-ledger.tsx`
- [X] T058 [US2] 实现异常优先考勤、取消替代和补课安排界面，写入 `frontend/src/features/classes/attendance-panel.tsx`、`frontend/src/features/classes/cancel-replace-dialog.tsx` 和 `frontend/src/features/classes/makeup-dialog.tsx`
- [X] T059 [US2] 编写固定班、考勤与课时 Playwright 旅程，写入 `e2e/specs/02-classes-attendance.spec.ts`

**Checkpoint**: US2 能独立证明课程与权益闭环，不依赖财务付款实现

---

## Phase 5: User Story 3 — 管理私教、散客订场与临时活动（Priority: P1）

**Goal**: 统一处理单次/课包私教、场地计价预订和临时活动，并接入统一排期

**Independent Test**: 创建单次与课包私教、多场地订场和临时活动，完成改期、取消及履约；占用、价格、状态和课时均正确

### Tests for User Story 3

- [X] T060 [P] [US3] 编写私教课包、单次私教和完成扣课规则测试，写入 `backend/tests/unit/private_lessons/test_private_lesson_rules.py`
- [X] T061 [P] [US3] 编写场地计价、连续多场地预订和活动占用集成测试，写入 `backend/tests/integration/bookings/test_booking_transactions.py`
- [X] T062 [P] [US3] 编写私教、价格模板、报价、订场和活动接口契约测试，写入 `backend/tests/contract/test_operations_contract.py`
- [X] T063 [P] [US3] 编写私教、订场和活动表单组件测试，写入 `frontend/src/features/operations/operations.test.tsx`

### Implementation for User Story 3

- [X] T064 [P] [US3] 实现 `PrivateLessonPackage` 与 `PrivateLesson` 模型和迁移，写入 `backend/src/shuttlecube/domain/private_lessons/models.py` 和 `backend/alembic/versions/0007_private_lessons.py`
- [X] T065 [P] [US3] 实现 `WalkInCustomer`、`VenuePriceRule`、`VenueBooking` 与 `TemporaryEvent` 模型和迁移，写入 `backend/src/shuttlecube/domain/venue_bookings/models.py`、`backend/src/shuttlecube/domain/events/models.py` 和 `backend/alembic/versions/0008_bookings_events.py`
- [X] T066 [US3] 实现私教预约、课包校验、履约扣课、换教练和取消改期用例，写入 `backend/src/shuttlecube/application/commands/private_lessons.py`
- [X] T067 [US3] 实现场地报价、多片连续占用、价格确认和预订状态用例，写入 `backend/src/shuttlecube/application/commands/venue_bookings.py`
- [X] T068 [US3] 实现临时活动创建、参与者记录、履约与取消用例，写入 `backend/src/shuttlecube/application/commands/events.py`
- [X] T069 [P] [US3] 实现私教与课包 API，写入 `backend/src/shuttlecube/api/v1/private_lessons.py`
- [X] T070 [P] [US3] 实现价格、报价、订场和活动 API，写入 `backend/src/shuttlecube/api/v1/venue_bookings.py` 和 `backend/src/shuttlecube/api/v1/events.py`
- [X] T071 [P] [US3] 实现私教课包、预约和履约页面，写入 `frontend/src/features/private-lessons/private-lessons-page.tsx`、`frontend/src/features/private-lessons/package-form.tsx` 和 `frontend/src/features/private-lessons/lesson-form.tsx`
- [X] T072 [P] [US3] 实现订场报价、多场地选择和散客管理页面，写入 `frontend/src/features/venue-bookings/bookings-page.tsx`、`frontend/src/features/venue-bookings/booking-form.tsx` 和 `frontend/src/features/venue-bookings/quote-panel.tsx`
- [X] T073 [P] [US3] 实现临时活动列表、表单和详情页面，写入 `frontend/src/features/events/events-page.tsx`、`frontend/src/features/events/event-form.tsx` 和 `frontend/src/features/events/event-detail.tsx`
- [X] T074 [US3] 编写私教、订场和活动 Playwright 旅程，写入 `e2e/specs/03-private-bookings-events.spec.ts`

**Checkpoint**: US3 可独立验证其他经营业务与统一排期整合

---

## Phase 6: User Story 4 — 追踪经营资金与退款（Priority: P1）

**Goal**: 分离应收、收款、退款、支出和凭证事实，并提供一致可追溯汇总

**Independent Test**: 对报名分两次收款、部分退款并登记日常支出；实收、欠费、可退金额、流水、凭证和汇总完全一致

### Tests for User Story 4

- [X] T075 [P] [US4] 编写金额精度、应收状态、累计收款和可退金额规则测试，写入 `backend/tests/unit/finance/test_money_rules.py`
- [X] T076 [P] [US4] 编写并发收款、超额退款、附件权限和资金事务集成测试，写入 `backend/tests/integration/finance/test_finance_transactions.py`
- [X] T077 [P] [US4] 编写收款、退款、支出和附件接口契约测试，写入 `backend/tests/contract/test_finance_contract.py`
- [X] T078 [P] [US4] 编写财务录入、金额汇总和凭证预览组件测试，写入 `frontend/src/features/finance/finance.test.tsx`

### Implementation for User Story 4

- [X] T079 [P] [US4] 实现 `Receivable`、`Payment`、`Refund`、`Expense` 和 `Attachment` 模型与约束，保留历史审计并为既有经营业务回填唯一应收，写入 `backend/src/shuttlecube/domain/finance/models.py` 和 `backend/alembic/versions/0010_finance.py`
- [X] T080 [US4] 实现业务创建时原子生成应收、应收列表/详情、金额调整、派生状态、收款和欠费汇总查询，写入 `backend/src/shuttlecube/application/queries/receivables.py`、`backend/src/shuttlecube/application/commands/receivables.py` 和 `backend/src/shuttlecube/application/commands/payments.py`
- [X] T081 [US4] 实现退款上限、权益调整、原资金事实保留和幂等退款事务，写入 `backend/src/shuttlecube/application/commands/refunds.py`
- [X] T082 [P] [US4] 实现支出登记与凭证上传、鉴权下载用例，写入 `backend/src/shuttlecube/application/commands/expenses.py` 和 `backend/src/shuttlecube/application/commands/attachments.py`
- [X] T083 [US4] 实现应收查询/调整、收款、退款、资金作废、支出列表和凭证上传/鉴权下载/软删除 API，写入 `backend/src/shuttlecube/api/v1/finance.py` 和 `backend/src/shuttlecube/api/v1/attachments.py`
- [X] T084 [P] [US4] 实现应收详情、分次收款和退款对话框，写入 `frontend/src/features/finance/receivable-detail.tsx`、`frontend/src/features/finance/payment-dialog.tsx` 和 `frontend/src/features/finance/refund-dialog.tsx`
- [X] T085 [P] [US4] 实现支出列表、支出表单和私有凭证预览，写入 `frontend/src/features/finance/expenses-page.tsx`、`frontend/src/features/finance/expense-form.tsx` 和 `frontend/src/features/finance/attachment-viewer.tsx`
- [X] T086 [US4] 为金额、退款、支出和凭证变更写入不可覆盖审计，写入 `backend/src/shuttlecube/application/audit/finance.py`
- [ ] T087 [US4] 编写收付款、退款与凭证 Playwright 旅程，写入 `e2e/specs/04-finance-refunds.spec.ts`

**Checkpoint**: US4 可独立证明资金事实和权益事实一致且可追溯

---

## Phase 7: User Story 5 — 结算教练课时费（Priority: P2）

**Goal**: 从已完成业务生成教练费用，汇总调整并一次性完成结算与工资支出

**Independent Test**: 完成三类授课、取消另一业务，再结算某教练期间费用；仅有效费用进入一次结算并生成一次工资支出

### Tests for User Story 5

- [ ] T088 [P] [US5] 编写完成/取消业务生成教练费用与调整规则测试，写入 `backend/tests/unit/payroll/test_coach_fee_rules.py`
- [X] T089 [P] [US5] 编写并发结算、重复费用和工资支出原子事务测试，写入 `backend/tests/integration/payroll/test_payroll_settlement.py`
- [X] T090 [P] [US5] 编写教练费用查询和结算接口契约测试，写入 `backend/tests/contract/test_payroll_contract.py`

### Implementation for User Story 5

- [X] T091 [P] [US5] 实现 `CoachFee` 与 `PayrollSettlement` 模型、状态和唯一约束，写入 `backend/src/shuttlecube/domain/payroll/models.py` 和 `backend/alembic/versions/0011_payroll.py`
- [ ] T092 [US5] 实现按业务完成/取消生成、作废和冲正费用的应用服务，写入 `backend/src/shuttlecube/application/commands/coach_fees.py`
- [X] T093 [US5] 实现费用筛选汇总、调整、结算锁定和工资支出原子用例，写入 `backend/src/shuttlecube/application/commands/payroll.py` 和 `backend/src/shuttlecube/application/queries/payroll.py`
- [X] T094 [US5] 实现教练费用查询/调整、结算创建、结算历史与详情及错误结算冲正 API，写入 `backend/src/shuttlecube/api/v1/payroll.py`
- [X] T095 [P] [US5] 实现教练费用列表、期间汇总和结算确认页面，写入 `frontend/src/features/payroll/coach-fees-page.tsx`、`frontend/src/features/payroll/settlement-dialog.tsx` 和 `frontend/src/features/payroll/settlement-detail.tsx`
- [ ] T096 [US5] 编写教练费用结算 Playwright 旅程，写入 `e2e/specs/05-coach-payroll.spec.ts`

**Checkpoint**: US5 可独立验证费用来源、调整、结算和支出闭环

---

## Phase 8: User Story 6 — 处理每日运营与审计（Priority: P2）

**Goal**: 聚合今日安排与待办、经营统计，并提供关键业务审计追踪

**Independent Test**: 准备当日业务与待处理数据并执行关键变更；工作台数量、快捷入口、经营报表和审计详情均与来源事实一致

### Tests for User Story 6

- [X] T097 [P] [US6] 编写工作台待办、收付实现统计和场地利用率查询测试，写入 `backend/tests/integration/dashboard/test_dashboard_queries.py`
- [X] T098 [P] [US6] 编写关键操作前后摘要、原因和操作人审计测试，写入 `backend/tests/integration/audit/test_audit_trail.py`
- [X] T099 [P] [US6] 编写工作台、经营报表和审计查询接口契约测试，写入 `backend/tests/contract/test_dashboard_contract.py`
- [X] T100 [P] [US6] 编写工作台卡片、图表、快捷筛选和审计抽屉组件测试，写入 `frontend/src/features/dashboard/dashboard.test.tsx`

### Implementation for User Story 6

- [X] T101 [US6] 实现今日安排、待考勤、欠费、待补课、即将结束和待结算聚合查询，写入 `backend/src/shuttlecube/application/queries/dashboard.py`
- [X] T102 [US6] 实现收付实现收入、退款、支出、利润和场地利用率报表查询，写入 `backend/src/shuttlecube/application/queries/operations_report.py`
- [X] T103 [US6] 实现全局审计筛选、实体历史、请求关联查询与敏感字段保护，写入 `backend/src/shuttlecube/application/queries/audit.py` 和 `backend/src/shuttlecube/api/v1/audit.py`
- [X] T104 [US6] 实现工作台和经营报表 API，写入 `backend/src/shuttlecube/api/v1/dashboard.py` 和 `backend/src/shuttlecube/api/v1/reports.py`
- [X] T105 [P] [US6] 实现工作台摘要、待办卡片和业务快捷入口，写入 `frontend/src/features/dashboard/dashboard-page.tsx` 和 `frontend/src/features/dashboard/pending-cards.tsx`
- [X] T106 [P] [US6] 实现经营图表、日期范围和场地利用率页面，写入 `frontend/src/features/dashboard/operations-report-page.tsx` 和 `frontend/src/features/dashboard/operations-charts.tsx`
- [X] T107 [P] [US6] 实现审计时间线和业务变更详情抽屉，写入 `frontend/src/features/audit/audit-timeline.tsx` 和 `frontend/src/features/audit/audit-drawer.tsx`
- [ ] T108 [US6] 编写工作台、报表与审计 Playwright 旅程，写入 `e2e/specs/06-dashboard-audit.spec.ts`

**Checkpoint**: US6 可独立验证日常运营总览和全业务追溯

---

## Phase 9: User Story 7 — 预留 AI 助手扩展入口（Priority: P3）

**Goal**: 展示与当前 UI 一致的“规划中”AI 助手入口，同时保证没有 AI 运行时、外部请求或业务副作用

**Independent Test**: 不配置模型、Redis 或 Worker 即可启动；打开占位入口能看到未来能力说明，网络面板无 AI 请求，数据库无新增业务记录，其余六条流程不受影响

### Tests for User Story 7

- [ ] T109 [P] [US7] 编写占位入口文案、功能开关和无运行控件组件测试，写入 `frontend/src/features/ai-placeholder/ai-placeholder.test.tsx`
- [ ] T110 [P] [US7] 编写依赖与配置守卫测试，阻止 LangGraph、Celery、Redis client、AI SDK、MCP 或模型密钥进入当前构建，写入 `scripts/check-current-scope.mjs`

### Implementation for User Story 7

- [ ] T111 [P] [US7] 创建仅包含展示配置的 AI 功能占位模块，写入 `frontend/src/features/ai-placeholder/config.ts` 和 `frontend/src/features/ai-placeholder/types.ts`
- [ ] T112 [US7] 按 shadcn 视觉实现“规划中”页面，说明定时提醒、自动任务和自然语言控制均为未来方向，写入 `frontend/src/features/ai-placeholder/ai-placeholder-page.tsx`
- [ ] T113 [US7] 将占位入口接入侧栏与路由并支持隐藏配置，写入 `frontend/src/layouts/sidebar.tsx` 和 `frontend/src/app/router.tsx`
- [ ] T114 [US7] 编写 AI 占位无外部请求、无业务写入及业务导航不受影响的 Playwright 检查，写入 `e2e/specs/07-ai-placeholder.spec.ts`

**Checkpoint**: US7 只完成产品和代码占位，不存在任何 Agent 后端实现

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: 完成跨故事性能、安全、可访问性、文档和发布验证

- [ ] T115 [P] 补齐所有关键业务命令的结构化日志、敏感字段过滤和 Sentry 关联，写入 `backend/src/shuttlecube/infrastructure/observability/logging.py` 和 `frontend/src/app/monitoring.ts`
- [ ] T116 [P] 为侧栏、表格、表单、对话框、日历和图表完成键盘与屏幕阅读器检查，写入 `frontend/src/test/accessibility.test.tsx`
- [ ] T117 优化排期、联系人、流水、审计和工作台查询索引并记录执行计划基线，写入 `backend/alembic/versions/0013_performance_indexes.py` 和 `backend/tests/performance/test_query_budgets.py`
- [ ] T118 [P] 实现业务数据备份、对象存储备份和恢复验证脚本，写入 `infra/postgres/backup.ps1`、`infra/postgres/restore.ps1` 和 `infra/object-storage/backup.ps1`
- [ ] T119 [P] 添加内容安全策略、上传限制、Cookie 安全头和 Nginx 限流配置，写入 `backend/src/shuttlecube/api/security_headers.py` 和 `infra/nginx/default.conf`
- [ ] T120 运行并修复后端 Ruff、mypy、unit、integration、contract 全部门槛，结果记录到 `specs/001-badminton-operations/validation/backend.md`
- [ ] T121 运行并修复前端 lint、typecheck、Vitest、API 漂移和 scope guard，结果记录到 `specs/001-badminton-operations/validation/frontend.md`
- [ ] T122 运行七条 Playwright 场景并核对 `quickstart.md` 的性能与并发结果，记录到 `specs/001-badminton-operations/validation/e2e.md`
- [ ] T123 更新本地启动、备份恢复、故障排查和 AI 非当前范围说明，写入 `README.md` 和 `specs/001-badminton-operations/quickstart.md`
- [ ] T124 执行最终契约与范围审计，确认 future Agent 路径未生成、Agent 数据草案无迁移、当前依赖无 AI 运行时，记录到 `specs/001-badminton-operations/validation/scope-audit.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**: 无依赖，可立即开始
- **Foundational（Phase 2）**: 依赖 Setup，完成前阻塞所有故事
- **US1（Phase 3）**: 依赖 Foundational，是统一资源占用基础
- **US2（Phase 4）**: 依赖 US1 的排期占用与冲突服务
- **US3（Phase 5）**: 依赖 US1；可与 US2 在不同模块并行
- **US4（Phase 6）**: 依赖 Foundational；与 US1—US3 的订单来源做增量集成
- **US5（Phase 7）**: 依赖 US2、US3 的已完成授课事实和 US4 的支出模型
- **US6（Phase 8）**: 依赖 US1—US5 的事实数据用于完整聚合；审计框架来自 Foundational
- **US7（Phase 9）**: 仅依赖 Foundational 的路由和布局，可在任一业务故事旁并行完成
- **Polish（Phase 10）**: 依赖计划纳入发布的全部故事

### User Story Dependency Graph

```text
Setup -> Foundational -> US1 -> US2 ----┐
                         └---> US3 ----┼-> US5 -> US6 -> Polish
                  └----------> US4 ----┘
                  └----------> US7 ---------------------> Polish
```

### Within Each User Story

- 先完成测试任务并确认失败，再实现模型、服务、API 和 UI
- 数据模型和迁移先于应用用例，应用用例先于 API
- OpenAPI 契约测试与实现同步，生成客户端不得手工编辑
- 后端纵向切片完成后连接 UI，最后完成 Playwright 独立验收
- 任意时候发现需要 Agent 运行时，停止该任务并将其移入未来功能规格，不得扩大本期范围

## Parallel Opportunities

- Setup 中 T003—T006、T008—T009 可按文件边界并行
- Foundational 中错误处理、安全、对象存储、前端 Provider 和共享组件可并行
- 每个故事的 `[P]` 测试可同时编写；同故事的模型与独立页面可并行
- Foundational 后 US7 可与所有业务故事并行
- US1 完成后 US2 与 US3 可并行；US4 的财务基础也可并行，但与各业务来源的连接需在来源完成后验证

## Parallel Examples

### User Story 1

```text
T028 目录规则单元测试
T029 PostgreSQL 冲突集成测试
T030 排期契约测试
T031 日历组件测试
```

### User Story 2

```text
T047 班级与课程模型
T048 报名、课时、考勤与补课模型
T056 班级页面
T057 报名与课时组件
```

### User Story 3

```text
T064 私教模型
T065 订场与活动模型
T071 私教页面
T072 订场页面
T073 活动页面
```

### User Story 4

```text
T075 金额规则测试
T076 财务事务测试
T077 财务契约测试
T078 财务组件测试
```

### User Story 5

```text
T088 教练费用规则测试
T089 结算事务测试
T090 结算契约测试
```

### User Story 6

```text
T097 工作台聚合测试
T098 审计追踪测试
T099 报表契约测试
T100 工作台组件测试
```

### User Story 7

```text
T109 AI 占位组件测试
T110 当前范围守卫
T111 静态占位配置
```

## Implementation Strategy

### MVP First（US1 Only）

1. 完成 Phase 1 Setup
2. 完成 Phase 2 Foundational
3. 完成 Phase 3 US1
4. 停止并独立验证统一排期与冲突阻止
5. 使用已确认的 shadcn 页面风格演示 MVP

### Incremental Delivery

1. Setup + Foundational：形成可登录、可审计的基础平台
2. US1：统一排期 MVP
3. US2：固定班、考勤和课时闭环
4. US3：私教、订场和活动
5. US4：收付款、退款、支出和凭证
6. US5：教练费用与结算
7. US6：工作台、报表和审计
8. US7：可随时加入的静态 AI 占位，不阻塞业务发布
9. Polish：执行完整质量与范围审计

## Notes

- `[P]` 表示不同文件且当前无未完成依赖，可并行处理
- `[USn]` 与 `spec.md` 用户故事一一对应
- `prototypes/ui-comparison` 是已确认视觉参考，不改写其嵌套仓库历史
- 当前 OpenAPI 客户端只生成业务路径；future Agent contract 仅供未来评审
- 当前数据库迁移必须停在业务实体，禁止创建 `Agent*`、Workflow、ToolCall 或 Approval 表
- 每完成一个故事执行其独立测试和 Playwright 场景，再进入下一增量

---

## Phase 11: Incremental Enhancement — 整小时订场与统一排期快捷创建

**Goal**: 四类场地相关创建入口统一使用一小时时间粒度；周排期总览可连续选择时段后补选场地，场地预订页可在场地排期表直接多选场地和连续时段，两种入口均预填创建表单。

- [X] T125 编写整小时粒度、结束早于开始、过去时间和营业时间警告测试，写入 `backend/tests/unit/scheduling/test_schedule_time_policy.py` 和 `frontend/src/features/schedule/schedule-time.test.ts`
- [X] T126 实现后端时间硬校验、场馆营业时间警告与显式确认机制，更新 `backend/src/shuttlecube/domain/scheduling/policies.py`、排期命令及四类 API
- [X] T127 实现共享整小时时间输入、红色错误和警告确认弹窗，更新排期、私教、订场和活动表单
- [X] T128 在周排期总览实现连续一小时时段选择和四类快捷入口，并将按场地与时段多选的场地排期表放入场地预订页；两种入口均预填场地和时间
- [X] T129 更新 OpenAPI 契约并运行后端单元测试、前端 Vitest、类型检查与 lint
- [X] T130 修复 SQLite 返回排期时间时丢失 UTC 时区导致的四类创建回显偏差；快捷私教默认单次结算，切换课包扣课后强制选择关联课包
- [X] T131 统一私教和散客订场的人员名称展示：工作台、统一排期、场地排期表、排期详情及业务列表显示客户、学员和教练名称，并兼容既有排期记录

## Phase 12: Incremental Enhancement — 场馆默认价格与订场自动报价

**Goal**: 场馆设置可维护工作日白天、工作日晚间和周末的时段与每小时价格；订场逐小时累计默认价格，并在实际应收为空时自动采用建议金额。

- [X] T132 实现三类默认价格的事务保存、旧规则停用保留、审计记录和时段校验
- [X] T133 实现按场馆时区逐小时匹配价格、跨价格时段累计及未配置时段阻止创建
- [X] T134 在场馆设置增加三类默认价格编辑界面，并在订场报价后自动填充空白实际应收
- [X] T135 更新 OpenAPI 契约并执行价格、订场和场馆设置相关回归测试

## Phase 13: Incremental Enhancement — 教练月结、学员权益与私教课包闭环

**Goal**: 修复工作台固定班时区聚合故障，补齐教练资料与履约入口，强制按自然月全量结算，并在学员和私教页面形成可维护、可追溯的课包权益闭环。

- [X] T136 更新规格、数据模型和任务计划，明确自然月全量结算、权益软终止及私教课包展示规则
- [X] T137 修复 SQLite 固定班时间与 UTC 工作台聚合比较故障，并覆盖固定班实收、欠费和即将结束提醒
- [X] T138 在侧栏接入教练管理，实现教练资料编辑、停用和重新启用
- [X] T139 在固定班详情接入考勤完成入口，在私教详情接入完成、扣课和逐笔教练费用入口
- [X] T140 新增 `0012_monthly_payroll` 迁移，服务端按教练和自然月自动锁定全部待结费用并限制同月重复有效结算
- [X] T141 将教练结算页面改为教练与月份查询、自然月全量确认和月度历史查询
- [X] T142 实现学员固定班与私教课包权益聚合 API、事后新增和带财务保护的软终止命令
- [X] T143 在学员档案实现培训权益中心，支持查看多个权益、添加和终止
- [X] T144 丰富私教课包和课程 API，在私教页面展示课包余额、有效期、收费及扣课流水，并将预约改为已有课包选择
- [X] T145 更新 OpenAPI 客户端并运行后端 Ruff、mypy、pytest 与前端 lint、typecheck、Vitest、build（不运行 Playwright）
- [X] T146 将私教课包创建改为系统有效学员和教练下拉选择，在共用后端命令增加存在及启用状态校验，并事务清理引用非系统资料的错误课包、未收款应收和课时流水且保留审计记录
- [X] T147 修复经营报表场地 UUID、学员列表权益占位、应收业务内部标识和审计代码直出问题，统一返回并展示可识别的场地、人员、权益及中文审计名称
- [X] T148 拆分工作台待安排补课与已安排待完成统计，仅按未来课程计算 7/15/30 天内即将结束班级，接入对应过滤清单并修复北京时间业务日期偏移
- [X] T149 在固定班课程计划中接入已完成考勤结果，展示学员状态、扣课、补课资格与备注
- [X] T150 实现教练固定班/私教有效期费用标准、创建时费用快照、零元逐笔费用、可读来源跳转、待结调整审计和场馆时区自然月结算，并在固定班、私教及教练结算页面展示费用状态
- [X] T151 移除固定班详情直接报名入口，统一从新增学员后的培训权益流程绑定固定班，并在核心报名命令拦截不存在或已停用学员
- [X] T152 完善固定班单节改期、取消补排提醒、续期与容量、归档失效及学员固定班权益整体转移闭环
