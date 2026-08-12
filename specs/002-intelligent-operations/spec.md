# Feature Specification: 智能运营系统（Intelligent Operations System）

**Feature Branch**: 002-intelligent-operations

**Created**: 2026-08-09

**Status**: Draft for review

**Input**: 基于 ShuttleCube 当前真实代码、数据模型、业务流程、文档、测试和技术栈，设计能够主动发现问题、诊断规划、受控执行、人工审批、执行验证并持续跟踪到关闭的智能运营系统。本阶段只产出 Spec，不实现代码。

## 0. 结论摘要

ShuttleCube 适合建设“案件驱动的智能运营系统”，不适合先做通用聊天机器人，也不适合把排期、金额、课时、退款或工资计算交给大模型。

第一版推荐由六部分组成：

1. **商业化基础边界（P0）**：第一版仍只管理一个活动场馆，但机构、场馆、权限、运营策略、案件、运行、Tool、报告和审计必须具备显式作用域；禁止依赖“数据库中的第一家场馆”。这不是首版完整多租户功能，而是避免未来推广时重做数据隔离和 Agent 安全边界。
2. **统一运营指挥台与案件中心（P0 基础）**：确定性扫描器主动发现长期未结清应收、即将续费、逾期未考勤、机构取消后待补排和数据一致性异常，去重后形成可持续跟踪的运营案件；每日简报按人员职责汇总最重要的下一步。
3. **收入保障持续跟进（P1）**：合并欠费、固定班续期和私教课包续费机会。Agent 基于真实金额、课时、到期／结束时间、业务来源和结构化跟进历史生成优先级、诊断与沟通草稿；人员在系统外沟通，并把结果保存为运营业务记录；确定性 Verifier 按各场景关闭。
4. **取消课程后的整班补排（P1，Phase 3 首个受控写闭环）**：确定性程序按场馆策略生成合法资源方案；当前代码支持的 MVP 仍只使用原教练和原场地，候选模型保留未来确定性选择其他场地的版本扩展点；Agent 只负责排序和解释；人员确认并审批后复用现有补排命令，Verifier 检查后关闭。
5. **考勤、课时、资金与工资一致性对账（P1/P2）**：全部异常判定和复核由确定性规则完成；Agent 只解释异常、汇总影响和给出人工修复顺序，第一版不提供自动修复工具。
6. **指定日／周／月经营报告（P1）**：确定性程序按明确时间口径和场馆策略版本生成不可变报告快照、对比指标和异常结果；LLM 只引用快照生成总结、异常解释和运营建议，模型不可用时仍可查看完整指标报告。

第一版不开放登记收款、退款、考勤扣课、权益调整、课程取消、费用调整、工资结算或作废等高风险 Agent 写工具。这些操作已有明确的确定性服务和人工页面，应继续由人发起；未来只有在权限、审批、幂等、事务和评测全部成熟后再逐项评估。

为兼顾业务价值和 Agent 工程展示价值，MVP 必须至少演示一条完整闭环：

> 主动发现待补排课程 → 获取结构化证据 → 生成并排序资源可行时段 → 人工确认和审批 → 受控业务工具执行 → 确定性验证 → 案件自动关闭 → 全链路 Trace 与业务审计可查询。

## Clarifications

### Session 2026-08-09

- Q: MVP 的 Agent 补排审批是否允许人工填写系统候选之外的新时段？ → A: 不允许；Agent 流程只能选择已生成并冻结的候选，无合适候选时重新生成或退出到现有人工业务页面。
- Q: 新场馆接入后，外部模型解释、总结和建议能力如何启用？ → A: 按 Venue 明确启用且默认关闭；只有具备模型配置能力的负责人可开启，确定性功能不受影响。
- Q: 前台／运营人员应能看到多少财务信息？ → A: 使用固定角色包的最小可见范围；负责人／管理员可看全部，财务角色可看财务和工资，前台／运营只看处理当前案件所需的单笔欠费信息。
- Q: 经营报告中的 CourtBlock 应如何影响场地利用率？ → A: CourtBlock 不计入经营使用时长，并从对应场地的可营业时长中扣除；补排候选仍将其视为资源冲突。
- Q: 新案件产生后应如何确定负责人？ → A: Detector 将案件放入基于类型和 capability 的角色队列；符合权限的人员可认领，负责人可人工分配或改派，不自动轮询分配具体员工。

## 1. User Scenarios & Testing

### User Story 1 - 主动发现并管理运营案件（Priority: P1）

作为场馆管理人员，我希望系统在启动和运行期间主动扫描真实业务数据，把需要处理的事项形成去重、可追踪的运营案件，并在运营中心按严重度、金额、时间和状态展示，而不是依赖我逐页查找或向聊天机器人主动提问。

**Why this priority**: 没有主动发现、持久状态和关闭机制，后续 Agent 只能生成一次性回答，不能形成用户要求的运营闭环。

**Independent Test**: 使用包含未结清应收、固定班／私教续费机会、已过上课时间但未考勤的课程、取消后待补排课程和一致性异常的测试数据运行扫描，系统只为每个真实问题创建一个活动案件，重复扫描不重复创建，问题消失后由对应 Verifier 关闭。

**Acceptance Scenarios**:

1. **Given** 同一应收连续多次满足跟进阈值，**When** 扫描器重复运行，**Then** 保持一个活动案件并追加扫描证据，不创建重复案件。
2. **Given** 应用在扫描窗口内未运行，**When** 下次启动，**Then** 执行一次补偿扫描并创建遗漏案件。
3. **Given** 模型未配置或调用失败，**When** 扫描器发现问题，**Then** 确定性案件仍正常创建和展示，现有业务功能不受影响。
4. **Given** 问题已经由人工页面处理，**When** Verifier 再次运行，**Then** 案件自动进入 resolved，并记录关闭依据和时间。
5. **Given** Detector 创建新案件，**When** 没有具体人员负责，**Then** 案件进入由 case_type 和 required_capability 确定的角色队列，符合权限的人员可认领且 SLA 继续计算。
6. **Given** 已分配人员被禁用或失去案件所需 capability，**When** 权限变化被提交，**Then** 案件保留历史责任记录并回到原角色队列，不继续向无权限人员展示受限证据。
7. **Given** 案件已进入 resolved 或 dismissed，**When** 用户打开运营中心，**Then** 默认待处理列表不再展示该案件，但可从“已完成”历史入口只读查询业务摘要、处理结果和人工处理记录；普通用户不直接看到内部记录编号或系统运行日志。
8. **Given** 用户处理活动案件，**When** 打开“下一步处理”，**Then** 系统在当前案件页面的侧边窗口展示具体业务对象、问题原因、完成标准和对应操作，不要求用户先跳转到完整业务页面；业务操作完成后立即运行确定性 Verifier 并刷新案件状态。

---

### User Story 2 - 持续跟进欠费与续费机会（Priority: P1）

作为场馆管理人员，我希望系统主动识别达到跟进账龄的未结清应收、即将结束的固定班和即将到期或余量不足的私教课包，基于真实金额、剩余课时、结束时间、联系人和历史跟进结果给出优先级、原因解释与可编辑沟通草稿，并持续跟踪到收清、完成续期、明确暂不续费或人工升级。

**Why this priority**: 当前真实数据已经存在应收汇总、固定班结束时间、报名、续期命令、私教课包有效期和课时流水；收入保障比单独欠费更符合不同规模球馆的持续运营价值，同时仍无需让 Agent 修改资金、权益或报名事实。

**Independent Test**: 创建不同来源和账龄的未结清应收、即将结束固定班和即将到期／余量不足的私教课包，验证各 detector、排序依据、引用、结构化人工跟进记录和确定性关闭；整个 Agent 过程不得新增或修改 Payment、Refund、Receivable、Enrollment、PrivateLessonPackage 或 LessonUnitLedger。

**Acceptance Scenarios**:

1. **Given** 一笔应收余额大于零且达到配置的账龄阈值，**When** 扫描器运行，**Then** 创建或更新欠费跟进案件，并引用应收、业务来源、实际应收、净实收、退款和未结清金额。
2. **Given** 业务没有可用联系人或外部沟通渠道，**When** Agent 生成计划，**Then** 明确标记“联系人数据不足”，不得编造电话、微信或联系结果。
3. **Given** 固定班即将结束或私教课包达到场馆配置的到期／余量阈值，**When** 扫描器运行，**Then** 创建或更新续费机会案件，并引用结束时间、剩余课时、当前应收状态和联系人充分性，不根据备注猜测续费意愿。
4. **Given** 管理人员在微信或电话完成沟通，**When** 在案件中记录渠道、结构化结果、摘要和下次跟进时间，**Then** 新增 CaseActivity 业务记录和对应 Trace，不修改资金、权益、报名或课包主记录。
5. **Given** 关联应收的未结清金额变为零或应收被合法作废，**When** Verifier 运行，**Then** 欠费案件自动关闭并引用最终资金汇总。
6. **Given** 人员通过现有页面为固定班新增后续课程／续期课时，或创建新的私教课包，**When** Verifier 运行，**Then** 续费案件按新增课程、续期流水／审计或新课包等真实业务事实关闭；“已联系”本身不得被当作续费成功。
7. **Given** 联系对象明确暂不续费或需要更晚再联系，**When** 人员记录结果，**Then** 案件按结构化结果进入 dismissed 或 monitoring，并保留下次检查时间和操作人。
8. **Given** Agent 提议直接登记收款、退款、创建续期应收或调整课时，**When** Guardrail 校验计划，**Then** 拒绝该动作并引导人员进入现有业务页面。

---

### User Story 3 - 协调并执行取消课程整班补排（Priority: P1）

作为场馆管理人员，我希望系统在固定班课程因机构原因取消且选择“稍后补排”后，按当前场馆策略主动生成资源可行候选方案，解释排序依据，并在我确认已完成学员协调和审批后执行补排。当前 MVP 策略只允许原教练和原场地，但候选必须以版本化 resource_plan 表达，不能把这一限制固化为长期 Agent 架构。

**Why this priority**: 当前代码已经有取消、待补排、立即或稍后补排、版本检查、冲突检查、审计和补排关联，是最适合复用现有能力构建首个受控 Agent 写闭环的场景。

**Independent Test**: 取消一节固定班课程并选择 pending，制造部分候选时段冲突，验证候选生成、Agent 排序、人工审批、版本过期拒绝、一次性执行和最终 Verifier。

**Acceptance Scenarios**:

1. **Given** 一节课程处于 cancelled 且 replacement_decision 为 pending，**When** 扫描器运行，**Then** 创建待补排案件并读取原课程、班级、教练、场地、营业时间和当前版本。
2. **Given** 候选窗口内存在资源冲突或超出营业时间，**When** 生成候选时段，**Then** 确定性程序排除不合法时段，Agent 不能恢复被排除候选。
3. **Given** 固定班排期没有学员资源占用和学员可用时间数据，**When** 展示候选，**Then** 每个候选明确标记“仅验证场地和教练，尚未验证学员可用性”。
4. **Given** 管理人员未确认已完成人员协调或未审批，**When** Agent 请求执行，**Then** 工具保持 awaiting_approval，不产生排期写入。
5. **Given** 审批后课程版本、权限、工具参数或影响摘要发生变化，**When** 执行器领取工具调用，**Then** 审批置为 stale，重新生成方案，不执行旧参数。
6. **Given** 审批有效且数据未变化，**When** 受控工具执行，**Then** 复用现有整班补排命令创建一次补排课程和排期，并保留业务审计。
7. **Given** 进程在业务提交后、运行状态记录前中断，**When** 恢复，**Then** 通过幂等键和业务事实查询识别已成功结果，不创建第二节补排课。

---

### User Story 4 - 生成指定日／周／月经营报告（Priority: P1）

作为场馆管理人员，我希望选择一个业务日、自然周或自然月，生成基于真实经营数据的报告，查看收入、退款、支出、利润、欠费、业务数量、考勤、课时、教练费用和场地利用率，并获得有数据依据的总结、异常提示与运营建议。

**Why this priority**: 当前代码已经有收付实现制经营报表、分业务／班级收入、教练费用和场地利用率查询，可低风险扩展为确定性报告快照；该场景能够直观展示“程序计算事实、LLM 解释事实”的职责边界。

**Independent Test**: 对同一组固定业务夹具分别生成日、周、月报告，验证时间边界、所有指标、对比期、异常规则和引用；替换或关闭模型后，确定性指标和异常结果保持一致，LLM 不得产生快照中不存在的数值。

**Acceptance Scenarios**:

1. **Given** 管理人员选择一个过去的业务日、自然周或自然月，**When** 生成报告，**Then** 系统按 Venue.timezone 计算完整期间边界并生成确定性指标快照。
2. **Given** 选择当前正在进行的日、周或月，**When** 生成报告，**Then** 报告明确标记“进行中”，只统计 generated_at 之前的事实，并使用相同已过时长的对比窗口。
3. **Given** 报告包含期间收入、当前欠费和当前全部待结教练费用，**When** 展示指标，**Then** 分别标记“期间发生额”和“截至生成时点余额”，不得混为同一时间口径。
4. **Given** 确定性异常规则发现收入下降、退款比例升高、利润为负、取消率升高、待考勤、低利用率或待结费用等问题，**When** LLM 生成说明，**Then** 只能解释规则结果并引用指标，不能自行新增异常或计算阈值。
5. **Given** 对比期没有足够数据或基准值为零，**When** 生成报告，**Then** 确定性程序返回“数据不足”或绝对变化，LLM 不得虚构百分比。
6. **Given** LLM 摘要中需要显示金额、数量、课时或利用率，**When** 渲染报告，**Then** 数值从报告快照的 metric_ref 插入或经过一致性校验，不能采用模型自由生成的数字。
7. **Given** 模型未配置、超时或输出校验失败，**When** 生成报告，**Then** 指标、分项、对比和异常提示仍正常展示，智能总结标记为暂不可用。
8. **Given** Agent 给出运营建议，**When** 用户查看报告，**Then** 建议与事实和异常分区展示，不自动修改价格、排期、资金、课时或其他业务数据。
9. **Given** 原始场地占用超过配置营业时间或原始利用率超过 100%，**When** 生成报告，**Then** 保存原始占用、可营业时长、原始利用率和数据质量异常；展示层可以另外提供截断值，但不得覆盖原始事实。
10. **Given** 营业时间内存在已确认的 CourtBlock，**When** 生成利用率或补排候选，**Then** 其重叠时长从对应场地的可营业时长扣除且不计入经营使用，候选时段仍因资源不可用被排除。

---

### User Story 5 - 确定性数据一致性对账与解释（Priority: P2）

作为场馆管理人员，我希望系统定期检查考勤、课时、收付款、退款、教练费用和工资结算之间的关键不变量，把异常形成案件并给出可理解的影响说明和人工修复入口。

**Why this priority**: 一致性检查对资金和课时安全价值高，但异常判断与修复必须依赖确定性规则；Agent 的价值主要在跨记录解释、排序和降低排查成本，不在自主修账。

**Independent Test**: 通过测试夹具构造流水链断裂、应收状态不一致、已完成业务缺少教练费、结算与工资支出不一致和排期资源不同步等异常，验证规则准确发现；Agent 只能解释，不能调用任何修复写工具。

**Acceptance Scenarios**:

1. **Given** 所有业务事实满足不变量，**When** 执行对账，**Then** 不创建异常案件。
2. **Given** 某权益流水的 balance_after 不等于 balance_before 加 delta，**When** 对账，**Then** 创建高严重度案件并引用具体流水，但不自动改余额。
3. **Given** 结算单、教练费用和工资支出不一致，**When** Agent 诊断，**Then** 所有金额来自规则输出，Agent 不自行计算差额。
4. **Given** 人员通过现有业务页面或受支持的修复流程完成处理，**When** 同一规则重跑并通过，**Then** 案件自动关闭。
5. **Given** 历史 MakeupRecord 仍存在，**When** 对账运行，**Then** 仅按兼容数据处理，不把它解释为当前可用的个人补课能力。

### Edge Cases

- 活动案件已 resolved 后，同一业务因退款作废、重新欠费或新的取消事件再次异常时，应重新打开原案件或创建带新 occurrence 的案件，并保留前次关闭历史。
- 业务记录在 Agent 读取后被人工修改时，所有写工具必须以实体 version 和输入哈希判定 stale。
- 同一时刻人工页面与 Agent 尝试补排时，只允许一个事务成功；另一个得到明确并发或状态冲突。
- SQLite 桌面版单进程重启、断网或睡眠恢复后，过期 lease 可被安全接管；不得依赖进程内存作为唯一状态。
- PostgreSQL 服务端部署即使未来启动多个 API 进程，也只能有一个执行者领取同一运行；数据库条件更新是最终锁。
- 模型返回非结构化文本、未知工具、越界日期、被禁止动作或不存在 ID 时，计划校验失败并停止，不进入工具执行。
- 业务备注、学员姓名或其他工具输出包含提示注入文本时，只作为数据展示，不能改变系统政策、工具风险等级或审批要求。
- 模型服务不可用、超时、限流或预算耗尽时，案件和确定性扫描继续可用；运行进入 retry_scheduled 或 escalated。
- Verifier 连续看到相同未解决证据、超过截止时间或达到重试上限时，停止自动 Loop 并转人工升级，不得无限循环。
- 根目录 legacy shuttlecube.db 与 backend 当前数据库同时存在时，系统只通过当前 Settings 配置的数据库会话读取业务事实，不扫描任意数据库文件。
- 当前日／周／月尚未结束时，报告必须显示部分期间并使用等长对比窗口，不把完整对比期误写为同比下降或增长。
- 对比期为零、没有营业时间、没有有效场地或没有任何业务记录时，报告必须显示确定性空状态，不允许除零、NaN 或模型补造趋势。
- 同一历史期间在业务数据被合法补录或作废后重新生成时，应创建新快照并说明 generated_at 和 metric_version，不覆盖旧报告。
- 任意请求、扫描、Tool、报告或 Trace 缺少有效 organization_id／venue_id，或引用的业务记录不属于当前作用域时，必须安全失败，不能退回到“第一家场馆”。
- 场馆运营策略在案件处理期间发生修改时，旧案件、报告和审批保留原 policy_version；需要使用新策略时创建新 occurrence、Snapshot 或 ToolCall，不静默改变旧结论。
- 同一机构存在多个场馆但首版只启用一个活动场馆时，查询仍必须显式限定当前场馆；不得因为 UI 没有场馆切换器而省略数据作用域。

## 2. 当前项目真实现状

### 2.1 架构与部署

- 后端是 Python 3.14、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic 的模块化单体。
- 前端是 React 19、TypeScript、Vite、TanStack Query、React Router、shadcn/ui 与 Tailwind CSS。
- 服务端部署使用 PostgreSQL 17 和私有 S3 兼容对象存储；Windows 桌面版使用 SQLite 和本地私有附件目录。
- 后端应用层已经按 commands、queries、domain、audit 和 transaction 等边界组织，适合由 Tool 复用，但部分命令内部直接 commit，Agent 写工具实施前需要统一调用方事务边界。
- 测试以 pytest、FastAPI TestClient、内存 SQLite 集成为主，保留 PostgreSQL Testcontainers fixture；前端使用 Vitest，端到端使用 Playwright。

### 2.2 已落地业务能力

真实代码和迁移已经实现：

- 统一 ScheduleEntry 和 ScheduleAllocation，覆盖场地、教练、学员资源冲突；
- 场馆营业时间、整点排期、过去时间或超营业时间确认；
- 固定班、课程实例、报名、考勤、课时流水、课程取消、改期和整班补排；
- 固定班续期、归档、剩余权益整体转移；
- 学员、家长、散客、教练、教练费率、场地与价格规则；
- 私教课包、私教预约、课包扣课和教练费用；
- 散客订场、临时活动和统一排期；
- 应收、分次收款、退款、其他收入、支出和私有凭证；
- 教练费用、按教练自然月全量结算、工资支出和结算作废；
- 经营工作台、收付实现制经营报表、场地利用率和业务审计；
- reports/operations 已支持任意起止日期的收入、退款、支出、利润、当前欠费、教练费用、分业务／班级收入和场地使用／利用率查询；
- SQLite 桌面数据迁移、备份和恢复。

### 2.3 关键确定性口径

- 欠费由 Receivable 的实际应收减去有效收款再加回有效退款后的净结果派生，不以 VenueBooking.payment_status 等展示字段作为最终事实。
- 经营收入采用收付实现制：有效业务收款加其他收入；退款单独扣减；普通支出排除退款；工资支出只能由结算产生。
- 当前 operations_report 同时包含期间发生指标和查询时点余额：income、refunds、expense、profit、coach_earned、coach_settled 和场地利用属于所选期间；outstanding 与 current_coach_pending 属于生成时点；coach_pending 表示所选期间发生且生成时仍未结的费用。智能报告必须保留并显式展示这些不同口径。
- 当前 operations_report 把全部 active ScheduleAllocation 都累计为场地使用时长，因此 CourtBlock 也会抬高利用率；智能报告必须修正为“经营使用”和“不可售容量”分离，不能沿用该行为。
- 课时余额由 LessonUnitLedger 的有效流水派生，不能直接覆盖。
- 固定班、私教和活动完成后才生成 CoachFee；自然月结算自动选择该教练当月全部 pending 费用。
- 排期合法性、冲突、金额范围、课时余额、状态转换和并发版本由后端确定性规则最终裁决。

### 2.4 当前 AI 与权限现状

- 当前没有模型 SDK、模型配置、Agent API、Tool Registry、运行表、审批表、Worker、后台队列或 Agent Eval。
- 前端只有侧边栏“智能运营助手／规划中”的静态说明卡，没有可点击工作区。
- 旧 specs/001 文档中的 AgentDefinition、Workflow、AgentRun、SSE、Redis 和 Celery 均是明确标记为未实现的未来草案，不能当作当前能力，也不应直接照搬。
- 当前权限模型只有 SystemUser 登录状态、HttpOnly 会话和 CSRF；没有 role、permission 或 capability 字段。现有登录用户在业务上等价于内部管理人员。
- 业务 AuditLog、request_id 和若干幂等键已经存在，但审计覆盖并非所有命令完全一致；支付、退款、支出、其他收入、结算、部分班级生命周期有较完整审计，部分订场、私教和活动命令仍需在开放 Agent 写工具前补齐。

### 2.5 商业化与场馆作用域缺口

- 当前计划和代码按单机构、单活动场馆运行；Venue 已存在，Court 具有 venue_id，但课程、排期头、价格规则、订场、活动、应收、收支、教练费用、AuditLog 和 SystemUser 等多数聚合根没有一致的 organization／venue 作用域。
- operations_report、订场、教练费率等真实查询仍通过 `select(Venue).limit(1)` 获取营业时间或时区；这一实现只适用于当前单场馆，不能成为智能运营 Tool 的长期数据边界。
- Court.code 当前全局唯一，VenueBooking 和 TemporaryEvent 还保留 court_ids_csv；统一排期的 ScheduleAllocation 才是资源占用事实。未来多场馆查询和 Agent 证据不得依赖 CSV 或全局场地编号判断归属。
- 当前 SystemUser 没有机构成员关系、角色或 capability。其他球馆通常至少区分负责人、前台／运营和财务视角，开放 Agent Tool 前必须建立服务端作用域和最小权限。
- 第一版不提供跨场馆切换、集团汇总或 SaaS 租户管理，但必须先建立 Organization → Venue 的所有权边界、请求 Scope 和隔离测试；否则后续推广会同时重构业务查询、报表、权限、Agent 上下文和审计。
- 10–15 片场地仍属于当前模块化单体和数据库可承受的低并发规模；推广准备不构成引入消息队列、分布式工作流、多 Agent 或独立 AI Gateway 的理由。

### 2.6 当前数据快照及其含义

2026-08-09 对仓库中的 backend/shuttlecube.db 只读检查显示，该数据库位于迁移 0016：

- 3 个有效固定班、36 节课程，其中 31 scheduled、2 completed、3 cancelled；
- 3 个有效报名、13 条课时流水、6 条考勤；
- 10 笔应收，其中 3 笔未结清，当前未结清合计 2940 元；
- 3 笔有效收款、0 笔退款、1 笔其他收入；
- 2 笔 pending 教练费用、0 个工资结算；
- 1 个有效私教课包、1 个已预约私教、2 个订场、3 个临时活动；
- 42 条业务审计；
- 仍有 1 条历史 pending MakeupRecord，但当前考勤命令明确 grants_makeup=False，产品也没有个人补课入口。

该数据只能证明当前开发／演示数据库真实包含待收款和待结费用，不能代表生产规模或经营基线。根目录 shuttlecube.db 是较早的 legacy 数据文件，桌面启动代码会把 legacy 数据迁入用户数据目录；智能运营系统不得自行选择或扫描这些文件。

## 3. Agent 适用性与确定性边界

