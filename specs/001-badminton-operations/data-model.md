# Data Model: 羽毛球培训与场地经营管理

## Modeling Conventions

- 所有实体使用不可复用的全局唯一标识，业务编号仅用于展示和检索。
- 金额使用定点小数，币种第一版固定为人民币；任何金额不得使用浮点数计算。
- 时间点保存为带时区值，并按机构业务时区展示；排期区间采用 `[开始, 结束)` 半开语义。
- 可编辑聚合根包含 `version`，更新时必须携带已读取版本以检测并发覆盖。
- 关键业务记录包含创建人、创建时间、最后修改人和最后修改时间；取消、作废、金额或课时调整另有审计记录。
- 取消、作废和冲正优先于物理删除。课时、资金、教练费用和审计记录为追加型事实记录。
- 所有外键删除默认受限；业务失效不得形成孤立记录。

## 1. Identity and Venue

### SystemUser

内部登录身份。

**Fields**: `id`, `username`, `display_name`, `password_hash`, `status(active|disabled)`, `last_login_at`, `created_at`, `updated_at`, `version`.

**Relationships**:

- 可选关联一个 `CoachProfile`，使管理人员也能被排课。
- 作为所有创建、修改、审计、资金和结算记录的操作人。

**Validation**:

- `username` 在机构内唯一且不可为空。
- 禁用用户不能新建会话，但其历史操作必须保留。

### CoachProfile

可承担固定班、私教和活动的授课人员。

**Fields**: `id`, `linked_user_id?`, `name`, `phone?`, `employment_status(active|inactive)`, `teaching_tags[]`, `notes?`, `version`.

**Relationships**: 关联排期资源、班级默认教练、课程实际教练、私教课包、私教预约、活动、教练费用和结算明细。

**Validation**:

- 停用前若存在未来有效排期，必须先处理或明确取消这些排期。
- 手机号可空；若提供，按机构约定格式规范化。

### Venue

单一机构及其时区、营业规则。

**Fields**: `id`, `name`, `timezone`, `weekday_open_time`, `weekday_close_time`, `weekend_open_time`, `weekend_close_time`, `version`.

**Validation**: 每类营业时间的结束值必须晚于开始值；默认工作日 14:00—22:00、周末 08:00—22:00。

### Court

可被排期占用的一片场地。

**Fields**: `id`, `venue_id`, `code`, `name`, `status(active|inactive)`, `notes?`, `version`.

**Relationships**: 属于一个 `Venue`；通过 `ScheduleAllocation` 被业务占用。

**Validation**: 第一版初始化四片场地；同一机构内 `code` 唯一；停用前必须处理未来有效排期。

## 2. Customers

### Student

参加固定班、私教或活动的学员。

**Fields**: `id`, `name`, `gender?`, `birth_date?`, `age_note?`, `phone?`, `level_or_tags[]`, `status(active|inactive)`, `notes?`, `version`.

**Relationships**: 与 `Guardian` 多对多；关联报名、课时流水、考勤、私教、活动和排期资源。

**Validation**: `birth_date` 与自由填写的 `age_note` 至少可选其一但均非强制；停用前提示未来排期和有效权益。

### Guardian

学员联系人。

**Fields**: `id`, `name`, `phone`, `wechat_note?`, `notes?`, `version`.

**Relationships**: 通过 `StudentGuardian` 与一个或多个学员关联。

**Validation**: 姓名与联系电话必填；同一电话允许对应不同联系人，但保存时提示潜在重复。

### StudentGuardian

**Fields**: `student_id`, `guardian_id`, `relationship_label`, `is_primary_contact`.

**Validation**: 同一学员和家长组合唯一；同一学员最多一个主要联系人。

### WalkInCustomer

散客轻量档案。

**Fields**: `id`, `display_name`, `phone?`, `wechat_note?`, `notes?`, `version`.

**Relationships**: 关联零到多个 `VenueBooking`。

## 3. Unified Scheduling

### ScheduleEntry

所有占用资源业务的统一排期头。

