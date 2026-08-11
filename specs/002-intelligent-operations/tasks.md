# Tasks: 智能运营系统

**Input**: Design documents from `/specs/002-intelligent-operations/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: 本功能涉及数据作用域、权限、资金／课时读取、Agent Tool、审批、幂等、恢复和复杂状态流转，按照 Spec 与 `AGENTS.md` 必须先编写并执行对应自动化测试。每个故事内的测试任务应先完成并确认会因缺少实现而失败，再开始实现任务。

**Organization**: 任务按用户故事组织。Phase 1 先同步澄清后的设计契约；Phase 2 是所有故事共享且不可跳过的安全与 Runtime 基础；Phase 3—7 分别交付可独立验收的业务切片。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可与同阶段其他 `[P]` 任务并行，且主要修改不同文件。
- **[US1]—[US5]**: 对应 Spec 的五个用户故事。
- 所有路径均相对仓库根目录。

---

## Phase 1: Setup and Contract Reconciliation

**Purpose**: 将 clarification 后新增的候选限制、per-Venue 模型开关、财务字段投影、CourtBlock 口径和案件责任队列同步到全部设计产物；本阶段完成前不得开始业务代码。

- [x] T001 Update architecture, rollout gates, capabilities, model opt-in, queue assignment, and CourtBlock decisions in `specs/002-intelligent-operations/plan.md`
- [x] T002 Update Venue flags, capability bundles, OperationCase queue fields, assignment audit, and CourtBlock metric rules in `specs/002-intelligent-operations/data-model.md`
- [x] T003 Update context/settings, claim/assign, capability-projected report, and generated-candidate-only replacement endpoints in `specs/002-intelligent-operations/contracts/openapi.yaml`
- [x] T004 Update Tool capabilities, model enablement guard, audience projection, resource-plan-only execution, and CourtBlock source semantics in `specs/002-intelligent-operations/contracts/tool-contracts.md`
- [x] T005 Update role isolation, model opt-in, assignment queue, and CourtBlock verification scenarios in `specs/002-intelligent-operations/quickstart.md`
- [x] T006 Add the OpenAI Python SDK dependency and lock it in `backend/pyproject.toml` and `uv.lock`
- [x] T007 [P] Create backend package skeletons and register operations ORM imports in `backend/src/shuttlecube/application/operations/__init__.py`, `backend/src/shuttlecube/domain/operations/__init__.py`, `backend/src/shuttlecube/infrastructure/ai/__init__.py`, and `backend/src/shuttlecube/domain/models.py`
- [x] T008 [P] Create the intelligent-operations frontend feature skeleton and test helpers in `frontend/src/features/intelligent-operations/api.ts` and `frontend/src/features/intelligent-operations/test-utils.tsx`

**Checkpoint**: Plan、data model、OpenAPI、Tool contract 和 quickstart 与最新 Spec 一致；OpenAPI 客户端生成校验通过后才进入 Phase 2。

---

## Phase 2: Foundational Scope, Policy, Runtime, and Security

**Purpose**: 建立所有用户故事共享的 Organization／Venue Scope、Membership、固定角色包、字段投影、OperationsPolicy、持久化 Runtime、Tool Registry、Trace 和可关闭模型适配层。

**⚠️ CRITICAL**: 本阶段阻塞所有用户故事。Scope 迁移、权限复核、Policy gate 和模型默认关闭测试未通过前，不得启用任何运营功能或写 Tool。

### Foundation tests

- [x] T009 [P] Add SQLite migration and backfill tests for Organization, Venue, scoped aggregates, row counts, orphan detection, and rollback in `backend/tests/integration/operations/test_scope_migration.py`
- [x] T010 [P] Add two-Organization and multi-Venue isolation tests for colliding court codes, business IDs, sessions, and direct object references in `backend/tests/integration/operations/test_scope_isolation.py`
- [x] T011 [P] Add role-bundle, capability, single-case receivable visibility, financial/payroll projection, and trace redaction tests in `backend/tests/integration/operations/test_capabilities.py`
- [x] T012 [P] Add per-Venue model-default-off, explicit-enable, disable-new-runs, and credential-does-not-enable tests in `backend/tests/integration/operations/test_model_enablement.py`
- [x] T013 [P] Add immutable OperationsPolicy schema, activation, versioning, missing-policy, and stale-policy tests in `backend/tests/unit/operations/test_policies.py` and `backend/tests/integration/operations/test_policy_activation.py`
- [x] T014 [P] Add OperationCase, Run, ToolCall, Approval, Event, ReportSnapshot, and CaseActivity persistence/state tests in `backend/tests/unit/operations/test_runtime_models.py`
- [x] T015 [P] Add runtime budget, checkpoint, lease takeover, and PostgreSQL concurrent-claim tests in `backend/tests/unit/operations/test_runtime_budgets.py` and `backend/tests/integration/operations/test_postgres_leases.py`
- [x] T016 [P] Add Tool Registry allowlist, strict-schema, forbidden-tool, capability, approval-policy, and redaction contract tests in `backend/tests/contract/test_operations_tools.py`
- [x] T017 [P] Add OpenAPI contract coverage for context, policies, runs, events, model settings, and problem responses in `backend/tests/contract/test_operations_contract.py`
- [x] T018 [P] Add frontend tests for capability-hidden navigation, model-disabled state, and deterministic-content fallback in `frontend/src/features/intelligent-operations/access-control.test.tsx`

### Foundation implementation

- [x] T019 [P] Add Organization, OrganizationMembership, and VenueMembership ORM models with optimistic versions in `backend/src/shuttlecube/domain/identity/organization_models.py`
- [x] T020 [P] Extend Venue with organization ownership, active-for-operations, and default-false model-enabled state in `backend/src/shuttlecube/domain/scheduling/court.py`
- [x] T021 Create the default Organization, membership review, and Venue ownership migration in `backend/alembic/versions/0017_organization_venue_membership.py`
- [x] T022 Add nullable Scope ownership fields to `backend/src/shuttlecube/domain/customers/models.py`, `backend/src/shuttlecube/domain/identity/coach.py`, `backend/src/shuttlecube/domain/classes/class_models.py`, `backend/src/shuttlecube/domain/classes/enrollment_models.py`, `backend/src/shuttlecube/domain/private_lessons/models.py`, `backend/src/shuttlecube/domain/venue_bookings/models.py`, `backend/src/shuttlecube/domain/events/models.py`, `backend/src/shuttlecube/domain/finance/models.py`, `backend/src/shuttlecube/domain/payroll/models.py`, `backend/src/shuttlecube/domain/scheduling/models.py`, and `backend/src/shuttlecube/domain/audit/models.py`, then create deterministic backfill and migration_issue reporting in `backend/alembic/versions/0018_scope_backfill.py`
- [x] T023 Enforce non-null Scope, scoped foreign-key validation, scoped unique constraints, and `(venue_id, code)` court uniqueness in `backend/alembic/versions/0019_scope_constraints.py`
- [x] T024 Implement immutable RequestScope resolution from authenticated active memberships in `backend/src/shuttlecube/api/dependencies.py`
- [x] T025 Implement version-controlled role bundles, capabilities, case-level receivable projection, finance/payroll projection, and safe 403/404 dependencies in `backend/src/shuttlecube/application/operations/access.py`, then enforce them on existing financial/report surfaces in `backend/src/shuttlecube/api/v1/finance.py`, `backend/src/shuttlecube/api/v1/payroll.py`, `backend/src/shuttlecube/api/v1/reports.py`, and `backend/src/shuttlecube/api/v1/dashboard.py`
- [x] T026 Implement membership review, role assignment, capability revalidation, and model-enable authorization services in `backend/src/shuttlecube/application/operations/memberships.py`
- [x] T027 Expose scoped membership review and per-Venue model enable/disable endpoints in `backend/src/shuttlecube/api/v1/operations_settings.py` and implement their capability-aware controls in `frontend/src/features/intelligent-operations/operations-settings-panel.tsx`
- [x] T028 [P] Add OperationsPolicy ORM and typed versioned config schemas in `backend/src/shuttlecube/domain/operations/policy_models.py` and `backend/src/shuttlecube/domain/operations/schemas.py`
- [x] T029 Implement draft validation, atomic activation/retirement, config hashing, and active-policy loading in `backend/src/shuttlecube/application/operations/policies.py`
- [x] T030 Add OperationsPolicy and model-setting tables and constraints in `backend/alembic/versions/0020_operations_policy_settings.py`
- [x] T031 Expose policy list, draft, and activation endpoints in `backend/src/shuttlecube/api/v1/operations.py` and implement validated policy draft/activation controls in `frontend/src/features/intelligent-operations/policy-settings-panel.tsx`
- [x] T032 Define strict Evidence, ModelOutput, checkpoint, Tool envelope, report, and error schemas in `backend/src/shuttlecube/domain/operations/schemas.py`
- [x] T033 Implement OperationCase, CaseActivity, OperationRun, OperationEvent, OperationToolCall, OperationApproval, and OperationsReportSnapshot ORM models in `backend/src/shuttlecube/domain/operations/models.py`
- [x] T034 Create scoped operations runtime tables, indexes, append-only constraints, idempotency uniqueness, and retention fields in `backend/alembic/versions/0021_operations_runtime.py`
- [x] T035 Implement deterministic Case and Run transition guards in `backend/src/shuttlecube/application/operations/state_machine.py`
- [x] T036 Implement scoped repositories, optimistic updates, append-only event sequencing, and result lookup in `backend/src/shuttlecube/application/operations/repositories.py`
- [x] T037 Implement checkpointed OperationsExecutor budgets, retry classification, stop conditions, and outcome states in `backend/src/shuttlecube/application/operations/runtime.py`
- [x] T038 Implement database lease claiming, fair per-Venue polling, startup catch-up hooks, and graceful shutdown in `backend/src/shuttlecube/application/operations/runner.py`
- [x] T039 Wire the lightweight Runner through FastAPI lifespan without holding transactions across model calls or approvals in `backend/src/shuttlecube/app.py`
- [x] T040 Implement the static Tool Registry, strict input/output validation, risk/capability/approval metadata, and disabled-write flags in `backend/src/shuttlecube/application/operations/tools.py`
- [x] T041 Implement scoped Tool idempotency result mapping and uncertain-outcome reconciliation primitives in `backend/src/shuttlecube/application/operations/idempotency.py`
- [x] T042 Implement redacted OperationEvent tracing, hash generation, model usage summaries, and business-audit linkage in `backend/src/shuttlecube/application/operations/tracing.py`
- [x] T043 Implement ModelClient, DisabledModelClient, and StubModelClient with strict structured outputs and per-Venue enablement checks in `backend/src/shuttlecube/application/operations/model_client.py`
- [x] T044 Implement the OpenAI Responses API adapter with timeouts, structured output parsing, strict read-tool projection, and redacted provider metadata in `backend/src/shuttlecube/infrastructure/ai/openai_client.py`
- [x] T045 Add model profile, timeout, retry, and secret configuration without auto-enabling Venue model use in `backend/src/shuttlecube/config.py`
- [x] T046 Register operations/settings routers and expose context, policy, run, event, and model-state APIs in `backend/src/shuttlecube/api/v1/router.py` and `backend/src/shuttlecube/api/v1/operations.py`
- [x] T047 Regenerate and verify the frontend API schema after foundational endpoints in `frontend/src/api/generated/current-openapi.yaml` and `frontend/src/api/generated/schema.d.ts`

**Checkpoint**: 两种数据库上的 Scope／Policy／Runtime 测试通过；所有现有用户仍为待复核成员；模型和写 Tool 默认关闭；跨 Scope、越权和财务旁路泄露均为零。

---

## Phase 3: User Story 1 - 主动发现并管理运营案件 (Priority: P1) 🎯 Deterministic MVP

**Goal**: 通过确定性扫描创建去重案件，提供角色队列、认领／分配、每日简报、证据、状态、SLA、业务链接和确定性关闭；模型关闭时完整可用。

**Independent Test**: 以逾期未考勤夹具运行手动扫描、15 分钟扫描和启动 catch-up；同一问题只有一个活动 Case，正确进入 capability 队列，可由合格人员认领，业务页面处理后由 Verifier 关闭，模型关闭不影响全流程。

### Tests for User Story 1

- [ ] T048 [P] [US1] Add detector evidence, fingerprint, occurrence, duplicate-scan, and missing-policy unit tests in `backend/tests/unit/operations/test_detectors.py`
- [ ] T049 [P] [US1] Add queue mapping, claim, manager assignment, invalid assignee, reassignment audit, and assignee-disable requeue tests in `backend/tests/unit/operations/test_case_assignment.py`
- [ ] T050 [P] [US1] Add manual scan, scheduled scan, startup catch-up, no-progress stop, and deterministic close integration tests in `backend/tests/integration/operations/test_scan_runtime.py`
- [ ] T051 [P] [US1] Add same-Scope queue visibility and required-capability claim/assign integration tests in `backend/tests/integration/operations/test_case_queues.py`
- [ ] T052 [P] [US1] Add cases, scans, claim, assign, dismiss, analyze, run, and event endpoint contract tests in `backend/tests/contract/test_operations_cases_contract.py`
- [ ] T053 [P] [US1] Add operations-center, queue filters, claim controls, daily brief, empty/loading/error, and model-disabled component tests in `frontend/src/features/intelligent-operations/operations-center.test.tsx`

### Implementation for User Story 1

- [x] T054 [P] [US1] Implement normalized EvidenceEnvelope, source references, hashes, and safe business links in `backend/src/shuttlecube/application/operations/evidence.py`
- [x] T055 [US1] Implement the versioned detector and case-type registries with deterministic queue_key and required_capability mappings in `backend/src/shuttlecube/application/operations/detectors.py`
- [x] T056 [US1] Implement the overdue-attendance detector as the first independently testable scan slice in `backend/src/shuttlecube/application/operations/detectors.py`
- [x] T057 [US1] Implement Case upsert, occurrence reopen, priority/SLA updates, and state-safe dismissal in `backend/src/shuttlecube/application/operations/cases.py`
- [x] T058 [US1] Implement self-claim, operations.case.assign manager assign/reassign, invalid-assignee rejection, assignment audit, and deterministic requeue in `backend/src/shuttlecube/application/operations/assignments.py`
- [x] T059 [P] [US1] Implement the verifier registry and overdue-attendance verifier in `backend/src/shuttlecube/application/operations/verifiers.py`
- [x] T060 [US1] Implement the scan workflow, detector fan-out limits, Case updates, verifier scheduling, and trace checkpoints in `backend/src/shuttlecube/application/operations/workflows.py`
- [x] T061 [US1] Implement deterministic daily brief grouping by capability, queue, severity, due date, and next action in `backend/src/shuttlecube/application/operations/briefs.py`
- [x] T062 [US1] Add daily scan, 15-minute scan, first-success brief, and startup catch-up scheduling to `backend/src/shuttlecube/application/operations/runner.py`
- [x] T063 [US1] Expose case list/detail, manual scan, analyze, dismiss, claim, assign, and run-event endpoints in `backend/src/shuttlecube/api/v1/operations.py`
- [x] T064 [P] [US1] Implement typed case, brief, run, and queue query hooks with polling and Problem handling in `frontend/src/features/intelligent-operations/api.ts`
- [x] T065 [US1] Implement the operations center with deterministic brief, queue tabs, filters, SLA, assignee, model state, and safe empty/error states in `frontend/src/features/intelligent-operations/operations-center-page.tsx`
- [x] T066 [US1] Implement case evidence, business links, state timeline, verifier result, trace summary, claim, assign, and dismiss controls in `frontend/src/features/intelligent-operations/case-detail-page.tsx`
- [x] T067 [US1] Add operations routes and replace the static “规划中” assistant card with capability-aware navigation in `frontend/src/app/router.tsx` and `frontend/src/layouts/sidebar.tsx`

**Checkpoint**: US1 可在模型完全关闭时独立演示和验收；这是后续收入、补排和对账案件的共同业务外壳。

---

## Phase 4: User Story 2 - 持续跟进欠费与续费机会 (Priority: P1)

**Goal**: 主动识别欠费、固定班续期和私教课包续费机会，以真实金额／课时／到期事实生成只读诊断和草稿，由人员记录 CaseActivity 并通过确定性业务事实关闭。

**Independent Test**: 使用三类来源应收、分次付款、退款、固定班结束、私教课包到期／余量不足、联系人缺失和多次跟进夹具；前台只能看到当前案件必要金额，CaseActivity 不写资金／权益，“已联系”不关闭，真实收清／续期或人工 dismiss 才结束。

### Tests for User Story 2

- [ ] T068 [P] [US2] Add receivable-aging, fixed-class-renewal, and private-package-renewal detector tests in `backend/tests/unit/operations/test_revenue_detectors.py`
- [ ] T069 [P] [US2] Add receivable summary, renewal facts, contact sufficiency, PII exclusion, and field-projection tests in `backend/tests/unit/operations/test_revenue_evidence.py`
- [x] T070 [P] [US2] Add CaseActivity validation, explicit confirmation, idempotency, next-check, and zero-finance/entitlement-side-effect tests in `backend/tests/integration/operations/test_followup_activities.py`
- [ ] T071 [P] [US2] Add receivable-paid, fixed-class-renewed, private-package-created, monitoring, and dismissal verifier tests in `backend/tests/integration/operations/test_revenue_retention.py`
- [ ] T072 [P] [US2] Add follow-up activity and case-analysis endpoint contract tests in `backend/tests/contract/test_operations_followup_contract.py`
- [ ] T073 [P] [US2] Add offline model evals for citation, contact abstention, communication drafts, prompt injection, and forbidden finance actions in `backend/tests/eval/operations/test_revenue_analysis.py`
- [ ] T074 [P] [US2] Add retention case, activity form, limited-money visibility, draft, monitoring, and permission component tests in `frontend/src/features/intelligent-operations/revenue-retention.test.tsx`

### Implementation for User Story 2

- [x] T075 [US2] Implement receivable, fixed-class renewal, and private-package renewal detectors in `backend/src/shuttlecube/application/operations/detectors.py`
- [x] T076 [US2] Implement scoped receivable and renewal evidence queries using existing summaries and ledger facts in `backend/src/shuttlecube/application/operations/evidence.py`
- [x] T077 [US2] Implement CaseActivity validation, persistence, next-check scheduling, and responsibility audit in `backend/src/shuttlecube/application/operations/activities.py`
- [x] T078 [US2] Register the human-confirmed `record_followup_outcome` handler with low-risk policy and idempotent results in `backend/src/shuttlecube/application/operations/tools.py`
- [x] T079 [US2] Implement receivable, fixed-class renewal, private-package renewal, monitoring, and human-dismiss verifiers in `backend/src/shuttlecube/application/operations/verifiers.py`
- [x] T080 [US2] Implement the read-only revenue analysis workflow, strict output schema, citations, abstention, and editable communication drafts in `backend/src/shuttlecube/application/operations/revenue_workflow.py`
- [x] T081 [US2] Expose follow-up context, case analysis, and activity endpoints with case-level field projection in `backend/src/shuttlecube/api/v1/operations.py`
- [x] T082 [US2] Implement retention evidence, limited amount cards, contact sufficiency, communication draft, and activity timeline UI in `frontend/src/features/intelligent-operations/revenue-retention-panel.tsx`
- [x] T083 [US2] Integrate revenue follow-up panels and next-check states into `frontend/src/features/intelligent-operations/case-detail-page.tsx`
- [x] T084 [US2] Verify Tool, Narrative, Trace, and business-link financial projections use the same audience rules in `backend/src/shuttlecube/application/operations/access.py`

**Checkpoint**: US2 独立满足收入保障跟进价值，但不注册任何收款、退款、续期、应收或课时写 Tool。

---

## Phase 5: User Story 3 - 取消课程后的整班补排闭环 (Priority: P1) 🎯 Agent Showcase MVP

**Goal**: 为待补排课程生成冻结且合法的原资源候选，只允许选择生成候选，经人员协调确认和审批后复用现有整班补排命令，确定性验证并关闭案件。

**Independent Test**: 对含冲突、CourtBlock、无候选、候选过期、课程版本变化、审批过期、并发执行和提交后崩溃的夹具完成发现→候选→确认→审批→执行→验证→关闭；未审批／stale／重复调用零副作用，有效调用只创建一节补排课。

### Tests for User Story 3

- [ ] T085 [P] [US3] Add slot enumeration, business-hours, original-resource, CourtBlock, conflict, expiry, and no-legal-candidate tests in `backend/tests/unit/operations/test_replacement_candidates.py`
- [ ] T086 [P] [US3] Add immutable resource-plan schema, evidence hash, subject version, and generated-candidate-only proposal tests in `backend/tests/contract/test_replacement_resource_plan.py`
- [ ] T087 [P] [US3] Add approval input/impact hash, capability, expiry, self-approval, rejection, and stale transition tests in `backend/tests/unit/operations/test_approvals.py`
- [x] T088 [P] [US3] Add candidate/proposal/approval/execution happy-path integration tests in `backend/tests/integration/operations/test_replacement_approval.py`
- [ ] T089 [P] [US3] Add session, policy, capability, conflict, plan-expiry, and Tool-version staleness integration tests in `backend/tests/integration/operations/test_replacement_stale.py`
- [ ] T090 [P] [US3] Add PostgreSQL concurrent approval/execution and single-side-effect tests in `backend/tests/integration/operations/test_replacement_concurrency.py`
- [ ] T091 [P] [US3] Add SQLite restart, before-commit failure, after-commit crash, and outcome-reconciliation tests in `backend/tests/integration/operations/test_runtime_recovery.py`
- [ ] T092 [P] [US3] Add replacement candidates, proposals, approvals, approve/reject, and polling API contract tests in `backend/tests/contract/test_operations_replacement_contract.py`
- [ ] T093 [P] [US3] Add candidate-only selection, coordination checkbox, impact card, stale, approval, progress, and verifier UI tests in `frontend/src/features/intelligent-operations/replacement-flow.test.tsx`

### Implementation for User Story 3

- [x] T094 [US3] Implement deterministic original-coach/original-court slot generation, business-hour checks, CourtBlock exclusion, and conflict filtering in `backend/src/shuttlecube/application/operations/candidates.py`
- [x] T095 [US3] Implement immutable versioned resource-plan creation, expiration, evidence hashing, and subject-version snapshots in `backend/src/shuttlecube/application/operations/candidates.py`
- [x] T096 [US3] Implement ToolCall proposal normalization and reject all browser/model attempts to submit arbitrary times or resources in `backend/src/shuttlecube/application/operations/tools.py`
- [x] T097 [US3] Implement immutable approval creation, impact snapshot, self-approval policy, approve/reject, expiry, and stale evaluation in `backend/src/shuttlecube/application/operations/approvals.py`
- [x] T098 [US3] Implement the replacement proposal workflow and waiting_approval checkpoint transitions in `backend/src/shuttlecube/application/operations/replacement_workflow.py`
- [x] T099 [US3] Adapt `schedule_cancelled_session_replacement` for caller-managed transactions and atomic Tool result mapping in `backend/src/shuttlecube/application/commands/class_cancellation.py`
- [x] T100 [US3] Implement the approved `schedule_cancelled_class_replacement` executor with full revalidation and actual-user audit in `backend/src/shuttlecube/application/operations/replacement_executor.py`
- [x] T101 [US3] Implement replacement outcome reconciliation using idempotency mapping, replacement relation, schedule facts, and AuditLog in `backend/src/shuttlecube/application/operations/idempotency.py`
- [x] T102 [US3] Implement the replacement relation, allocation, resource, conflict, and audit verifier in `backend/src/shuttlecube/application/operations/verifiers.py`
- [x] T103 [US3] Expose candidate, proposal, approval list, approve, and reject endpoints in `backend/src/shuttlecube/api/v1/operations.py`
- [x] T104 [P] [US3] Implement candidate cards, ranking explanations, coordination limitation, and generated-plan selection in `frontend/src/features/intelligent-operations/replacement-candidates.tsx`
- [x] T105 [P] [US3] Implement immutable impact, approval, stale, execution progress, and verifier result cards in `frontend/src/features/intelligent-operations/approval-card.tsx`
- [x] T106 [US3] Integrate the full replacement workflow into `frontend/src/features/intelligent-operations/case-detail-page.tsx`

**Checkpoint**: US1 + US3 构成 Spec 要求的首条完整 Agent 工程展示闭环；写 Tool 仍必须由 Venue rollout gate 单独开启。

---

## Phase 6: User Story 4 - 指定日／周／月经营报告 (Priority: P1)

**Goal**: 生成不可变的确定性日／周／月经营报告快照、对比和异常；CourtBlock 正确扣减不可售容量；LLM 只引用快照解释和建议，模型失败时完整降级。

**Independent Test**: 对同一固定夹具生成已结束和进行中的日／周／月报告，逐项核对金额、数量、课时、对比、异常和利用率；模型替换／关闭后确定性内容不变，未引用数值为零，非财务角色不能旁路读取受限指标。

### Tests for User Story 4

- [ ] T107 [P] [US4] Add Venue timezone, day/week/month, in-progress, comparable-elapsed-window, future-period, and DST-safe period tests in `backend/tests/unit/operations/test_report_periods.py`
- [ ] T108 [P] [US4] Add cash-basis finance, as-of balances, counts, attendance, lesson units, coach fee, and Decimal precision tests in `backend/tests/unit/operations/test_report_metrics.py`
- [ ] T109 [P] [US4] Add CourtBlock union, outside-hours, business-overlap, capacity subtraction, raw/display utilization, and data-quality tests in `backend/tests/unit/operations/test_report_court_capacity.py`
- [ ] T110 [P] [US4] Add deterministic anomaly threshold, zero-baseline, insufficient-data, severity, and reproducibility tests in `backend/tests/unit/operations/test_report_anomalies.py`
- [x] T111 [P] [US4] Add immutable snapshot, repeated-generation, source-ref, evidence-hash, and child narrative-run integration tests in `backend/tests/integration/operations/test_report_snapshots.py`
- [ ] T112 [P] [US4] Add offline narrative citation, server-side number rendering, unsupported root-cause, recommendation guard, injection, and model-failure evals in `backend/tests/eval/operations/test_report_narrative_offline.py`
- [ ] T113 [P] [US4] Add owner/finance/operations field-projection tests across Snapshot, Narrative, Trace, and business links in `backend/tests/integration/operations/test_report_access.py`
- [ ] T114 [P] [US4] Add report list/generate/detail/narrative-retry endpoint contract tests in `backend/tests/contract/test_operations_reports_contract.py`
- [ ] T115 [P] [US4] Add period picker, deterministic-first rendering, anomaly, caveat, permission, loading, and narrative-failure UI tests in `frontend/src/features/intelligent-operations/report-page.test.tsx`

### Implementation for User Story 4

- [x] T116 [US4] Refactor report source queries to require RequestScope and remove `select(Venue).limit(1)` in `backend/src/shuttlecube/application/queries/operations_report.py`
- [x] T117 [US4] Implement per-court operating capacity, CourtBlock interval union, commercial usage classification, and raw/display utilization in `backend/src/shuttlecube/application/operations/report_capacity.py`
- [x] T118 [US4] Implement versioned deterministic finance, balance, count, attendance, lesson-unit, coach-fee, and court metric builders in `backend/src/shuttlecube/application/operations/reports.py`
- [x] T119 [US4] Implement versioned deterministic anomaly rules, thresholds, evidence, and data-sufficiency results in `backend/src/shuttlecube/application/operations/report_anomalies.py`
- [x] T120 [US4] Implement immutable snapshot persistence, source refs, evidence hashing, and repeated-generation semantics in `backend/src/shuttlecube/application/operations/report_snapshots.py`
- [x] T121 [US4] Implement report Run orchestration, current-period cutoff, comparable windows, deterministic success, and optional child Narrative Run in `backend/src/shuttlecube/application/operations/report_workflow.py`
- [x] T122 [US4] Implement strict report Narrative schemas, metric/anomaly citation validation, server-side number rendering, and safe recommendation output in `backend/src/shuttlecube/application/operations/report_narrative.py`
- [x] T123 [US4] Expose report list, generate, detail, and narrative-retry endpoints with capability projection in `backend/src/shuttlecube/api/v1/operations.py`
- [x] T124 [P] [US4] Implement typed report hooks, polling, permissions, and deterministic/narrative state handling in `frontend/src/features/intelligent-operations/api.ts`
- [x] T125 [US4] Implement the day/week/month report view with metric refs, breakdowns, anomalies, CourtBlock capacity, caveats, and narrative separation in `frontend/src/features/intelligent-operations/report-page.tsx`
- [x] T126 [US4] Route `/reports` to the new Snapshot view while retaining a scoped legacy-query comparison path during migration in `frontend/src/app/router.tsx` and `frontend/src/features/dashboard/operations-report-page.tsx`

**Checkpoint**: US4 可在 ModelClient disabled 时独立作为确定性经营报告交付；启用模型只增加可失败、可重试的 Narrative。

---

## Phase 7: User Story 5 - 确定性数据一致性对账与解释 (Priority: P2)

**Goal**: 用版本化规则发现课时、资金、教练费用、工资结算和排期不变量异常，形成案件并提供只读解释与人工修复入口；MVP 不自动修复。

**Independent Test**: 分别构造流水断链、应收汇总不一致、缺少教练费、结算／工资支出不一致和排期资源异常；规则准确发现，模型只能解释，真实修复后规则重跑通过才关闭。

### Tests for User Story 5

- [ ] T127 [P] [US5] Add versioned reconciliation rule registry, invariant result, source-ref, severity, and abstention tests in `backend/tests/unit/operations/test_reconciliation_rules.py`
- [ ] T128 [P] [US5] Add Hypothesis tests for ledger chains, receivable bounds, duplicate idempotency, and allocation consistency in `backend/tests/unit/operations/test_reconciliation_properties.py`
- [ ] T129 [P] [US5] Add reconciliation detector, case deduplication, recurrence, escalation, and real-fact close integration tests in `backend/tests/integration/operations/test_reconciliation_cases.py`
- [ ] T130 [P] [US5] Add read-only reconciliation Tool contract and forbidden-repair-tool tests in `backend/tests/contract/test_operations_reconciliation_contract.py`
- [ ] T131 [P] [US5] Add offline explanation evals for invariant fidelity, impact ordering, uncertainty, injection, and no-auto-repair in `backend/tests/eval/operations/test_reconciliation_explanations.py`
- [ ] T132 [P] [US5] Add reconciliation evidence, invariant, repair-link, escalation, permission, and resolved UI tests in `frontend/src/features/intelligent-operations/reconciliation-panel.test.tsx`

### Implementation for User Story 5

- [x] T133 [US5] Implement the versioned reconciliation registry and normalized invariant result schemas in `backend/src/shuttlecube/application/operations/reconciliation.py`
- [x] T134 [P] [US5] Implement lesson ledger, attendance, private-lesson completion, and reversal consistency rules in `backend/src/shuttlecube/application/operations/reconciliation_lesson_units.py`
- [x] T135 [P] [US5] Implement receivable summary, payment/refund, and status consistency rules in `backend/src/shuttlecube/application/operations/reconciliation_finance.py`
- [x] T136 [P] [US5] Implement coach-fee, payroll-settlement, payroll-expense, and void consistency rules in `backend/src/shuttlecube/application/operations/reconciliation_payroll.py`
- [x] T137 [P] [US5] Implement ScheduleEntry, ScheduleAllocation, source state, resource, and Scope consistency rules in `backend/src/shuttlecube/application/operations/reconciliation_schedule.py`
- [x] T138 [US5] Implement reconciliation detectors, daily cadence, compatible-rule close, and three-failure escalation in `backend/src/shuttlecube/application/operations/detectors.py` and `backend/src/shuttlecube/application/operations/verifiers.py`
- [x] T139 [US5] Register the read-only reconciliation context Tool and reject all repair Tool keys in `backend/src/shuttlecube/application/operations/tools.py`
- [x] T140 [US5] Implement strict reconciliation explanation, impact ordering, uncertainty, and human repair-link workflow in `backend/src/shuttlecube/application/operations/reconciliation_workflow.py`
- [x] T141 [US5] Expose reconciliation evidence through scoped case detail and Tool result APIs in `backend/src/shuttlecube/api/v1/operations.py`
- [x] T142 [US5] Implement invariant tables, impact explanation, repair links, escalation, and verifier result UI in `frontend/src/features/intelligent-operations/reconciliation-panel.tsx`

**Checkpoint**: US5 能发现和解释确定性异常；Registry 中仍不存在 ledger、资金、费用、结算、排期或作废自动修复工具。

---

## Phase 8: Polish, Eval, Performance, and Rollout Gates

**Purpose**: 完成跨故事安全、隔离、性能、恢复、保留、客户端漂移、端到端和发布门禁。

- [ ] T143 [P] Create anonymous two-Organization, multi-Venue, 4/10/15-court, report-boundary, recovery, role, and injection fixtures in `backend/tests/fixtures/operations/scenarios.py`
- [ ] T144 [P] Add 2-second case/evidence, 3-second current report, 3-second 14-day candidates, 5-second 15-court month report, and 60-second catch-up benchmarks in `backend/tests/performance/test_operations_scale.py`
- [ ] T145 [P] Add cross-story PII, secret, prompt, Tool result, financial field, Trace, and source-ref redaction tests in `backend/tests/contract/test_operations_redaction.py`
- [ ] T146 [P] Add fixed Chinese offline scenario suites and explicitly marked live-model regression profiles in `backend/tests/eval/operations/test_scenario_suite.py` and `backend/pyproject.toml`
- [ ] T147 Add the full scan→case→claim→analysis→approval→execution→verification→report browser journey in `e2e/specs/04-intelligent-operations.spec.ts`
- [x] T148 [P] Implement retention selection, safe archive, and non-deletion of CaseActivity/AuditLog/business facts in `backend/src/shuttlecube/application/operations/retention.py`
- [ ] T149 Validate upgrade/downgrade/re-upgrade, row counts, migration issues, desktop backup/restore, and PostgreSQL rollback in `backend/tests/integration/operations/test_migration_rollbacks.py`
- [ ] T150 Validate SQLite restart and PostgreSQL transaction/concurrency parity for every write boundary in `backend/tests/integration/operations/test_database_parity.py`
- [x] T151 Regenerate the production OpenAPI client and enforce no-drift contract checks in `frontend/src/api/generated/current-openapi.yaml`, `frontend/src/api/generated/schema.d.ts`, and `scripts/check-api-client.mjs`
- [ ] T152 Add operations unit, integration, contract, offline Eval, frontend, and Playwright commands to CI documentation and scripts in `package.json` and `backend/pyproject.toml`
- [x] T153 Document model-disabled operation, Venue opt-in, capability review, Policy activation, write-tool rollout, rollback, and incident-disable procedures in `docs/intelligent-operations-runbook.md`
- [ ] T154 Execute every scenario in `specs/002-intelligent-operations/quickstart.md` and record only verified command/result corrections back into that file
- [ ] T155 Perform the final rollout-gate review and record migration, permission, policy, deterministic, AI, write, security, performance, and regression evidence in `specs/002-intelligent-operations/checklists/release-readiness.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 — Contract reconciliation**: 无依赖，必须最先完成；T001 → T002 → T003/T004 → T005，T006—T008 可在契约稳定时并行。
- **Phase 2 — Foundation**: 依赖 Phase 1；测试 T009—T018 先行，T019—T047 完成前阻塞所有用户故事。
- **Phase 3 — US1**: 依赖 Phase 2；提供所有案件型故事共享的 Case／queue／brief UI。
- **Phase 4 — US2**: 依赖 Phase 2 和 US1 的 Case／assignment slice；不依赖 US3、US4 或 US5。
- **Phase 5 — US3**: 依赖 Phase 2 和 US1 的 Case／state slice；不依赖 US2、US4 或 US5。
- **Phase 6 — US4**: 只依赖 Phase 2 的 case-less Run、Snapshot 和权限基础，可与 US1—US3 并行实现并独立交付。
- **Phase 7 — US5**: 依赖 Phase 2 和 US1 的 Case／verifier slice；不依赖 US2—US4。
- **Phase 8 — Hardening**: 依赖计划发布的全部故事；可在每个故事合入时逐步执行对应测试，但 T155 必须最后完成。