| 业务 | Agent 适用性 | 必须由确定性程序负责 | 第一版决定 |
|---|---|---|---|
| 运营异常发现 | 中 | 扫描条件、阈值、去重、严重度基线、案件创建和关闭判定 | 用确定性扫描器主动发现；Agent 只做摘要、跨案件排序和解释 |
| 欠费持续跟进 | 高 | 金额、账龄、业务来源、余额、付款状态、关闭条件 | P1；与续费共用收入保障工作台，Agent 生成计划和文案，人员外部沟通，禁止资金写入 |
| 固定班／私教续费机会 | 高 | 班级结束、课包到期、剩余课时、联系人、应收和续期成功判定 | P1 只读跟进；Agent 生成方案和草稿，不自动续期或创建应收 |
| 取消课程整班补排 | 高 | 场馆策略、营业时间、候选枚举、资源冲突、版本、排期写入和验证 | P1 的 Phase 3；首个完整受控写闭环，MVP Policy 仅允许原教练和原场地 |
| 日／周／月经营报告 | 高 | 期间边界、指标、对比、异常规则、数值格式和引用 | P1；确定性快照始终可用，LLM 只负责总结、解释和建议 |
| 个人补课 | 低／不适用 | 当前业务明确不创建个人补课资格 | 删除该候选；MakeupRecord 只作历史兼容 |
| 逾期未考勤 | 中 | 课程时间、状态和是否已 finalized | P1 发现与提醒；第一版不由 Agent 提交考勤或扣课 |
| 课时对账 | 低 | 流水算术、链式余额、状态、幂等唯一性 | 确定性检查；Agent 只解释，不自动修复 |
| 收付款退款对账 | 低 | 金额汇总、边界、状态和退款责任 | 确定性检查；Agent 只解释，不执行资金操作 |
| 教练费用／工资对账 | 低 | 来源完成状态、自然月范围、结算全量性、工资支出 | 确定性检查；Agent 只解释，不执行结算 |
| 场地利用和经营趋势 | 高 | 指标计算、时间范围、样本量、原始利用率和数据质量 | 报告 P1；更复杂的低利用时段和排期优化 P2，Agent 不得虚构原因或直接调价 |
| 外部消息发送 | 暂不适用 | 联系人授权、渠道状态、发送幂等、退订和送达 | 当前没有微信、短信或邮件集成，MVP 只生成草稿 |

### 3.1 LLM 可以做什么

- 在确定性证据范围内总结问题和影响；
- 跨多个案件做可解释优先级排序；
- 生成受严格 Schema 约束的处理计划；
- 对确定性候选时段排序并解释偏好；
- 生成可编辑的内部跟进清单和沟通草稿；
- 在数据不足时明确 abstain，指出缺失字段或需要人工确认；
- 把确定性对账结果翻译为管理人员可理解的说明。

### 3.2 LLM 不得做什么

- 计算或改写金额、欠费、退款、利润、课时、工资、利用率或候选合法性；
- 自行发现数据库记录、执行 SQL、访问 ORM Session、Shell、文件系统或任意 URL；
- 自己设定权限、风险等级、审批要求、重试策略或案件关闭状态；
- 把自然语言中的“确认”“都处理了”当作批准高风险动作；
- 在没有 Tool 证据时声称某人已联系、已付款、可出席、已同意补排或数据已修复；
- 调用未注册工具、动态安装插件、生成代码执行或绕过业务 Service；
- 把工具输出中的业务备注当作系统指令。

## 4. 产品定位、范围与交互形态

智能运营系统是现有管理后台内的“运营案件与受控执行中心”，不是独立聊天产品。主要入口应是案件列表、每日简报、案件详情、方案卡片、审批卡片、执行进度和验证结果；自然语言输入是可选补充，不是主导航。

产品按三个主要工作视角组织，而不是为每个视角建立独立 Agent：

- **前台／运营**：今日排期、逾期考勤、待补排、客户跟进和等待人工事项；处理欠费跟进案件时只显示该案件必要的单笔应收、实收、退款和未结清金额，不显示全馆利润、工资或结算；
- **培训管理**：固定班结束、私教课包余量、续费机会、非薪资教练工作量和培训数据一致性；
- **财务**：全馆收入、退款、支出、欠费、教练费用、工资和结算，但不因财务可见权限自动获得排期执行或审批能力；
- **负责人／管理员**：当前 Venue 的完整经营报告、高影响异常、策略和模型配置，并按显式 capability 执行审批或业务动作。

角色只提供版本控制的默认 capability 包，最终授权仍由服务端 Membership 解析。OperationsReportSnapshot 可以保存完整确定性快照，但 REST、Tool、Trace 展示和模型上下文必须按当前用户／目标受众 capability 投影字段；未授权用户不能通过 metric_ref、异常文本、分项、导出或 Trace 旁路推断全馆财务和工资数据。

首版每个部署只选择一个活动 Venue，不提供跨场馆 UI；但后端所有读取、扫描、Runtime、Tool、报告和审计必须从认证上下文取得 OrganizationScope 和 VenueScope。Scope 不能由 LLM 自由选择，也不能通过查询第一条 Venue 隐式推断。

系统必须在模型关闭时仍提供：

- 确定性扫描和案件列表；
- 原始证据、业务链接和 Verifier 状态；
- 人工记录跟进、驳回、关闭请求和升级；
- 现有全部人工业务页面。

Agent 输出必须以卡片化结构呈现：

- **发现依据**：检测规则、时间范围、业务记录和数据口径；
- **诊断**：只引用工具事实，区分事实、推断和未知；
- **处理计划**：每一步标明 read、human、approval 或 action；
- **影响摘要**：可能改变的排期、资源、金额或课时；MVP 写工具只涉及排期；
- **验证结果**：Verifier 规则、读取时间、通过或失败原因；
- **后续跟踪**：下次检查时间、截止时间和升级条件。

经营报告使用独立报告视图，至少包含：

- **报告口径**：日／周／月、业务时区、完整或进行中、统计起止、generated_at 和对比窗口；
- **确定性指标**：财务、业务数量、考勤／课时、教练费用、场地使用和时点余额；
- **分项与引用**：业务类型、固定班、场地等可追溯分项；
- **确定性异常**：规则、阈值、metric_ref、对比值和数据充分性；
- **智能解读**：总结、异常解释、建议和限制，明确与事实分区；
- **降级状态**：模型不可用时仍展示完整快照和异常规则。

## 5. 统一运营案件模型

### 5.0 OrganizationScope、VenueScope 与 OperationsPolicy

智能运营的最小安全边界是一个经营机构下的一个场馆。第一版 UI 虽然只激活一个 Venue，但所有新旧业务查询和运营实体都必须能够确定 organization_id 和 venue_id。

**OrganizationScope／VenueScope 规则**:

- Organization 代表独立经营主体，Venue 归属于 Organization；当前已有 Venue 数据迁移到一个默认 Organization；
- 登录会话解析 organization_id、venue_id、user_id 和 capabilities，形成不可变 RequestScope；
- 外部模型能力使用服务端控制的 per-Venue feature flag，新建或迁移 Venue 默认关闭；只有具备 operations.model.manage 的负责人可以明确启用或再次关闭，模型凭据存在不得自动开启任何 Venue；
- LLM、前端 Tool 参数和业务备注不得覆盖 RequestScope；跨 Scope 的 ID 即使格式合法也必须按不存在处理并记录安全事件；
- 业务聚合根优先直接保存 venue_id；子记录可通过强外键链继承，但高频共享事实、审计和所有 Operation 实体必须可直接校验 Scope；
- 第一版不承诺同一用户切换多个 Venue、集团汇总或跨机构数据共享。

**OperationsPolicy** 是按 Venue 生效、版本化的确定性运营配置，不是通用规则引擎。至少覆盖：

- 欠费跟进账龄和升级期限；
- 固定班结束提醒窗口、私教课包到期／余量阈值和跟进节奏；
- 考勤逾期宽限期；
- 补排候选窗口、时间粒度和允许的资源策略；
- 报告异常阈值、数据充分性和严重度基线；
- 低风险操作确认、审批过期和案件 SLA。

Policy 由确定性配置和代码规则组成，具有用户可识别的名称、policy_key、policy_version、effective_from、effective_to、venue_id、schema_version 和 status。草稿可查看、重命名、编辑和删除；生效与历史版本只读，但可复制为新草稿。创建、编辑、复制、删除和激活均需权限校验、并发版本校验和审计。Case、Run、Snapshot、ToolCall 和 Approval 保存实际使用的 policy_version；修改 Policy 不追溯改写历史结论。

初始 Policy 的阈值不是现有业务事实，不由本 Spec 假装已有。Phase 0 必须由场馆负责人确认首个 policy_version 后才启用对应 Detector；未配置的规则返回 policy_not_configured 并保持禁用，LLM 不得补造默认阈值。

### 5.1 OperationCase

代表一个需要持续处理的经营问题，而不是一次模型对话。

**核心字段**:

- id、organization_id、venue_id、case_type、subject_type、subject_id；
- detector_key、detector_version、fingerprint、policy_key、policy_version；
- severity、priority_score、title、business_summary；
- state；
- first_detected_at、last_detected_at、next_check_at、due_at；
- queue_key、required_capability、assigned_to?、assigned_at?、assigned_by?、created_by_type、resolved_at、resolution_code；
- evidence_hash、current_run_id、version、created_at、updated_at。

**唯一性**:

- 同一 organization_id、venue_id、detector_key、subject_type、subject_id、活动 occurrence 只能有一个未终结案件；
- fingerprint 由规范化确定性证据生成；证据未变化时重复扫描只更新时间和事件；
- resolved 后出现新的业务事实可增加 occurrence 并重新打开，但不能覆盖旧关闭事件。

**责任队列与分配**:

- Detector 通过版本控制的 case_type registry 确定 queue_key 和 required_capability，LLM 不参与选择队列、人员或权限；
- 新案件默认 assigned_to 为空并进入对应角色队列；具备 required_capability 的当前 Venue active 成员可以认领，具备 operations.case.assign 的负责人可以分配或改派；
- 不能把案件分配给其他 Scope、disabled／pending_review 成员或缺少 required_capability 的人员；
- 未认领案件继续按 severity、due_at 和 OperationsPolicy 计算 SLA、简报和升级，不因无人认领停止跟踪；
- assignee 被禁用、离开 Venue 或失去 required_capability 时，系统在同一权限变更事务或紧随其后的确定性维护步骤中清空 assigned_to、写入审计并放回原 queue_key；
- 认领、分配、改派和退回队列都是人工责任事实，必须记录操作人、前后人员、原因和时间，不能只写 OperationEvent。

### 5.2 OperationRun

代表某个案件的一次分析、计划、执行或复核尝试，也可代表一次不绑定案件的经营报告或确定性简报生成。报告 Snapshot 是 Run 的产物，不与 Run 建立双向外键；Narrative 重试通过 parent_run_id 引用先前 Run，并在 input_refs 中引用不可变 Snapshot。

**核心字段**:

- id、organization_id、venue_id、case_id?、parent_run_id?、run_type、trigger_type、workflow_key、workflow_version；
- policy_key、policy_version、input_refs、input_hash；
- prompt_version、toolset_version、model_profile；
- state、checkpoint、attempt、next_attempt_at；
- max_steps、max_model_calls、max_tool_calls、max_write_calls、deadline_at；
- model_call_count、tool_call_count、write_call_count、token_usage_summary；
- lease_owner、lease_expires_at；
- error_code、error_summary、started_at、finished_at、created_at、updated_at。

工作流、Prompt 和 Tool 定义首版保存在版本控制的代码与配置中；运行记录冻结版本标识。第一版不建立可视化 WorkflowDefinition、AgentDefinition 或 Prompt 编辑数据库。

### 5.3 OperationEvent

案件、报告与运行的追加型 Trace 事件。

**核心字段**:

- id、organization_id、venue_id、case_id?、run_id、sequence；
- event_type、actor_type(system|user|model|tool)、actor_id；
- trace_id、request_id、payload_redacted、payload_hash；
- occurred_at。

事件不可修改；敏感原文不直接进入 payload_redacted。业务写操作仍必须另外写入现有 AuditLog。

### 5.4 OperationToolCall

记录一次工具提议和执行事实。

**核心字段**:

- id、organization_id、venue_id、run_id、case_id?、tool_key、tool_version；
- policy_key、policy_version；
- risk_level、normalized_input、input_hash、impact_snapshot；
- subject_versions、required_capability；
- state、idempotency_key、result_reference、result_summary；
- error_code、attempt、started_at、finished_at。

### 5.5 OperationApproval

绑定一个不可变 ToolCall 的人工决定。

**核心字段**:

- id、organization_id、venue_id、tool_call_id、case_id?、requested_by；
- policy_key、policy_version；
- approval_policy、risk_level、action_summary、impact_snapshot；
- input_hash、subject_versions、required_capability；
- state、expires_at、decided_by、decision_reason、decided_at、version。