**Fields**: `id`, `source_type(class_session|private_lesson|venue_booking|event|court_block)`, `source_id`, `title`, `starts_at`, `ends_at`, `status(tentative|confirmed|completed|cancelled|rescheduled)`, `original_entry_id?`, `cancellation_reason?`, `notes?`, `version`.

**Relationships**:

- 一对多拥有 `ScheduleAllocation`。
- `source_type + source_id` 指向具体业务记录；一个有效业务安排至多对应一个当前排期。
- 改期记录可通过 `original_entry_id` 指回原排期。

**Validation**:

- `ends_at > starts_at`；默认不得跨越业务日，跨日需显式确认。
- `confirmed` 和 `tentative` 中会占场的预订参与冲突；`cancelled` 不占用资源。
- 业务状态和排期状态必须由同一应用事务同步改变。

**State transitions**:

```text
tentative -> confirmed -> completed
tentative -> cancelled
confirmed -> cancelled
confirmed -> rescheduled (old) + confirmed (new)
```

完成、取消或已改期的旧记录不可重新回到待定状态。

### ScheduleAllocation

一条排期对单个资源的占用事实。

**Fields**: `id`, `schedule_entry_id`, `resource_type(court|coach|student)`, `resource_id`, `starts_at`, `ends_at`, `active`, `created_at`.

**Relationships**: 属于一个 `ScheduleEntry`；资源标识解析到场地、教练或学员。

**Validation**:

- 同一排期同一资源只能有一条有效占用。
- 对任何有效占用，同类型同资源的时间区间不得重叠。
- 时间区间必须与排期头一致；取消排期时同事务停用所有占用。

### CourtBlock

场地停用或维护业务。

**Fields**: `id`, `reason`, `starts_at`, `ends_at`, `status(confirmed|cancelled)`, `notes?`, `version`.

**Relationships**: 对一片或多片场地创建 `ScheduleAllocation`。

## 4. Fixed Classes, Enrollment and Attendance

### FixedClass

长期班级规则。

**Fields**: `id`, `name`, `class_type`, `age_or_level?`, `recurrence_rule`, `start_date`, `default_start_time`, `duration_minutes`, `session_count`, `capacity`, `default_coach_id`, `required_court_count`, `student_unit_price`, `coach_fee_per_session`, `status(draft|recruiting|active|ended|disabled)`, `notes?`, `version`.

**Relationships**: 默认教练；零到多个默认场地；拥有多个 `ClassSession` 和 `Enrollment`。

**Validation**: 课次数、容量、时长和场地数必须为正数；默认场地数不得少于所需数量；启用前必须具备完整周期、教练和场地配置。

**State transitions**:

```text
draft -> recruiting -> active -> ended
draft|recruiting|active -> disabled
```

### ClassSession

固定班在具体日期实际发生的一次课程。

**Fields**: `id`, `fixed_class_id`, `sequence_number`, `scheduled_start`, `scheduled_end`, `actual_coach_id`, `coach_fee_override?`, `status(scheduled|completed|cancelled|rescheduled)`, `replacement_for_session_id?`, `replacement_decision?(pending|scheduled|waived)`, `cancellation_reason?`, `attendance_finalized_at?`, `notes?`, `version`.

**Relationships**: 关联一个 `ScheduleEntry`、多个 `AttendanceRecord`、教练费用；补排课指回被取消课程。

**Validation**:

- 同一班级 `sequence_number` 唯一；补排课不增加合同课次总数。
- 完成前必须有实际教练；取消课程不得产生正常扣课或有效教练费用。

**State transitions**:

```text
scheduled -> completed
scheduled -> cancelled
scheduled -> rescheduled (old) + scheduled (replacement)
```

### Enrollment

学员对某固定班的一次独立报名权益。

**Fields**: `id`, `student_id`, `fixed_class_id`, `enrolled_on`, `purchased_units`, `unit_price`, `suggested_receivable`, `actual_receivable`, `is_midterm`, `price_adjustment_reason?`, `status(pending|active|completed|withdrawn|transferred|void)`, `notes?`, `version`.