### User story dependency graph

```text
Phase 1 Contract Gate
          │
Phase 2 Scope / Policy / Runtime / Security
          ├──────────────► US4 Deterministic Reports
          │
          └──► US1 Operations Center
                    ├──► US2 Revenue Retention
                    ├──► US3 Approved Replacement
                    └──► US5 Reconciliation

Selected stories ──► Phase 8 Hardening and Rollout
```

### Within each story

1. 完成该故事所有 tests tasks，并确认它们因缺少实现而失败。
2. 完成确定性领域模型、Query、规则和 Verifier。
3. 完成 Runtime／Tool／Model 工作流；模型不是确定性逻辑的前置条件。
4. 完成 REST 契约与前端纵向切片。
5. 运行该故事独立测试与现有相关业务回归后再进入 Checkpoint。

---

## Parallel Opportunities

### Foundation

- T009—T018 的测试文件可以并行编写。
- T019/T020、T028、T032/T033 可以在迁移依赖明确后并行。
- T040—T045 分属 Tool、幂等、Trace、Model 和配置文件，可在 Runtime Schema 冻结后并行。

### User Story 1

```text
Parallel: T048 detector tests | T049 assignment tests | T052 API contract | T053 frontend tests
Then:     T054 evidence → T055 registry → T056 detector → T057 case service
Parallel: T058 assignment | T059 verifier | T064 frontend hooks
Then:     T060/T061/T062 runtime → T063 API → T065/T066/T067 UI
```