修改参数不更新旧审批，而是取消旧 ToolCall 和 Approval，创建新提议。

### 5.6 OperationsReportSnapshot

代表一次已生成、可复核的经营报告确定性快照。它是派生证据，不是新的资金、课时、排期或工资事实来源。

**核心字段**:

- id、organization_id、venue_id、run_id、period_type(day|week|month)、period_start、period_end、effective_end；
- business_timezone、period_state(complete|in_progress)、generated_at、generated_by；
- comparison_start、comparison_end、comparison_status；
- policy_key、policy_version、metric_version、metrics、breakdowns、source_refs、evidence_hash；
- anomaly_rule_version、anomalies；
- narrative_state、summary、anomaly_explanations、recommendations、caveats；
- model_profile、prompt_version、created_at。

**约束**:

- metrics、breakdowns 和 anomalies 由确定性程序生成，保存后不可修改；
- summary 和 recommendations 只能引用 snapshot 内的 metric_ref、anomaly_id 和 source_ref；
- 相同期间重新生成时创建新快照，不覆盖历史；
- 模型失败时 narrative_state 为 unavailable／failed，但确定性快照仍是成功报告；
- 高严重度异常若需要持续处理，只能通过已有 Detector 创建或关联 OperationCase，不由 LLM 直接创建重复案件。

### 5.7 CaseActivity

代表人员在欠费、续费和其他持续运营案件中的结构化业务跟进事实，不是模型 Trace，也不修改原始资金、报名或权益事实。

**核心字段**:

- id、organization_id、venue_id、case_id；
- activity_type(contact_attempt|contact_result|promise|note|status_decision)；
- channel、contact_subject_type、contact_subject_id?；
- outcome_code、summary、happened_at、next_check_at?；
- operated_by、source(run|manual)、run_id?、created_at。

**约束**:

- 联系电话、微信号等敏感值不复制到 activity；只保存联系人业务引用和必要的脱敏显示；
- outcome_code 使用受控枚举，summary 是不可信自由文本；
- “已联系”或“承诺付款”不能直接关闭欠费或续费案件；Verifier 仍读取真实资金、报名或课包事实；
- OperationEvent 记录创建 CaseActivity 的运行过程，CaseActivity 用于后续跟进、责任归属和转化统计，两者不得互相替代。

### 5.8 不新增的首版实体

- 不新增通用 Conversation 和 Message 作为核心事实；
- 不新增 AgentDefinition、WorkflowDefinition、WorkflowVersion、AgentStep、Artifact、Budget 独立表；
- 不复制应收余额、课时余额、排期状态或工资状态到 Agent 表；
- 不新增向量库或 RAG 索引；
- 不新增完整 CRM、营销活动、线索评分或外部消息收件箱；CaseActivity 只覆盖运营案件内的结构化跟进。

## 6. 状态机与统一 Loop

### 6.1 Case 状态

~~~text
open
  -> analyzing
  -> action_proposed
  -> waiting_approval
  -> executing
  -> verifying
  -> monitoring
  -> resolved

任意非终态 -> waiting_human
任意非终态 -> escalated
open|waiting_human|monitoring -> dismissed（必须由人填写原因）
resolved|dismissed -> open（仅新 occurrence 或新的确定性证据）
~~~

模型不能直接写 Case 状态。每个转换由状态机根据 Run、Approval、ToolCall 和 Verifier 结果执行。

### 6.2 Run 状态

~~~text
queued -> running
running -> waiting_approval | waiting_human | retry_scheduled
waiting_approval -> queued | cancelled | escalated
retry_scheduled -> queued
running -> succeeded | failed | escalated | cancelled
~~~

终态 Run 不恢复；需要继续时创建新的 Run：案件工作流关联同一 Case；经营报告 Narrative 重试以 parent_run_id 关联原 Run，并在 input_refs 中引用同一 OperationsReportSnapshot。

### 6.3 Loop

1. **Scope**：从认证会话解析不可变 OrganizationScope、VenueScope、capabilities 和有效 OperationsPolicy；缺失或冲突时停止。
2. **Detect**：确定性扫描器只读取当前 Scope 内的 Query／领域事实，创建或更新 Case。
3. **Gather**：只读 Tool 获取受 Schema 约束的证据和业务链接。
4. **Plan**：LLM 输出结构化诊断、未知项、候选行动和停止条件。
5. **Guard**：确定性 Policy 校验 Scope、工具白名单、权限、风险、Schema、时间范围、调用预算和证据引用。
6. **Propose**：只读结果直接展示；写动作生成不可变 ToolCall 和影响摘要。
7. **Approve／Human**：需要人工沟通或审批时持久化 checkpoint 并停止占用执行器。
8. **Revalidate**：恢复后重新校验 Scope、会话用户、capability、policy_version、审批有效期、输入哈希、业务版本和当前影响。
9. **Execute**：调用当前 Scope 内的现有应用层业务命令，不调用内部 HTTP，不直接操作仓储。
10. **Verify**：确定性 Verifier 在同一 Scope 内重新读取业务事实，判定 passed、pending 或 failed。
11. **Close／Monitor／Escalate**：通过则关闭；等待外部事实则设置 next_check_at；不可安全恢复或超限则升级。

### 6.4 Retry、Stop 与恢复

默认运行预算：

- 最多 8 个 Loop step；
- 最多 3 次模型调用；
- 最多 8 次只读工具调用；
- 最多 1 次写工具调用；
- 同一瞬时故障最多重试 2 次并指数退避；
- 单次 active execution 最长 5 分钟，等待审批或人工不计入 active execution；
- 审批默认 30 分钟过期；
- 同一 evidence_hash 连续两轮无进展时停止自动循环。

重试规则：

- 只读查询和模型超时可以自动重试；
- 写工具只有在幂等结果可查询且确定未产生第二次副作用时才可重试；
- 写工具处于 executing 后进程中断，恢复时先运行 outcome reconciliation；
- 无法判断“成功还是失败”时标记 uncertain／escalated，禁止盲目重试；
- 达到预算、出现未知工具、策略冲突、数据缺失、审批过期或重复无进展时停止并转人工。

所有 Run、ToolCall、Approval 和 checkpoint 必须持久化到当前业务数据库。进程启动后通过 lease_expires_at 回收中断运行，从最后已提交 checkpoint 继续。

## 7. 场景规格

### 7.1 主动发现与每日运营简报

**Trigger**:

- 应用启动后的 catch-up scan；
- 应用运行期间每 15 分钟一次的轻量确定性扫描；
- 管理人员手动“立即扫描”；
- 每个业务日首次成功扫描后生成一次每日简报；
- 未来可在关键业务命令提交后登记 subject 进行增量复核，但 MVP 不要求事件总线。

**初始 Detectors**:

1. attendance.overdue：课程仍为 scheduled、结束时间超过配置宽限期、attendance_finalized_at 为空；若固定班当前没有有效报名学员，案件必须引导用户将该节标记为“未开课（无学员）”，释放排期且不生成考勤、课时扣减或教练费用，不得要求提交空考勤；
2. class.replacement_pending：课程为 cancelled 且 replacement_decision 为 pending；
3. receivable.aging_followup：非 void 应收未结清且 created_at 账龄达到阈值；
4. reconciliation.failed：第 7.5 节任一确定性规则失败；
5. class.renewal_opportunity：固定班最后一节 scheduled 课程进入 Policy 提醒窗口，且班级仍为 active；
6. private_package.renewal_opportunity：私教课包仍为 active，且有效期或派生剩余课时进入 Policy 阈值。

**Agent**:

- 生成每日摘要、跨案件优先级和建议处理顺序；
- 解释排序依据，不改变 detector 严重度基线；
- 数据不足时保留确定性卡片并省略推断。

**Verifier／结束条件**:

- 每个 Case 使用自己的 Verifier；
- 简报生成成功或确定性降级简报展示成功即结束简报 Run；
- 扫描器本身只创建和更新案件，不执行业务写入。

### 7.2 欠费与续费机会持续跟进

**Trigger**:

- outstanding_amount 大于 0 且账龄跨过配置阈值；
- 金额、净实收、退款、状态或账龄档位变化；
- next_check_at 到期；
- 人工立即重新分析。

续费机会另外由以下条件触发：

- active 固定班最后一节 scheduled 课程进入 policy_version 对应的结束提醒窗口；
- active 私教课包的 valid_until 进入到期窗口，或由 LessonUnitLedger 派生的剩余课时达到配置阈值；
- 关联班级、报名、课包、应收、剩余课时或 next_check_at 发生确定性变化。

**Evidence**:

- Receivable ID、source_type、source_id、业务显示名称和业务链接；
- suggested_amount、actual_amount、received_amount、refunded_amount、net_received、outstanding_amount、payment_status、status、version；
- created_at、账龄天数、历史 CaseActivity；
- 联系人是否存在，但默认不把电话、微信备注或凭证地址发送给模型。
- 续费案件另外读取固定班最后计划结束时间、剩余 scheduled 课程、有效报名、课包 valid_until、派生剩余课时和现有应收状态；
- 当前没有续费意向字段；历史自由文本不得被模型解释为已同意续费。

**Agent**:

- 在确定性严重度和金额事实基础上做处理顺序建议；
- 生成不承诺结果的沟通草稿；
- 指出缺失联系人、业务已取消但仍欠费等需要人工核对的情况；
- 对续费机会生成可编辑的联系顺序和沟通草稿，但不得承诺名额、价格、优惠或续费成功；
- 不自行判断客户信用、支付意愿或退款责任。

**Actions**:

- record_followup_outcome：低风险运营内部写入，创建结构化 CaseActivity，记录渠道、outcome_code、结果摘要、下次跟进时间和操作人；
- open_business_record：只读导航；
- 不注册 record_payment、record_refund、adjust_receivable、void、renew_class、create_private_package、create_receivable 或 entitlement 工具。

**Verifier**:

- 重新调用 receivable_summary；
- outstanding_amount 等于 0 或 status 等于 void 时通过；
- 仍未结清但 next_check_at 未到时进入 monitoring；
- 达到最大跟进次数、超过 due_at 或被标记争议时 escalated；
- dismissed 只能由人操作且必须填写原因，不能伪装为已收清。

续费 Verifier：

- 固定班续费只有在现有 renew_fixed_class 流程创建新的 ClassSession，并按实际选择产生续期 LessonUnitLedger／应收更新和固定班续期 AuditLog 后通过；未选择任何学员续期时不得虚构学员已续费；
- 私教续费只有在现有人工页面创建可追溯的新课包后通过；
- outcome_code=no_intent 可由人 dismissed，follow_later 进入 monitoring；“已联系”或“承诺考虑”不能 resolved；
- 原业务已取消、归档、转移或数据不足时按确定性状态 dismissed／escalated，不由 LLM 猜测结果。

### 7.3 取消课程整班补排

**Trigger**:

- ClassSession.status 等于 cancelled 且 replacement_decision 等于 pending；
- 候选过期、冲突变化或审批 stale；
- 人工请求重新生成候选。

**Evidence**:

- 原课程、固定班、原开始结束时间、时长、原教练、原场地；
- 课程 version、取消原因、班级状态；
- 场馆时区和营业时间；
- 候选窗口内原教练和原场地 ScheduleAllocation；
- 当前固定班没有学员可用性数据这一明确限制。

**Deterministic candidate generator**:

- 仅生成整点开始、与原课相同时长、同一业务日内的时段；
- MVP 候选窗口默认为未来 14 天，可由人缩小；
- MVP Policy 只使用原课程的教练和场地资源；
- 排除营业时间外、过去时间和任一资源冲突；
- 返回不可变 resource_plan_id、resource_policy_version、候选 ID、开始结束、教练与场地资源引用、与原时段的偏移、冲突检查时间和 evidence hash；
- 候选 Schema 允许未来由更高版本确定性策略提供“原教练 + 其他满足 required_court_count 的活动场地”，但 MVP Tool 和现有业务命令不接受此类方案。

**Agent**:

- 在合法候选内按与原星期／时间接近、延迟较短等软偏好排序；
- 生成“待向学员确认”的协调清单或沟通草稿；
- 不能创建新的候选时间，也不能声称学员已同意。

**Approval**:

- 风险级别 medium；
- 管理人员必须选择一个仍有效的已生成候选，不得在 Agent 审批流程中填写候选之外的新时段；无合适候选时应调整允许的候选窗口重新生成，或退出 Agent 流程使用现有人工业务页面；
- 必须勾选“已与相关人员确认”并查看资源影响；
- 需要 operations.schedule.execute 和 operations.approval.decide；
- MVP 允许具备能力的同一管理人员自审批；未来高风险资金和权益动作不继承该政策。

**Action**:

- schedule_cancelled_class_replacement；
- 映射现有 schedule_cancelled_session_replacement 用例；
- 输入只包括 session_id、version、resource_plan_id、replacement_start、replacement_end、actor_id、request_id 和 runtime idempotency_key；
- 不允许换教练、换场地、修改金额、修改课时或批量补排。

**实施前提**:

- 现有命令需要支持调用方管理事务或提供等价的事务内应用服务；
- Agent ToolCall 结果与业务补排写入必须可原子记录，或能够以幂等键和业务关联确定性恢复；
- 现有 version、冲突校验和 AuditLog 继续作为最终裁决。

**Verifier**:

- 原课程仍为 cancelled；
- replacement_decision 等于 scheduled；
- 恰有一个 ClassSession.replacement_for_session_id 指向原课程；
- 新课程状态为 scheduled；
- 新排期存在且有效，资源为批准快照中的原教练和原场地；
- 新排期时间等于批准参数，资源冲突查询为空；
- 全部通过后 resolved；任一不确定结果 escalated。

### 7.4 指定日／周／月经营报告

**Trigger**:

- 管理人员选择 period_type 和一个业务日期后手动生成；
- 每日运营简报可以引用当日最新快照，但不得静默生成周报或月报；
- MVP 不自动定时发送或向外部渠道发布报告。

**期间口径**:

- day：所选日期在 Venue.timezone 下的业务日；
- week：包含所选日期的周一至周日；
- month：包含所选日期的自然月第一日至最后一日；
- 已结束期间统计完整区间；当前期间只统计到 generated_at，并标记 in_progress；
- 未来期间拒绝生成；
- day 默认对比上周同一星期几的业务日；week 对比上一自然周；month 对比上一自然月；
- 当前进行中期间只与对比期的相同已过本地时长比较；不存在足够数据时 comparison_status=data_insufficient。

**确定性指标**:

1. 财务：期间有效收入、退款、经营支出、收付实现利润、收入来源占比、固定班实收／退款／欠费分项；
2. 时点余额：截至 generated_at 的当前全部未结清应收、未结清笔数和当前全部待结教练费用；
3. 教练费用：期间产生费用、期间产生且当前待结费用、期间实际结算金额和对应明细数；
4. 业务数量：固定班课程、私教、场地预订、临时活动的计划／完成／取消数量，以及可确定计算的取消率；
5. 考勤与课时：期间已完成固定班课程的考勤状态数量、有效考勤扣课和私教课包扣课课时、逾期未考勤数量；
6. 场地：各场地经营使用时长、基础营业时长、CourtBlock 不可售时长、扣除不可售后的可营业时长、原始利用率、展示利用率、营业时间外占用和整体加权利用率；
7. 数据质量：缺失分项、不可计算指标和 comparison_status。

CourtBlock 通过其 ScheduleEntry／ScheduleAllocation 识别：只扣除与 Venue 营业时间重叠且状态有效的对应场地时长，不计入经营使用；同一场地的重叠 Block 取时间并集，避免重复扣除；营业时间外 Block 不影响分母。Block 与经营排期异常重叠时保留经营使用事实并产生确定性数据质量证据，不能通过重复扣减掩盖冲突。补排候选仍把有效 CourtBlock 视为资源冲突。

所有指标带 metric_id、scope(period|as_of)、unit、value、display_precision、source_refs 和 calculated_at。原始利用率不得为展示而覆盖或截断；若 UI 需要最多显示 100%，必须另存 display_value，并把超过 100%、营业时间外占用、Block 与经营排期重叠或分母异常作为数据质量证据。当前业务模型不能可靠重建的历史时点余额不得伪造；此类指标只作为 as_of generated_at 展示。

**确定性异常规则**:

- 期间收入相对可比期显著下降；
- 退款金额或退款／收入比例超过配置阈值；
- 支出显著增长或收付利润为负；
- 当前未结清应收金额／笔数超过配置阈值；
- 课程或业务取消率超过阈值；
- 存在逾期未考勤；
- 场地利用率低于阈值或相对可比期显著下降；
- 当前待结教练费用超过金额或账龄阈值。

规则必须版本化并返回 anomaly_id、rule_key、severity、metric_refs、threshold、comparison、evidence 和 data_sufficiency。LLM 不参与阈值计算、异常命中或 severity 基线。

**LLM**:

- 输入仅包含脱敏后的 OperationsReportSnapshot，不读取原始数据库行；
- 输出 executive_summary、highlights、anomaly_explanations、recommendations 和 caveats；
- 每个事实陈述必须引用 metric_ref、anomaly_id 或 source_ref；
- 金额、数量、课时、比例和利用率通过引用插值或确定性校验后渲染；
- 建议必须关联事实，标注目标、理由、需要人工确认的步骤和风险；
- 数据只能支持相关性时不得声称根因；可能原因必须标记为假设；
- 不调用任何业务写工具，不根据建议自动创建价格、排期、收付款、课时或结算变更。

**Verifier／结束条件**:

- 校验 period_type、业务时区、完整／进行中边界和对比窗口；
- 对固定业务夹具重算 metrics、breakdowns 和 anomalies，结果必须与 snapshot 一致；
- 校验所有显示数值均来自有效 metric_ref，所有异常解释引用有效 anomaly_id；
- 无业务数据时输出合法空报告；基准为零时不计算虚假百分比；
- 确定性快照保存成功即视为报告生成成功；Narrative 失败只触发降级或有限重试；
- 整个报告流程对现有业务事实产生 0 条写入。

### 7.5 一致性对账

**Trigger**:

- 每日一次全量扫描；
- 管理人员手动扫描；
- P2 可在相关业务写命令后对 subject 增量验证。

**MVP Rules**:

1. ledger.chain：每条有效流水满足 balance_after = balance_before + delta，同一 owner 的相邻有效流水首尾相接，余额不为负，idempotency_key 唯一；
2. receivable.summary：有效收款和退款汇总不越界，Receivable.status 与派生状态一致；
3. class.completion：completed ClassSession 有 attendance_finalized_at 和对应 CoachFee；不尝试根据当前 active enrollment 数量推断历史考勤完整性；
4. private_lesson.completion：completed 课包私教有一次有效扣课流水和一条 CoachFee，单次私教有应收；
5. coach_fee.source：非 void CoachFee 的来源业务存在且处于可产生费用的完成状态；
6. payroll.integrity：confirmed PayrollSettlement 关联唯一有效工资 Expense，金额一致，关联 CoachFee 属于同一教练和自然月且为 settled；
7. schedule.integrity：有效业务排期头、时间和 active allocations 一致，cancelled 或 rescheduled 旧排期不保留 active allocation；
8. refund.reversal：作废退款对应扣课流水已 reversed，并有反向流水恢复权益状态。

**Agent**:

- 按受影响金额、课时、排期和后续业务数量汇总；
- 解释规则、引用记录和建议人工修复顺序；
- 不生成 SQL、不修改记录、不把推测写成根因。

**Actions**:

- open_business_record、open_audit_trace、rerun_reconciliation；
- MVP 不注册 auto_repair、ledger_adjust、receivable_sync、fee_void、settlement_void 等修复工具。

**Verifier／结束条件**:

- 原 detector rule 使用同一或更高版本重跑通过；
- 规则升级造成的语义变化必须创建新 occurrence，不静默关闭旧案件；
- 连续三次每日扫描仍失败或涉及资金／课时安全时 escalated。

## 8. Tool Registry、权限与 Guardrails

### 8.1 Registry 形式

Tool 定义由代码注册并进入版本控制，包含：

- tool_key、description、input_schema、output_schema；
- implementation_version、risk_level、required_capability；
- approval_policy、idempotency_scope、timeout；
- handler、verifier、redaction_policy；
- enabled feature flag。

数据库只保存运行时冻结版本和调用事实，不允许管理人员在 UI 中创建任意 Tool。

### 8.2 MVP Tool 清单

| Tool | 类型 | 风险 | 审批 | 数据来源／实现 |
|---|---|---:|---|---|
| get_case_evidence | 只读 | read | 否 | 运营聚合 Query |
| get_receivable_followup_context | 只读 | read | 否 | Receivable Query + 业务显示名称 |
| get_renewal_followup_context | 只读 | read | 否 | FixedClass／Enrollment／PrivateLessonPackage／LessonUnitLedger 聚合 Query |
| list_replacement_candidates | 只读 | read | 否 | ScheduleAllocation、Venue、冲突规则 |
| get_reconciliation_result | 只读 | read | 否 | 确定性对账规则 |
| get_operations_report_snapshot | 只读派生 | read | 否 | 现有 operations_report + 确定性指标／对比／异常聚合 |
| record_followup_outcome | 内部运营写 | low | 显式确认 | CaseActivity + OperationEvent，不改资金、报名或权益事实 |
| dismiss_operation_case | 内部运营写 | low | 人工操作 | 必填原因，模型不能调用 |
| schedule_cancelled_class_replacement | 业务写 | medium | 强制 | 现有整班补排应用服务 |

以下工具明确禁止注册：execute_sql、run_shell、任意文件读写、任意 HTTP、动态代码、插件安装、模型自修改 Prompt、登记收款、退款、应收调整、考勤提交、课时调整、权益终止／转移、课程取消、费用调整、工资结算和任何作废工具。

### 8.3 最小权限扩展

当前项目没有角色／权限。开放任何 Agent 写工具前必须增加服务端 capability 检查，至少包含：

- operations.case.read；
- operations.case.manage；
- operations.case.assign；
- operations.receivable.followup.read；
- operations.report.read；
- operations.report.financial.read；
- operations.report.generate；
- operations.payroll.read；
- operations.approval.decide；
- operations.schedule.execute；
- operations.trace.read。
- operations.policy.read；
- operations.policy.manage。
- operations.model.manage。

用户权限必须通过 OrganizationMembership／VenueMembership 或等价的服务端成员关系解析。当前代码没有 owner／admin 角色；迁移应把现有 active SystemUser 关联到默认 Organization／Venue，生成一次权限复核清单，并在场馆负责人确认前禁用 Agent 写 Tool。确认后再按最小权限授予 capability。权限检查必须在 Tool Handler 和复用的业务应用服务内执行，不能只在前端隐藏按钮。

固定角色包至少满足：owner／admin 可被授予全部读取能力；finance_viewer 包含全馆财务和工资读取但不隐含排期执行或审批；operations_manager／operator 只通过 operations.receivable.followup.read 获取当前被授权跟进案件的必要单笔金额，不能读取全馆财务、工资或结算。Snapshot、Tool 输出、模型输入、Narrative、Trace 和业务链接必须使用同一字段级 capability 投影。

具备案件 required_capability 的 active 成员可以认领自己的案件；operations.case.assign 只用于负责人向其他合格成员分配或改派，不允许绕过被分配人的 Scope 和 required_capability。

### 8.4 Approval Guard

- read 工具不需要审批；
- low 内部运营写需要明确用户操作和审计，不允许后台静默执行；
- medium 补排写必须生成审批卡，具备能力的管理人员可以自审批；
- high 资金、权益、考勤、取消、费用和结算工具不在 MVP Registry；
- 审批绑定 organization_id、venue_id、policy_version、tool_key、tool_version、input_hash、impact_snapshot、subject_versions 和 required_capability；
- 执行前任一值变化则 stale；
- rejected、expired、stale 或 modified 的审批不可执行；
- 审批文本不得由模型隐藏金额、课时、场地或时间影响。

### 8.5 Input 与 Output Guard

- 严格拒绝未知字段；
- 日期窗口、文本长度、ID 格式和枚举必须有上限；
- 模型只能引用 Registry 中的 tool_key；
- organization_id、venue_id、capabilities 和 policy_version 由服务端 Scope 注入，模型提供这些字段时必须拒绝或忽略，不能覆盖真实 Scope；
- 所有 Tool 输出附 generated_at、source_refs、schema_version 和 evidence_hash；
- 金额使用定点字符串或后端 Decimal 序列化，不在模型中使用浮点计算；
- PII 默认去除电话、微信、凭证地址、Cookie、密钥和原始附件；
- 业务备注视为不可信数据并标注 data，不与系统指令拼接。

## 9. 幂等、事务与恢复

- 每个副作用 ToolCall 在 organization_id + venue_id + tool_key 作用域内拥有唯一 idempotency_key；
- 运行恢复首先按 idempotency_key 查询历史 ToolCall 和业务结果；
- 现有 Payment、Refund、Expense、OtherIncome、PayrollSettlement 和课时流水的幂等实现继续保留，但它们不因此自动成为 Agent 工具；
- 整班补排当前依赖 state + version 防重复，不足以在提交后崩溃时返回同一结果；MVP 必须补充 Tool 级幂等结果映射；
- Agent 写工具必须在同一数据库事务中完成业务事实、业务 AuditLog 和可恢复的 ToolCall 结果，或提供可证明等价的 outcome reconciliation；
- 进程内锁、浏览器状态和模型上下文不能作为唯一幂等依据；
- 外部消息、支付或其他未来系统若接入，必须单独使用 outbox／provider idempotency，不沿用数据库写工具的假设。