**Relationships**: 关联一个 `Receivable`、多条 `LessonUnitLedger`、考勤和退款。

**Derived values**: `received_amount`, `refunded_amount`, `outstanding_amount`, `remaining_units` 均由关联有效事实汇总，不作为可直接编辑来源。

**Lifecycle additions**: 固定班归档时有效报名转为 `expired`，但剩余课时不清零；权益整体转移时原报名转为 `transferred`，以一出一入两条课时流水连接目标报名。目标报名记录 `acquisition_type=transfer` 和 `source_enrollment_id`，不创建新应收。

**Validation**: 购买课时和金额不得为负；实际应收偏离建议值时必须填写原因；同一学员可有多个班级报名，各自独立。

### LessonUnitLedger

固定班报名或私教课包的课时增减流水。

**Fields**: `id`, `owner_type(enrollment|private_package)`, `owner_id`, `change_type(purchase|attendance|leave_restore|makeup|refund|transfer|manual_add|manual_subtract|correction|reversal)`, `delta`, `balance_before`, `balance_after`, `source_type`, `source_id`, `reason?`, `status(effective|reversed)`, `reversal_of_id?`, `operated_by`, `operated_at`, `idempotency_key`.

**Validation**:

- `delta != 0`，且 `balance_after = balance_before + delta`。
- 同一权益的流水按序串行写入；前一有效余额必须等于下一条的 `balance_before`。
- 手动调整、错误修正、退款和冲正必须填写原因。
- 同一幂等键只能产生一次业务变化。

### AttendanceRecord

**Fields**: `id`, `class_session_id`, `student_id`, `enrollment_id`, `status(present|leave|absent|unprocessed; makeup_present 仅兼容历史数据)`, `deduct_units`, `grants_makeup(仅兼容历史数据)`, `lesson_ledger_id?`, `decision_note?`, `version`.

**Validation**: 同一课程和学员唯一；初始化默认为正常出勤且扣一节；请假或缺席可以逐次选择不扣课，未扣课时直接保留在原报名余额中。当前版本不生成独立补课资格。

### MakeupRecord

**Fields**: `id`, `student_id`, `origin_attendance_id`, `target_class_session_id?`, `status(pending|scheduled|completed|cancelled|void)`, `deduct_units?`, `created_by`, `completed_at?`, `notes?`, `version`.

**Compatibility note**: 该表仅为已有数据库和历史数据兼容保留；当前产品不创建、安排或核销独立学员补课记录，也不暴露相关管理入口。后续可在确认无需保留历史数据的迁移阶段再评估删除。

**State transitions**:

```text
历史数据沿用原状态，不再产生新的状态流转。
```

## 5. Private Lessons, Venue Bookings and Events

### PrivateLessonPackage

**Fields**: `id`, `student_id`, `bound_coach_id`, `purchased_units`, `unit_price`, `actual_receivable`, `valid_until?`, `status(pending|active|exhausted|expired|refunded|void)`, `notes?`, `version`.

**Relationships**: 关联应收、收款、课时流水和多个私教预约。

**Validation**: `student_id` 必须指向系统已有且启用的学员，`bound_coach_id` 必须指向系统已有且启用的教练；创建入口不得接受自由文本标识。换教练必须记录原因；有效期可空。

### PrivateLesson

**Fields**: `id`, `student_id`, `coach_id`, `package_id?`, `billing_mode(single|package)`, `starts_at`, `ends_at`, `actual_receivable`, `coach_fee`, `status(pending|booked|completed|cancelled|rescheduled|refunded)`, `adjustment_reason?`, `notes?`, `version`.

**Relationships**: 关联排期、可选课包、应收、课时流水和教练费用。

**Validation**: 课包模式必须关联有效课包；单次模式不得扣课包；完成课包私教默认扣一节。

### VenuePriceRule

**Fields**: `id`, `name`, `day_type(weekday|weekend|custom)`, `effective_from?`, `effective_to?`, `time_start`, `time_end`, `price_per_court_hour`, `priority`, `status(active|inactive)`, `version`.