### User Story 2

```text
Parallel: T068 detector tests | T069 evidence tests | T070 activity tests | T073 Eval | T074 UI tests
Then:     T075/T076 → T077/T078/T079 → T080/T081 → T082/T083/T084
```

### User Story 3

```text
Parallel: T085 candidate tests | T086 plan contract | T087 approval tests | T090 concurrency | T093 UI tests
Then:     T094/T095 → T096/T097/T098 → T099/T100/T101/T102 → T103/T104/T105/T106
```

### User Story 4

```text
Parallel: T107 periods | T108 metrics | T109 CourtBlock | T110 anomalies | T112 Eval | T115 UI tests
Then:     T116/T117/T118/T119 → T120/T121/T122 → T123/T124/T125/T126
```

### User Story 5

```text
Parallel: T127 rules | T128 properties | T130 contract | T131 Eval | T132 UI tests
Then:     T133 → T134/T135/T136/T137 → T138/T139/T140 → T141/T142
```

---

## Implementation Strategy

### Contract-first gate

1. 完成 T001—T005，消除 clarification 与旧计划／契约的差异。
2. 重新运行 OpenAPI 解析、客户端生成和文档链接检查。
3. 只有 Design Contract Gate 通过后才执行依赖、迁移或代码任务。

### Safe deterministic pilot