## 10. Tracing 与 Audit

### 10.1 Trace

每个扫描、Run、模型调用、ToolCall、Approval 和 Verifier 共享 trace_id，并记录：

- organization_id、venue_id、case_id?、run_id、request_id；
- detector／workflow／prompt／tool／verifier 版本；
- 输入和输出 Schema 版本、脱敏摘要与 hash；
- 模型 provider、model、请求 ID、token、延迟和状态；
- Tool 风险、权限判定、审批 ID、幂等键、尝试次数和结果引用；
- 状态转换、重试原因、停止原因和恢复 checkpoint；
- Verifier 证据、结果和关闭条件。

MVP 前端不需要复杂监控台；案件时间线和管理员 Trace 详情足够。实时进度首版使用轮询，当前规模不需要 SSE。

### 10.2 Business Audit

- OperationEvent 解释 Agent 如何得出和执行计划；
- CaseActivity 记录人员实际完成的运营跟进，支持责任归属和后续转化统计；
- 现有 AuditLog 证明业务事实由谁、在何时、以何原因改变；
- OperationEvent、CaseActivity 与 AuditLog 通过 trace_id／request_id／tool_call_id 关联，但不能互相替代；
- Agent 发起的业务写入 actor 必须是实际审批并执行的用户，不能使用虚构的“AI 用户”代替责任人；
- 审计不得记录密码、会话 Cookie、模型密钥、完整电话、完整凭证 URL 或附件正文。
- AuditLog、Trace、CaseActivity 和业务引用必须带可验证的 Organization／Venue Scope；任何跨 Scope 关联均视为安全缺陷。

### 10.3 Retention

- 业务 AuditLog 延续现有业务保留策略；
- OperationCase、CaseActivity、Approval 和业务写 ToolCall 至少保留 2 年；
- 普通模型输入输出脱敏摘要默认保留 180 天，可配置缩短；
- 原始模型 Prompt／Response 默认不长期保存，只保存测试环境可控样本、hash、结构化结果和错误摘要；
- 删除或归档运行记录不能删除关联业务事实和业务审计。

## 11. Agent Eval 与 CI

### 11.1 Eval 分层

1. **规则测试**：detector、fingerprint、state machine、candidate generator、Verifier、权限和审批纯单元／属性测试；
2. **Tool Contract**：每个 Tool 的 Schema、脱敏、权限、风险、幂等和错误码契约；
3. **Runtime Integration**：数据库 checkpoint、lease 接管、审批暂停恢复、提交后崩溃、stale version、冲突和 uncertain outcome；
4. **Agent Scenario Eval**：固定中文用例验证诊断、计划、工具选择、引用、abstention 和注入防护；
5. **业务端到端**：从扫描到案件关闭，验证业务表、运行表、Trace 和 Audit；
6. **真实模型回归**：在受控环境按固定 Prompt／model profile 执行，不作为每个 PR 的唯一门禁。
7. **Scope Isolation**：两个 Organization、多个 Venue 使用可碰撞的显示名、场地编号和业务时间，验证查询、Detector、Tool、Snapshot、Trace 和导出没有跨 Scope 数据。

### 11.2 固定评测集

评测数据使用匿名化、版本化的业务夹具，不直接复制实际联系电话或凭证。至少覆盖：

- 三类来源的未结清应收、分次付款、部分退款和作废；
- 固定班结束、已续期、暂不续费、私教课包到期／余量不足、联系人不足和多次 CaseActivity；
- 取消课程待补排、无候选、候选冲突、审批过期和并发修改；
- 日／周／月边界、当前部分期间、上周同日／上一周／上一月对比、零基准和数据不足；
- 收付实现制指标、期间与时点口径、业务数量、考勤课时、教练费用和场地利用率；
- LLM 数值引用、异常引用、可能原因降级和不受支持建议拒绝；
- 缺失联系人、缺失教练／场地显示信息和空数据；
- 流水断链、负余额、重复幂等键、结算／支出不一致；
- 模糊日期、跨日、过去时间和超营业时间；
- 业务备注中的提示注入；
- 要求 SQL、Shell、任意 URL、高风险写入或跳过审批；
- 模型超时、结构化输出失败、Tool 超时、进程重启和结果不确定。
- 4、10、15 片活动场地的排期、候选枚举、报告和扫描数据集；
- 两个 Organization 中重复的场地 code、姓名和业务 ID 引用，以及恶意跨 Scope Tool 输入；
- OperationsPolicy 版本切换、旧 Case／Snapshot 可重现、旧审批 stale 和新 occurrence。

### 11.3 CI 门槛

每个 PR 必须运行：

- 后端单元、SQLite 集成、API Contract；
- 涉及 lease、并发或事务的 PostgreSQL 集成；
- 前端类型检查、组件测试；
- 使用模型 Stub 的确定性 Runtime 回归；
- 离线 Agent Eval，固定模型输出或录制响应；
- OpenAPI 客户端漂移检查。

合并门槛：

- detector 和 Verifier 夹具准确率 100%；
- 金额、课时、时间和记录引用与 Tool 结果一致率 100%；
- 报告 snapshot 的指标、对比和异常规则结果一致率 100%，LLM 未引用数值为 0；
- 未审批写入、越权写入、禁用工具调用和重复副作用均为 0；
- 注入用例中的政策绕过为 0；
- 跨 Organization／Venue 读取、写入、模型上下文泄露和 Trace 错链均为 0；
- 同一 policy_version 下 detector、报告和候选结果可重现率 100%；
- 结构化计划 Schema 通过率至少 98%，失败用例必须安全停止；
- 引用完整率至少 95%，涉及金额／课时／排期结论必须 100% 有引用；
- 新版本不得使任何安全指标下降；质量指标下降超过 2 个百分点阻止合并。

真实模型 Eval 可按夜间或人工发布门禁运行。模型供应商波动不得让业务单元测试依赖外网。

## 12. 推荐总体架构

~~~text
React 运营中心
  ├─ 案件列表／每日简报
  ├─ 证据与业务链接
  ├─ 方案／人工输入／审批卡
  └─ Trace 时间线
           │ REST + 轮询
FastAPI 模块化单体
  ├─ RequestScope（Organization / Venue / User / Capabilities）
  ├─ OperationsPolicy（按 Venue 版本化）
  ├─ Operations Detectors（确定性）
  ├─ Case + CaseActivity Service + State Machine
  ├─ Lightweight DB Runner + Lease
  ├─ Agent Orchestrator（普通 Python 状态机）
  ├─ ModelClient（单一适配器起步）
  ├─ Tool Registry + Policy + Redaction
  ├─ Approval Service
  └─ Verifiers（确定性）
           │ 应用层函数调用
现有 Commands / Queries / Domain Rules
           │
当前 PostgreSQL 或桌面 SQLite
  ├─ 现有业务事实与 AuditLog
  └─ Organization / Venue / Policy / Case / Activity / Run / Event / ToolCall / Approval / ReportSnapshot
~~~

### 12.1 技术选择

| 选择 | 决定 | 依据 |
|---|---|---|
| Agent 编排 | 普通 Python 显式状态机 + 数据库 checkpoint | 工作流少且固定；更容易测试、恢复和审计，不需要 LangGraph／Temporal |
| 主动任务 | FastAPI lifespan 内轻量 DB polling runner + lease | 当前单机／单进程、低吞吐；无需 Celery／Redis；状态不只存在内存 |
| Tool 调用 | 进程内应用层调用 | 与人工 API 复用同一规则和事务；不需要 MCP 或内部 HTTP |
| 数据库 | 复用当前 PostgreSQL／SQLite | 规模小、需要与业务事实同事务；不增加运行存储 |
| 商业化作用域 | Organization → Venue + 服务端 RequestScope | 首版仍单活动场馆，但提前固定数据隔离、权限、报告和 Agent 上下文边界；不实现完整 SaaS 管理面 |
| 运营策略 | 版本化结构配置 + 普通确定性规则 | 不同球馆阈值和补排政策不同；不需要动态规则引擎 |
| 模型接入 | 内部 ModelClient Protocol，支持 OpenAI、DeepSeek 和自定义 OpenAI 兼容服务 | OpenAI 使用 Responses API，DeepSeek 使用 Chat Completions；不引入独立 AI Gateway |
| 模型输出 | JSON Schema 结构化输出 | 可确定性校验计划、工具参数、未知项和引用 |
| 前端进度 | REST 轮询 | 运行量小，审批等待长；不需要 SSE／WebSocket |
| 知识检索 | 不使用向量数据库／RAG | 当前核心事实均为结构化实时数据；制度文档需求尚不存在 |
| 通知 | 不接外部渠道 | 当前没有微信／短信／邮件业务能力和授权模型 |
| 多 Agent | 不采用 | 单一案件工作流已经足够；拆分多 Agent 会增加状态、授权和 Eval 成本 |

桌面版允许场馆负责人选择 OpenAI、DeepSeek 或自定义 OpenAI 兼容服务，并独立填写模型名称与 API Key。OpenAI 使用 Responses API，DeepSeek 使用 Chat Completions API，自定义服务由用户选择协议。保存配置只代表连接验证成功，不得自动开启当前 Venue 的 AI 服务；选择非 OpenAI 服务时必须提示业务信息会发送给对应第三方。

### 12.2 Runner 约束

- 桌面版只有一个应用实例，使用 SQLite 短事务和单执行者；
- 服务端即使配置多个 API 进程，也以数据库条件更新领取 lease；
- Runner 每次领取、扫描和执行都绑定 organization_id／venue_id，按 Venue 限制并发和每轮工作量，避免一个场馆的积压饿死其他场馆；
- Runner 与 FastAPI lifespan 通过内部 Executor 接口解耦；首版在同一进程运行，未来只有出现 24×7 或明显吞吐需求时才把同一 Executor 移到独立进程，不改变 Case、Run、Tool 和 checkpoint 模型；
- 扫描、模型调用和业务写入不得长时间占用同一数据库事务；
- 审批等待不占用线程或进程；
- Runner 关闭时停止领取新任务，已运行步骤在安全 checkpoint 后退出；
- 应用未运行期间不承诺实时扫描，下次启动 catch-up；需要 24×7 定时时再评估独立 Worker。

## 13. 分阶段开发路线

### Phase 0 - 业务与安全前提

- 建立默认 Organization、Venue 所有权和服务端 RequestScope；把 Agent 将读取的业务聚合、AuditLog 和唯一约束迁移到可验证 Scope，消除 `select(Venue).limit(1)` 依赖；
- 建立 Organization／Venue 成员关系和 capability 安全回填；首版 UI 仍只选择一个活动 Venue；
- 建立轻量 OperationsPolicy、由场馆负责人确认的初始 policy_version 和变更审计；未配置规则保持禁用；
- 建立 CaseActivity 与 OperationEvent 的职责边界；
- 固定 OperationRun 单向产出 Snapshot、parent_run_id 重试和 case_id 可选的关联方式；
- 冻结当前关键业务口径和首批 detector／verifier 规则；
- 补齐 Agent 写路径所需的 capability；
- 统一整班补排的调用方事务与幂等恢复边界；
- 补齐该写路径的 AuditLog 和 request_id／trace_id 关联；
- 建立 feature flag、ModelClient 接口和脱敏策略；
- 修正经营报告原始利用率、营业时间外占用和数据质量口径；
- 建立两个 Organization、多 Venue 和 4／10／15 片场地的匿名化评测夹具；
- 不接模型即可完成 Scope、Policy 和规则测试。

**Exit**: 禁用模型时，现有业务回归全部通过；跨 Organization／Venue 读取和写入测试为 0 泄露；旧 policy_version 可重现；补排工具具备权限、版本、幂等和审计前提。

### Phase 1 - 确定性运营案件中心

- 实现 OperationCase、Run、Event 基础状态；
- 实现启动、15 分钟和手动扫描；
- 实现逾期未考勤、未结清应收、固定班／私教续费机会、待补排和首批对账 detector；
- 实现案件去重、重新打开、Verifier 和确定性每日简报；
- 实现日／周／月 OperationsReportSnapshot、期间／时点口径、可比窗口和异常规则；
- 前端提供案件列表、证据、业务跳转和时间线。

**Exit**: 不配置模型也能主动发现、持续跟踪和自动关闭确定性案件。

### Phase 2 - 只读 Agent 诊断与收入保障跟进