**Validation**: 时间段必须有效；多个匹配规则按更具体条件及优先级选择，优先级相同且范围重叠时禁止启用。

### VenueBooking

**Fields**: `id`, `customer_id`, `starts_at`, `ends_at`, `price_rule_id?`, `suggested_receivable`, `actual_receivable`, `price_adjustment_reason?`, `payment_status(unpaid|partial|paid|refunded|partially_refunded)`, `status(pending|booked|completed|rescheduled|cancelled|refunded)`, `notes?`, `version`.

**Relationships**: 关联一片或多片场地、排期、应收、收款和退款。

**Validation**: 至少一片场地；未付款但状态为 `booked` 的记录仍占用资源；非整小时仅给出建议，实际应收由管理人员确认。

### TemporaryEvent

**Fields**: `id`, `event_type`, `name`, `starts_at`, `ends_at`, `coach_fee`, `suggested_receivable`, `actual_receivable`, `expense_amount`, `track_participants`, `requires_attendance`, `status(draft|confirmed|completed|cancelled)`, `notes?`, `version`.

**Relationships**: 可关联场地、教练、学员参与者、排期、应收、收付款和教练费用。

**Validation**: 确认前至少有时间和一片场地；只有 `track_participants` 为真时记录参与者；只有 `requires_attendance` 为真时创建考勤。

## 6. Finance, Attachments and Payroll

### Receivable

一项业务确认应收。

**Fields**: `id`, `source_type(enrollment|private_lesson|private_package|venue_booking|event|other)`, `source_id`, `suggested_amount`, `actual_amount`, `adjustment_reason?`, `status(open|settled|partially_refunded|refunded|void)`, `version`.

**Derived values**: `received_amount`, `refunded_amount`, `outstanding_amount`, `payment_status`。

**Validation**: 同一业务至多一个有效应收；实际金额偏离建议时必须填写原因；金额不得为负。累计有效收款不得超过当前实际应收。退款与相同金额的应收责任减少在同一事务完成，因此退款不会重新制造欠费；作废退款同时恢复应收责任。固定班报名或私教课包退款扣减课时时，作废退款必须将原扣减流水标记为已冲正、追加反向课时流水并恢复因退款失效的权益状态。

**Calculation**: `net_received = effective_payments - effective_refunds`；`outstanding_amount = max(actual_amount - net_received, 0)`。经营报表中的收付实现利润为有效业务收款加有效其他收入，再减有效退款和有效经营支出；退款不得作为普通支出重复扣减。

### Payment

一笔实际收款。

**Fields**: `id`, `receivable_id`, `paid_at`, `amount`, `method`, `payer_name?`, `received_by?`, `operated_by`, `notes?`, `status(effective|void)`, `void_reason?`, `idempotency_key`.

**Relationships**: 可关联多个 `Attachment`；可被一个或多个退款引用，但累计有效退款不得超过可退金额。

### Refund

一笔实际退款。

**Fields**: `id`, `receivable_id`, `payment_id?`, `refunded_at`, `suggested_amount`, `actual_amount`, `reason`, `operated_by`, `status(effective|void)`, `void_reason?`, `idempotency_key`.

**Relationships**: 关联原应收，优先关联原收款；可关联凭证；固定班退款同时关联课时冲正。

**Validation**: 实际退款必须为正且不超过可退余额；作废退款通过反向资金事实恢复汇总，不覆盖原记录。

### Expense

一笔实际支出。

**Fields**: `id`, `category`, `spent_at`, `amount`, `payee`, `payment_method`, `source_type?`, `source_id?`, `operated_by`, `notes?`, `status(effective|void)`, `void_reason?`, `idempotency_key`。日常分类可使用 `rent|utilities|equipment|supplies|other` 或简短自定义值；系统生成的工资支出使用 `coach_payroll`。

**Validation**: 金额为正；普通支出接口不得创建或单独作废工资支出；工资支出只能由教练结算自动生成，并以 `source_type=payroll_settlement` 关联唯一结算。退款类资金外流以 `Refund` 为业务主记录，普通支出接口拒绝 `refund` 分类，避免重复计入。