1. 完成 Phase 1 和 Phase 2。
2. 完成 US1，模型与写 Tool 保持关闭。
3. 可并行完成 US4，先交付确定性案件中心和经营报告。
4. 验证 Scope、角色投影、CourtBlock、SQLite/PostgreSQL 和 4/10/15 场地门槛。

### Agent showcase MVP

1. 在 US1 基础上完成 US3。
2. 通过 PostgreSQL 并发、SQLite 重启、审批、stale、幂等和提交后崩溃测试。
3. 仅对已通过全部 Gate 的一个 Venue 开启补排写 Tool。
4. 演示“主动发现→候选→人工协调→审批→受控执行→确定性验证→关闭”。

### Incremental business rollout

1. US2 增加收入保障，但保持所有资金／权益写入为人工现有页面。
2. US4 增加可关闭模型的经营 Narrative，不改变 Snapshot 数字和异常。
3. US5 增加只读对账解释，不增加自动修复工具。
4. 每个 Venue 独立完成 Membership、Policy、模型 opt-in 和写 Tool rollout。

---

## Notes

- `[P]` 仅表示文件和前置依赖允许并行，不允许多人同时修改同一共享文件而不协调。
- 所有 Agent Query／Command 必须接收 RequestScope；浏览器和模型不能提交 organization_id／venue_id。
- 所有金额、课时、利用率、候选合法性、异常和关闭结论必须来自确定性程序。
- 新 Venue 的模型能力默认关闭；配置 provider 凭据不得改变该状态。
- 前台／运营的单笔欠费可见性不能扩散到报告、Narrative、Trace 或工资数据。
- Agent 补排只接受已生成 resource_plan；任意新时段必须退出 Agent 流程使用现有人工页面。
- CourtBlock 扣减不可售容量且不计经营使用，但仍阻止补排候选。
- Detector 只分配 queue_key／required_capability；具体人员由认领或具备能力的负责人分配。
- 不实现多 Agent、MCP、向量数据库、Celery、Redis、Temporal、Kafka、Kubernetes 或独立 AI Gateway。
- 任何测试未执行时不得报告通过；T155 只记录真实验证证据。