- 接入一个 ModelClient adapter；
- 实现结构化诊断／计划、引用和 Guardrail；
- 实现欠费／续费优先级、沟通草稿、CaseActivity 和 record_followup_outcome；
- 实现经营报告的结构化总结、异常解释、建议、数值引用和模型失败降级；
- 建立 Trace、用量、错误降级和离线 Eval。

**Exit**: Agent 只能读取受控证据，并在人员明确确认后创建 CaseActivity／对应 OperationEvent；资金、报名、课包、课时、排期和工资业务表在分析前后保持不变。

### Phase 3 - MVP 受控整班补排

- 实现版本化 resource_plan 候选时段生成和排序；MVP Policy 与现有命令仍限制原教练和原场地；
- 实现 ToolCall、Approval、lease、checkpoint 和恢复；
- 接入 schedule_cancelled_class_replacement；
- 实现 stale、冲突、重复执行、提交后崩溃和 Verifier 测试；
- 完成端到端审批闭环。

**Exit**: 满足第 14 节 MVP 验收，正式称为“智能运营系统 MVP”。

### Phase 4 - 对账扩展与使用反馈

- 根据真实异常补充确定性规则；
- 增加案件统计、平均处理时间和误报反馈；
- 评估确定性“原教练 + 其他合法场地”候选策略和排期碎片优化，只有业务服务先具备安全能力后才扩展 Tool 版本；
- 只有真实运行数据证明需要 24×7 调度、长任务或大量并发时，才评估独立 Worker、Redis 或更强工作流引擎。

## 14. MVP 验收标准

### 14.1 功能闭环

- 未结清应收、固定班／私教续费机会、逾期未考勤、待补排和一致性异常均可由扫描主动创建案件；
- 重复扫描不创建重复活动案件；
- 至少一条待补排案件完成“发现—计划—审批—执行—验证—关闭”；
- 欠费和续费案件支持至少两次结构化 CaseActivity；欠费在余额清零后自动关闭，续费只在真实续期／新课包事实出现或人员明确 dismissed 后结束；
- 对账案件只能通过规则重跑关闭，Agent 文本不能直接关闭。
- 可生成指定日、自然周和自然月报告，当前期间明确标记为进行中；
- 报告在模型关闭时仍包含完整确定性指标、对比和异常规则结果；
- 同一代码路径可在 4、10、15 片活动场地夹具下生成正确扫描、候选和报告，不需要改变 Runtime 架构；

### 14.2 正确性与安全

- 所有金额、课时、时间和状态与现有 Query／领域规则 100% 一致；
- 报告中的金额、数量、课时、比例和利用率 100% 来自 OperationsReportSnapshot；
- LLM 不能新增异常命中、改变阈值／severity 或输出未引用数值；
- Agent 分析和候选排序产生 0 条业务写入；
- 未审批、审批过期、审批 stale、权限不足或版本变化时产生 0 条补排写入；
- 同一 ToolCall 在重试、双击和进程恢复下最多产生一节补排课程；
- 业务写入后 Verifier 失败或结果不确定时不宣称成功，案件进入 escalated；
- 禁止工具和高风险写动作在运行时不可达。
- 任何跨 Organization／Venue 的证据读取、Tool 执行、模型上下文、Snapshot 或 Trace 关联均安全失败并产生 0 条数据泄露／副作用；
- Case、Run、ToolCall、Approval、CaseActivity 和 Snapshot 使用的 policy_version 可查询，历史结果不因 Policy 修改而变化；
- 原始场地利用率、展示利用率和营业时间外占用分开保存，超过 100% 时不静默截断原始指标。

### 14.3 可观测与恢复

- 100% Agent 写入可从 OperationEvent 追到 Approval、ToolCall、CaseActivity（适用时）、业务 AuditLog 和最终 Verifier；
- 进程在 waiting_approval、retry_scheduled 和业务提交后中断的恢复用例全部通过；
- 模型关闭、断网或超时不影响现有排期、考勤、财务、结算和报表；
- 新案件在应用持续运行时 15 分钟内可见；启动 catch-up 在 60 秒内完成当前规模扫描；
- 常用案件列表和证据页面在当前规模下 2 秒内显示确定性内容，模型生成可以异步后补。
- 当前规模下，日／周／月确定性报告在 3 秒内显示，智能总结可异步后补。
- 在 15 片场地标准夹具下，14 天补排候选在 3 秒内返回、确定性月报在 5 秒内显示、启动 catch-up 在 60 秒内完成；模型生成时间不计入确定性结果门槛。

### 14.4 Eval

- 第 11.3 节 CI 指标全部达到门槛；
- 提示注入、越权、跳过审批、任意 SQL／Shell／URL 和虚构事实测试均安全失败；
- 发布所用 prompt_version、toolset_version、verifier_version 和 model_profile 可追溯。

## 15. Functional Requirements

### 15.1 定位与边界

- **FR-001**: 系统 MUST 以 OperationCase 组织持续经营问题、以 OperationRun 组织报告和执行，不把一次聊天会话作为业务闭环。
- **FR-002**: 系统 MUST 在模型不可用时保持确定性扫描、案件、Verifier 和现有业务页面可用。
- **FR-003**: LLM MUST NOT 直接读取数据库、ORM、文件、Shell 或任意网络资源。
- **FR-004**: 所有 Agent Tool MUST 映射到受控应用层 Query 或 Command。
- **FR-005**: 金额、课时、时间、状态、冲突和关闭条件 MUST 由确定性程序产生和验证。

### 15.2 案件与扫描

- **FR-006**: 系统 MUST 支持启动补偿、周期和手动扫描。
- **FR-007**: Detector MUST 版本化并输出规范化 evidence 和 fingerprint。
- **FR-008**: 同一业务问题重复扫描 MUST NOT 创建重复活动案件。
- **FR-009**: 案件 MUST 保存首次／最近发现、下次检查、截止时间、状态和关闭依据。
- **FR-010**: resolved 或 dismissed 案件再次异常时 MUST 保留旧历史并记录新 occurrence。
- **FR-010a**: 运营中心默认工作队列 MUST 排除 resolved 和 dismissed；终态案件 MUST 在独立历史入口保持只读可查询，详情默认展示业务摘要而非内部记录 ID，系统运行记录仅向具备案件管理权限的用户折叠展示。
- **FR-010b**: 活动案件 MUST 优先在案件页侧边操作窗口完成考勤、单笔收款、固定班续期、私教课包续费、课程补排和数据核对；窗口 MUST 明确当前对象、异常依据与完成标准。完整业务页面只作为补充资料或未支持修正流程的兜底入口，业务写入后 MUST 可立即触发确定性核对。
- **FR-011**: 系统 MUST 提供业务链接和原始证据，不要求用户相信无来源的模型结论。

### 15.3 场景

- **FR-012**: 系统 MUST 识别达到账龄阈值且 outstanding_amount 大于零的应收。
- **FR-013**: 欠费 Agent MUST 引用真实应收汇总并在联系人不足时 abstain。
- **FR-014**: 欠费跟进 MUST NOT 自动登记收款、退款或修改应收。
- **FR-015**: 系统 MUST 以结构化 CaseActivity 记录人工跟进结果、操作人和下次检查时间。
- **FR-016**: 欠费案件 MUST 由 receivable_summary 的确定性结果关闭。
- **FR-017**: 系统 MUST 识别 cancelled + replacement_decision=pending 的课程。
- **FR-018**: 补排候选 MUST 由 policy_version、营业时间、时间粒度、resource_plan 和冲突规则确定性生成；MVP Policy MUST 只使用原资源。
- **FR-019**: 候选 MUST 明确声明未验证固定班学员可用性。
- **FR-020**: Agent MUST 只能排序合法候选，不能创造未校验候选。
- **FR-021**: 补排写入 MUST 经过有效审批、权限、版本和影响重校验。
- **FR-022**: 补排 Tool MUST 复用现有整班补排业务规则。
- **FR-023**: 补排案件 MUST 由补排关系、排期和资源 Verifier 关闭。
- **FR-024**: 系统 MUST 提供第 7.5 节首批一致性规则。
- **FR-025**: 对账异常 MUST NOT 由 LLM 判断通过或自动修复。
- **FR-026**: 历史 MakeupRecord MUST NOT 被解释为当前个人补课能力。

### 15.4 经营报告

- **FR-054**: 系统 MUST 支持按指定业务日、自然周和自然月生成经营报告。
- **FR-055**: 报告期间 MUST 使用当前 Scope 的 Venue.timezone；当前期间 MUST 标记 in_progress 并只统计到 generated_at。
- **FR-056**: 当前进行中期间 MUST 使用相同已过时长的确定性对比窗口；未来期间 MUST 被拒绝。
- **FR-057**: 报告中的金额、数量、课时、比例、利用率、对比和异常 MUST 由确定性程序计算。
- **FR-058**: 报告 MUST 区分 period 指标和 as_of generated_at 时点余额。
- **FR-059**: Snapshot MUST 保存 metric_version、anomaly_rule_version、source_refs、evidence_hash 和 generated_at。
- **FR-060**: 相同期间重新生成 MUST 创建新 Snapshot，不覆盖历史结果。
- **FR-061**: LLM MUST 只消费脱敏后的 Snapshot，并只负责总结、解释、假设和建议。
- **FR-062**: LLM 输出中的所有数值事实 MUST 引用 metric_ref 并通过确定性渲染或校验。
- **FR-063**: 异常提示 MUST 来自版本化规则；LLM MUST NOT 新增命中、修改阈值或修改 severity 基线。
- **FR-064**: 报告 MUST 分隔确定性事实、异常、LLM 解释、运营建议和限制。
- **FR-065**: 数据不足、零基准或不可重建历史时点时 MUST 明确降级，不得生成虚假比例或趋势。
- **FR-066**: 模型失败时 Snapshot、分项、对比和异常 MUST 仍可查看。
- **FR-067**: 报告生成和建议 MUST 对现有业务事实产生 0 条写入。

### 15.5 Runtime

- **FR-027**: Run MUST 持久化状态、checkpoint、预算、版本和 lease。
- **FR-028**: Runtime MUST 支持 waiting_approval、waiting_human、retry_scheduled 和 restart recovery。
- **FR-029**: Runtime MUST 对模型、Tool、step、时长和写入次数设置上限。
- **FR-030**: Runtime MUST 在无进展、超限、未知结果或策略冲突时停止并升级。
- **FR-031**: 模型输出 MUST 通过严格结构化 Schema 校验。
- **FR-032**: Case 和 Run 状态转换 MUST 由确定性状态机执行。
- **FR-033**: 写 Tool 中断恢复 MUST 先执行 outcome reconciliation。

### 15.6 Tool、权限与审批

- **FR-034**: Registry MUST 固定 Tool Schema、版本、风险、capability、审批、幂等和脱敏策略。
- **FR-035**: 模型 MUST NOT 修改 Tool 风险或审批政策。
- **FR-036**: Tool Handler MUST 在服务端校验当前用户 capability。
- **FR-037**: medium 或 high 写入 MUST 绑定不可变 Approval。
- **FR-038**: 审批 MUST 在输入、影响、版本、权限或有效期变化时 stale。
- **FR-039**: 修改审批参数 MUST 创建新 ToolCall 和 Approval。
- **FR-040**: MVP Registry MUST NOT 包含资金、权益、考勤、取消、费用、工资或作废写工具。
- **FR-041**: 所有副作用 Tool MUST 具备可查询幂等结果。

### 15.7 安全与隐私

- **FR-042**: 模型上下文 MUST 默认排除电话、微信、凭证地址、Cookie、密钥和附件正文。
- **FR-043**: Tool 输出中的自由文本 MUST 作为不可信数据处理。
- **FR-044**: 系统 MUST 拒绝任意 SQL、Shell、文件、URL、代码执行和动态插件工具。
- **FR-045**: Agent 业务写入的责任人 MUST 是实际批准／执行用户。
- **FR-046**: 模型、Tool 和审批错误 MUST 以可理解状态展示，不得静默部分执行。

### 15.8 Trace、Audit 与 Eval

- **FR-047**: 所有运行节点 MUST 共享 trace_id 并记录版本、耗时、状态和脱敏摘要。
- **FR-048**: Agent Trace MUST 与现有业务 AuditLog 关联但不得替代。
- **FR-049**: 系统 MUST 记录模型用量和错误，不记录秘密或不必要原文。
- **FR-050**: 项目 MUST 建立匿名化、版本化的固定中文评测集。
- **FR-051**: CI MUST 覆盖 detector、verifier、Tool contract、Runtime recovery、approval、injection 和 end-to-end。
- **FR-052**: 真实模型回归 MUST 与离线确定性 CI 分离。
- **FR-053**: 任何安全指标回归 MUST 阻止发布。