### OtherIncome

一笔不需要建立应收的即时其他收入，例如装备售卖、饮料和水。

**Fields**: `id`, `category`, `received_at`, `amount`, `payer`, `payment_method`, `operated_by`, `notes?`, `status(effective|void)`, `void_reason?`, `idempotency_key`.

**Validation**: 金额必须为正；分类允许使用常用选项或管理人员输入的简短自定义分类；作废必须填写原因，作废后不再计入经营收入但保留原始记录和审计。

### Attachment

**Fields**: `id`, `owner_type(payment|refund|expense|payroll_settlement)`, `owner_id`, `storage_key`, `original_filename`, `media_type`, `size_bytes`, `uploaded_by`, `uploaded_at`, `status(active|deleted)`, `deleted_by?`, `deleted_at?`.

**Validation**: 仅允许配置的图片类型和大小；`storage_key` 不可预测且唯一；下载必须验证当前用户及业务关联。

### CoachFee

一次已完成授课产生的应付明细。

**Fields**: `id`, `coach_id`, `source_type(class_session|private_lesson|event)`, `source_id`, `occurred_at`, `base_amount`, `adjustment_amount`, `adjustment_reason?`, `status(pending|settled|void)`, `settlement_id?`, `version`.

**Validation**: 同一业务和教练至多一条有效费用；只有已完成业务可生成；取消业务的费用必须为 `void`。

### PayrollSettlement

一次教练工资支付。

**Fields**: `id`, `coach_id`, `period_start`, `period_end`, `calculated_amount`, `adjustment_amount`, `actual_amount`, `adjustment_reason?`, `paid_at`, `settled_by`, `status(confirmed|void)`, `expense_id`, `version`, `idempotency_key`.

**Relationships**: 一对多包含 `CoachFee`；关联一笔工资 `Expense` 和可选凭证。

**Validation**:

- 结算明细必须属于同一教练、尚未结算且处于所选范围。
- 实际金额与计算金额不同必须填写原因。
- 费用锁定、结算记录和工资支出必须在同一事务完成。
- `period_start` 固定为自然月第一天，`period_end` 固定为该月最后一天；客户端只提交月份，服务端派生边界并自动锁定该教练当月全部 `pending` 费用。
- 同一 `coach_id + period_start` 最多存在一份 `confirmed` 结算；结算作废后允许重新结算该月。
- 作废结算必须在同一事务中作废关联工资支出，并将全部关联费用恢复为 `pending`；关联工资支出不能脱离结算单单独作废。

### 财务入口与报表口径

- “业务收款”只管理固定班、私教、场地预订和临时活动产生的应收、收款与退款；零金额业务显示为无需收款，但仍保留业务事实。
- “日常收支”只管理没有上述业务应收的即时收入和日常经营成本，不承担订单收款、退款或教练工资结算，避免一笔资金被登记两次。
- “教练结算”是教练工资支出的唯一创建与作废入口；费用明细、结算单和工资支出保持一一可追溯。
- 经营报表采用收付实现制。期间收入、退款、支出和实际结算按资金发生时间统计；期间教练费用按授课发生时间统计；“当前全部待结”是查询时点余额，不受所选期间限制，页面必须与期间发生额分区展示。

### StudentEntitlementView（聚合读模型）

不新增通用权益关联表。学员培训权益由既有 `Enrollment` 与 `PrivateLessonPackage` 聚合，返回名称、购买/剩余课时、状态、应收、实收、欠费和付款状态。

**终止规则**: 权益不物理删除；无可退实收时将报名置为 `cancelled` 或课包置为 `void`，并以一条有原因的冲正流水把剩余课时归零。仍有可退实收时拒绝终止，要求先通过财务退款流程处理。

## 7. Audit and Dashboard

### AuditLog

**Fields**: `id`, `actor_user_id`, `action_type`, `entity_type`, `entity_id`, `occurred_at`, `before_summary?`, `after_summary?`, `reason?`, `request_id`.

**Validation**: 追加后不可编辑；不得记录密码、会话密钥或完整凭证内容；同一请求可产生多条关联审计。

业务记录被取消、作废或物理清理时，关联审计仍必须保留；审计不通过业务外键级联删除。

### DashboardSnapshot (optional optimization)

工作台默认直接聚合业务表。只有性能测量不达标时才启用此可重建实体。

**Fields**: `venue_id`, `business_date`, `metric_key`, `metric_value`, `refreshed_at`.

**Validation**: 只读衍生数据，不得作为资金、课时或排期事实来源；可随时从源记录重建。

## 8. Cross-Entity Transaction Boundaries

### Create or Reschedule Schedule

1. 验证业务状态和版本。
2. 锁定涉及的场地、教练和学员资源。
3. 检查全部有效占用区间、班级容量和营业时间。
4. 一次写入排期头、全部资源占用、业务状态与审计。
5. 任一步失败则全部回滚。

### Finalize Class Attendance

1. 锁定课程、报名和相关课时权益。
2. 建立或更新每名学员考勤决策。
3. 为需扣课或恢复的学员追加课时流水。
4. 将课程标记完成并生成一次有效教练费用。
5. 写入审计后一次提交；重复幂等键返回原结果。

### Refund Enrollment

1. 锁定应收、有效收款、历史退款、报名和课时权益。
2. 校验可退金额，记录实际退款。
3. 追加课时扣减/冲正，更新报名状态及衍生欠费。
4. 写入审计；任何失败全部回滚。

### Settle Coach Payroll

1. 根据教练和自然月派生月初、月末，并锁定该月全部待结算 `CoachFee`。
2. 再次确认该月不存在其他有效结算且费用未被其他结算占用。
3. 创建结算、关联费用并创建工资支出。
4. 写入审计与可选凭证元数据后提交。

## 9. Required Indexes and Integrity Rules

- 所有有效资源占用按 `resource_type + resource_id + time_range` 支持重叠检测。
- 排期、课程、私教、预订、活动按状态和时间建立组合索引。
- 学员姓名/电话、家长电话、散客电话和业务编号支持常用检索。
- 流水按权益所有者与操作时间、资金记录按应收与发生时间、教练费用按教练/状态/发生时间索引。
- `source_type + source_id` 的有效应收、教练费用和排期关联具备业务唯一性约束。
- 幂等键在各关键命令作用域内唯一；审计 `request_id` 支持一次业务操作的完整追踪。

## Future Appendix: Agent Data Model (Not Implemented This Release)

> 本节及其后所有 AgentDefinition、Workflow、Run、Step、Event、ToolCall、Approval、Artifact、Usage 与 Budget 模型仅作为未来设计草案。当前版本不得为它们创建迁移、表、仓储、API、种子数据或运行服务；本期唯一 AI 数据是前端静态占位配置，不写入 PostgreSQL。未来正式立项时必须重新评审本附录与届时需求。

## 10. Agent Definitions, Workflows and Tools (Future Draft)

### AgentDefinition

可执行 Agent 的稳定身份与默认政策，不直接保存可变工作流内容。

**Fields**: `id`, `key`, `name`, `description`, `status(draft|active|disabled)`, `default_model_profile`, `system_policy_ref`, `created_by`, `created_at`, `updated_at`, `version`.

**Relationships**: 可关联多个 `WorkflowDefinition`；`AgentRun` 保存启动时所使用的定义与配置快照。

### ToolDefinition

Agent 可调用工具的受控注册记录。

**Fields**: `id`, `key`, `name`, `description`, `input_schema`, `output_schema`, `required_permission`, `risk_level(read_only|low|high|prohibited)`, `approval_policy`, `idempotency_scope`, `timeout_seconds`, `enabled`, `implementation_version`, `created_at`, `updated_at`.

**Validation**:

- `prohibited` 工具不可启用；任意代码、SQL、宿主机 Shell 与自动插件安装不得注册为可执行工具。
- `high` 必须配置强制审批，运行时不能被工作流或模型降低风险级别。
- 工具只能映射到应用层查询或命令，不允许映射到数据库仓储。

### WorkflowDefinition