### 15.9 商业化作用域、策略与持续运营

- **FR-068**: 系统 MUST 建立 Organization → Venue 所有权边界；第一版可以只启用一个 Venue，但不得省略 Scope。
- **FR-069**: 每个认证请求 MUST 解析不可变 organization_id、venue_id、user_id 和 capabilities；LLM 与 Tool 输入 MUST NOT 覆盖该 Scope。
- **FR-070**: Agent 使用的业务 Query／Command MUST 要求显式 Scope，MUST NOT 通过读取第一条 Venue 推断场馆。
- **FR-071**: OperationCase、OperationRun、OperationEvent、OperationToolCall、OperationApproval、CaseActivity、OperationsReportSnapshot 和相关审计 MUST 可直接验证 Organization／Venue Scope。
- **FR-072**: 跨 Organization／Venue 的业务 ID、Tool、审批、Snapshot、Trace 和模型上下文请求 MUST 安全失败并产生 0 条泄露或副作用。
- **FR-073**: 用户 capability MUST 来源于服务端 Organization／Venue 成员关系；现有用户迁移 MUST 关联默认 Scope 并完成人工权限复核，在复核前 MUST 禁用 Agent 写 Tool。
- **FR-074**: 系统 MUST 提供按 Venue 生效、版本化的 OperationsPolicy，覆盖跟进、续费、考勤、补排、报告异常和案件 SLA 的首批参数。
- **FR-075**: Case、Run、ToolCall、Approval 和 Snapshot MUST 冻结实际使用的 policy_version；Policy 修改 MUST NOT 追溯改变历史结论。
- **FR-076**: CaseActivity MUST 区分 channel、outcome_code、summary、happened_at、next_check_at 和 operated_by，且 MUST NOT 复制不必要的完整联系方式。
- **FR-077**: OperationEvent MUST 记录运行 Trace，CaseActivity MUST 记录人工运营事实，二者 MUST NOT 互相替代。
- **FR-078**: 系统 MUST 确定性识别进入 Policy 窗口的固定班结束和私教课包到期／余量不足机会。
- **FR-079**: 固定班续费案件 MUST 由新增 ClassSession、对应续期流水／审计等真实业务事实或人工 dismissed 结束；私教续费案件 MUST 由真实新课包或人工 dismissed 结束。
- **FR-080**: Agent MUST NOT 自动续期固定班、创建私教课包、新增应收、承诺价格或修改课时权益。
- **FR-081**: OperationsReportSnapshot MUST 通过 run_id 单向引用生成 Run；Narrative 重试 MUST 使用 parent_run_id 和不可变 Snapshot 引用，MUST NOT 建立 Run／Snapshot 循环依赖。
- **FR-082**: OperationToolCall 和 OperationApproval 的 case_id MUST 可选，并从 Run 继承 Scope；无 Case 的报告 Run MUST 保持可追踪和可授权。
- **FR-083**: 补排候选 MUST 使用版本化 resource_plan；未来增加其他合法场地时 MUST 先由确定性业务服务支持并发布新 Tool 版本。
- **FR-084**: 场地报告 MUST 区分经营使用、基础营业时长、CourtBlock 不可售时长、扣除不可售后的可营业时长、原始利用率、展示利用率和营业时间外占用；有效 CourtBlock MUST 从对应场地分母按重叠时长并集扣除且 MUST NOT 计入经营使用，原始利用率 MUST NOT 被静默截断。
- **FR-085**: CI MUST 覆盖两个 Organization、多 Venue 和 4／10／15 片场地夹具，且跨 Scope 泄露与副作用必须为 0。
- **FR-086**: 场地归属、占用、候选和利用率 MUST 以当前 Scope 的 Venue、Court 和 ScheduleAllocation 为事实，Agent 报告与 Tool MUST NOT 依赖 court_ids_csv 或全局场地 code 判断资源归属。
- **FR-087**: 外部模型能力 MUST 按 Venue 默认关闭并由具备 operations.model.manage 的负责人明确启用；配置模型凭据 MUST NOT 自动启用任何 Venue，关闭后新 Run MUST 只执行确定性路径。
- **FR-088**: 系统 MUST 按服务端角色包和 capability 投影财务字段；前台／运营只能读取当前获授权跟进案件必要的单笔欠费信息，MUST NOT 通过报告、Tool、模型上下文、Narrative、Trace 或业务链接读取全馆利润、工资和结算数据。
- **FR-089**: Detector MUST 按版本化 case_type registry 为案件设置 queue_key 和 required_capability，MUST NOT 自动选择具体员工；系统 MUST 支持合格人员认领及具备 operations.case.assign 的负责人分配／改派，并在 assignee 失效时审计后退回队列且保持 SLA 跟踪。

## 16. Key Entities

- **OperationCase**: 持续存在的经营问题、责任队列、可选 assignee 和关闭状态。
- **Organization／Venue／Membership**: 经营主体、场馆和服务端用户作用域／能力来源；Venue 保存服务端控制、默认关闭的模型能力启用状态，首版只启用一个活动 Venue。
- **OperationsPolicy**: 按 Venue 生效、版本化的确定性运营阈值和流程配置。
- **CaseActivity**: 欠费、续费等案件中的结构化人工跟进业务事实。
- **OperationRun**: 一次可恢复的分析／计划／执行尝试。
- **OperationEvent**: 追加型运行与案件 Trace。
- **OperationToolCall**: 一次受控工具提议、执行和幂等结果。
- **OperationApproval**: 绑定不可变影响快照的人工授权。
- **OperationsReportSnapshot**: 指定日／周／月的不可变确定性指标、对比、异常和智能解读快照。
- **Existing Business Entities**: ClassSession、ScheduleEntry、ScheduleAllocation、Receivable、Payment、Refund、LessonUnitLedger、AttendanceRecord、PrivateLesson、CoachFee、PayrollSettlement、Expense 和 AuditLog 继续是唯一业务事实来源。

## 17. Success Criteria

- **SC-001**: 在标准测试数据中，六类 MVP detector 的预期案件发现率和去重正确率均为 100%。
- **SC-002**: 100% 金额、课时、状态、日期和业务引用与确定性 Tool 输出一致。
- **SC-003**: 至少 95% 标准 Agent 场景一次生成可通过 Schema 的安全计划；其余场景安全停止。
- **SC-004**: 所有未审批、越权、stale 或过期写入尝试产生 0 条业务副作用。
- **SC-005**: 补排闭环在不包含外部人员沟通时间时可由管理人员在 5 分钟内完成。
- **SC-006**: 双击、重试和进程恢复测试中，同一批准动作最多产生一次业务副作用。
- **SC-007**: 100% Agent 业务写入可追溯到案件、运行、Tool、审批、业务审计和 Verifier。
- **SC-008**: 应用持续运行时，新异常在 15 分钟内出现在案件中心。
- **SC-009**: 模型完全禁用时，现有业务回归通过且确定性案件中心仍可使用。
- **SC-010**: 注入、SQL、Shell、任意 URL、禁用 Tool、越权和审批绕过评测的成功攻击数为 0。
- **SC-011**: 日、周、月报告中 100% 金额、数量、课时、比例和利用率可追溯到确定性 metric_ref。
- **SC-012**: 固定报告评测集中，期间边界、可比窗口、指标和异常规则结果正确率为 100%。
- **SC-013**: LLM 报告输出中的未引用数值、模型自行命中的异常和被当作事实的无证据根因均为 0。
- **SC-014**: 模型不可用时，100% 测试报告仍能显示完整确定性快照和异常规则结果。
- **SC-015**: 管理人员可在 3 分钟内选择期间、生成报告并定位最重要的三个指标或异常。
- **SC-016**: 两个 Organization、多 Venue 的隔离评测中，跨 Scope 业务读取、Tool 写入、模型上下文泄露和 Trace 错链成功数均为 0。
- **SC-017**: 4、10、15 片活动场地夹具中的扫描、补排候选、报告指标和资源引用正确率均为 100%。
- **SC-018**: 同一 policy_version 和业务夹具重复运行时，Detector、候选、异常和 Verifier 结果可重现率为 100%。
- **SC-019**: 100% 欠费和续费人工跟进可追溯到 CaseActivity、操作人、结构化结果和下次检查时间，且“已联系”不会错误关闭案件。
- **SC-020**: 所有超过 100% 或包含营业时间外占用的利用率夹具均保留原始值并产生确定性数据质量提示。
- **SC-021**: 在 15 片场地标准夹具下，14 天补排候选、确定性月报和启动补偿扫描分别在 3 秒、5 秒和 60 秒内完成，且不改变总体 Runtime 架构。
- **SC-022**: 新建或迁移 Venue 在负责人明确启用前产生 0 次外部模型调用；关闭模型后 100% 新 Run 使用确定性路径且扫描、案件、报告和 Verifier 继续可用。
- **SC-023**: 固定角色隔离评测中，前台／运营可正确读取其欠费跟进案件的必要单笔金额，同时通过报告、Tool、模型上下文、Narrative、Trace 和业务链接获取全馆利润、工资或结算信息的成功次数为 0。
- **SC-024**: 包含单个、重叠、营业时间外和与经营排期异常重叠 CourtBlock 的固定夹具中，不可售时长并集、可营业时长、经营使用时长和补排冲突判定正确率均为 100%，CourtBlock 被计作经营使用的次数为 0。
- **SC-025**: 固定队列评测中，100% 新案件进入正确 queue_key 且 required_capability 正确；跨 Scope、无权限或失效成员成功认领／被分配次数为 0，失效 assignee 的案件全部审计后回到队列并继续 SLA 跟踪。

## 18. 明确暂不实现

- 通用聊天机器人或全站自然语言控制；
- 多 Agent、Agent 群体协作或可视化工作流编辑器；
- AgentDefinition／WorkflowDefinition 的数据库管理与在线发布；
- LangGraph、Temporal、Celery、Redis、Kafka、Kubernetes 或独立 AI Gateway；
- MCP、任意第三方插件、任意 HTTP、SQL、Shell 或文件工具；
- 向量数据库、结构化业务数据 RAG、OCR 和凭证识别；
- 微信、短信、邮件自动发送及送达跟踪；
- 定时自动发送经营报告、外部分享链接、PDF／Excel 导出和管理层邮件分发；
- 自动登记收款、退款、支出、考勤、课时、权益、取消、费用、工资结算或作废；
- 自动修复对账异常；
- 个人补课资格或跨班个人补课；
- 自动续费、自动创建新增应收或自动调价；
- MVP 执行更换补排教练／场地、批量补排和学员可用性自动协调；候选 Schema 的 resource_plan 版本扩展点除外；
- 24×7 独立 Worker 和应用关闭期间的实时扫描；
- 多场馆切换 UI、集团跨场馆汇总、集中 SaaS 租户开通／计费／运维、跨机构共享数据、复杂组织权限和强制双人审批；Organization／Venue 基础作用域和隔离不属于本排除项；
- 制度文档知识库或长期原始 Prompt／Response 存档。

## 19. Assumptions

- 第一版仍服务一个 Organization 下的一个活动 Venue 和少量内部管理人员；数据、权限、运营策略和 Agent Runtime 从第一天显式保留 Organization／Venue Scope。
- 业务时区由 Venue.timezone 决定，默认 Asia/Shanghai。
- 当前 SystemUser 都是内部管理人员但没有 owner／admin 角色；实施 Organization／Venue Membership 后，现有 active 用户先进入默认 Scope 的待复核成员清单，场馆负责人确认 capability 前 Agent 写 Tool 保持禁用。
- 未结清应收的“账龄”以 Receivable.created_at 为代理，不等同合同到期日；UI 必须使用“达到跟进账龄”而非法律意义“逾期”。
- 固定班当前没有学员可用性／偏好模型，候选时段仅证明教练和场地资源可行。
- 外部沟通仍发生在微信或电话，系统只保存人员主动录入的结果。
- 每个球馆的欠费账龄、续费窗口、考勤宽限期、补排限制和异常阈值可能不同，由版本化 OperationsPolicy 表达；第一版不提供任意脚本或可视化规则编辑器。
- 当前现有补排 Command 只会复用原课程资源；其他场地 resource_plan 只是长期 Schema 边界，实施前必须先扩展并测试确定性业务服务。
- 经营报告沿用现有收付实现制口径；当前欠费和当前全部待结费用是 generated_at 时点余额，不伪装为历史期间发生额。
- 模型 provider、网络和数据保留政策在实施计划中选择，但不能改变本 Spec 的脱敏、Tool、审批和降级边界。
- specs/001 中的 Future Agent 草案由本 Spec 在智能运营范围内取代；现有业务 Spec 及其验收标准仍然有效。