可复用工作流的稳定身份。

**Fields**: `id`, `key`, `name`, `description`, `agent_definition_id`, `status(draft|active|archived)`, `latest_version_number`, `created_by`, `created_at`, `updated_at`, `version`.

### WorkflowVersion

工作流的不可变发布快照。

**Fields**: `id`, `workflow_definition_id`, `version_number`, `graph_schema`, `prompt_bundle`, `tool_bindings`, `input_schema`, `output_schema`, `budget_policy`, `checksum`, `status(draft|validated|published|retired)`, `created_by`, `created_at`, `validated_at?`, `published_at?`.

**Validation**: 同一工作流的版本号与校验值唯一；`published` 版本不可修改，只能创建新版本；发布前验证图可达性、输入输出、工具存在性、风险政策和预算上限。

## 11. Agent Runs, Steps and Events

### AgentRun

一次目标执行的持久化顶层记录。

**Fields**: `id`, `agent_definition_id`, `workflow_version_id?`, `initiated_by`, `goal`, `input`, `status(queued|running|waiting_approval|paused|needs_review|succeeded|failed|cancelled)`, `current_step_id?`, `checkpoint_ref?`, `model_profile`, `budget_snapshot`, `usage_summary`, `result_summary?`, `error_summary?`, `started_at?`, `finished_at?`, `created_at`, `updated_at`, `version`, `idempotency_key`.

**State transitions**:

```text
queued -> running
running -> waiting_approval -> running
running|waiting_approval -> paused -> queued|running
running -> needs_review -> paused|queued|failed|cancelled
queued|running|waiting_approval|paused|needs_review -> cancelled
running -> succeeded|failed
```

终态不可恢复；需要再次执行时创建新运行并用 `parent_run_id`（可选扩展字段）关联。恢复必须从已提交检查点继续，不得重新执行已成功且有副作用的工具调用。

### AgentStep

工作流中一次节点尝试。

**Fields**: `id`, `run_id`, `node_key`, `sequence`, `attempt`, `step_type(model|tool|approval|control|human)`, `status(pending|running|waiting|succeeded|failed|skipped|cancelled)`, `input_snapshot`, `output_summary?`, `error_summary?`, `started_at?`, `finished_at?`, `checkpoint_ref?`.

**Validation**: `run_id + sequence + attempt` 唯一；失败重试创建新的 attempt，不能覆盖历史尝试。

### AgentEvent

前端实时状态、断线回放和审计关联使用的追加事件。

**Fields**: `id`, `run_id`, `sequence`, `step_id?`, `event_type`, `visibility(operator|internal)`, `payload`, `occurred_at`, `trace_id?`.

**Validation**: `run_id + sequence` 唯一且严格递增；事件不可修改；先与状态变化在 PostgreSQL 事务中落库，提交后再发布至 Redis。SSE 使用 `sequence` 作为事件 ID，重连从最后确认序号继续。

## 12. Tool Calls, Approvals, Artifacts and Usage

### ToolCall

一次受控工具执行或执行意图。

**Fields**: `id`, `run_id`, `step_id`, `tool_definition_id`, `tool_version`, `risk_level`, `normalized_input`, `input_hash`, `impact_snapshot`, `business_versions`, `status(proposed|awaiting_approval|executing|succeeded|failed|uncertain|cancelled)`, `idempotency_key`, `result_summary?`, `error_summary?`, `external_reference?`, `started_at?`, `finished_at?`.

**Validation**:

- 工具作用域内 `idempotency_key` 唯一；重复投递返回原调用状态或结果。
- 高风险工具只有关联审批处于有效 `approved` 且业务版本未变化时才能进入 `executing`。
- 高风险调用结果为 `uncertain` 时不得自动重试，运行进入 `needs_review`。

### ApprovalRequest

对特定不可变工具影响的人工授权。

**Fields**: `id`, `run_id`, `tool_call_id`, `requested_by`, `assigned_to?`, `risk_level`, `action_summary`, `normalized_input`, `impact_snapshot`, `business_versions`, `status(pending|approved|rejected|modified|expired|stale|cancelled)`, `decision_by?`, `decision_reason?`, `modification?`, `requested_at`, `expires_at?`, `decided_at?`, `version`.

**State transitions**:

```text
pending -> approved|rejected|modified|expired|stale|cancelled
modified -> cancelled + new pending approval/tool proposal
approved -> stale (仅当执行前业务版本或权限发生变化)
```

审批决定使用条件更新防止重复处理。`approved` 不是直接执行凭证；Worker 领取后仍须重新检查审批状态、操作人权限、输入哈希、业务版本和幂等结果。

### AgentArtifact

运行产生的报告、导出、图片或大型工具输出元数据。

**Fields**: `id`, `run_id`, `step_id?`, `kind`, `name`, `media_type`, `size_bytes`, `storage_key`, `checksum`, `created_by_type(agent|user|tool)`, `created_at`, `status(active|deleted)`, `retention_until?`.

**Validation**: 内容存于私有对象存储；访问必须校验当前用户和运行权限；敏感产物遵循保留与删除策略。

### ModelUsage

一次模型调用的用量与成本事实。

**Fields**: `id`, `run_id`, `step_id`, `provider`, `model`, `request_id?`, `input_tokens`, `output_tokens`, `cached_tokens`, `estimated_cost`, `latency_ms`, `status(succeeded|failed|cancelled)`, `occurred_at`.

### AgentBudget

运行启动时冻结的资源上限。

**Fields**: `run_id`, `max_input_tokens?`, `max_output_tokens?`, `max_cost?`, `max_tool_calls?`, `max_duration_seconds?`, `max_steps?`, `on_limit(pause|fail)`, `consumed_snapshot`, `updated_at`, `version`.

**Validation**: 执行每个模型或工具步骤前原子检查并预留预算；超限后不得启动新副作用，按策略进入 `paused` 或 `failed`。

## 13. Agent Transaction and Recovery Boundaries

### Start or Resume Run

1. 以幂等键创建或读取 `AgentRun`，冻结工作流版本、工具版本、模型配置和预算。
2. 在数据库事务中写入状态、步骤/检查点与 `AgentEvent`。
3. 提交后向 Celery 投递；Worker 使用运行锁确保同一运行只有一个活动执行者。
4. 恢复时读取最近已提交检查点和工具调用状态，跳过已成功副作用。

### Propose and Execute High-Risk Tool

1. 规范化参数并计算输入哈希，读取当前权限与业务实体版本。
2. 同事务创建 `ToolCall(awaiting_approval)`、`ApprovalRequest(pending)`、检查点和事件。
3. 批准后 Worker 重新校验审批、权限、哈希、版本和幂等记录。
4. 任一业务版本变化则将审批置为 `stale`，不执行工具并产生新影响摘要。
5. 执行应用层用例；明确成功时原子记录结果与事件，不确定时置为 `uncertain` 并转人工复核。

### Persist then Publish Event

1. 状态变化和下一事件序号在同一 PostgreSQL 事务内锁定与写入。
2. 提交后发布 Redis 通知；发布失败不回滚事实。
3. 在线订阅者收到通知后读取持久化事件；重连者按最后序号回放，因此重复通知无副作用。

## 14. Agent Indexes and Integrity Rules

- `AgentRun(status, updated_at)`、`AgentRun(initiated_by, created_at)` 支持运行队列与历史查询。
- `AgentEvent(run_id, sequence)` 唯一并支持连续回放；按保留策略归档但不得破坏审计链。
- `ToolCall(tool_definition_id, idempotency_key)` 在定义的作用域唯一。
- `ApprovalRequest(status, assigned_to, requested_at)` 支持审批箱；一个工具调用最多一个当前 `pending` 审批。
- `WorkflowVersion(workflow_definition_id, version_number)` 唯一；运行引用的版本不可删除。
- `ModelUsage(run_id, occurred_at)` 支持预算、费用与延迟聚合。
- Agent 外键不得级联删除业务事实、审批、工具调用和审计记录；停用定义不影响历史运行可读性。
