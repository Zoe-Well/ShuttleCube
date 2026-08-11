# Quickstart Validation Guide: 羽毛球经营管理与 AI 扩展占位

本指南用于在实现完成后验证第一版核心闭环。它不是部署手册，也不包含业务实现代码。实体和约束见 [data-model.md](./data-model.md)，接口输入输出见 [contracts/openapi.yaml](./contracts/openapi.yaml)。

## Prerequisites

- Python 3.14 与 `uv`
- Node.js Active LTS、Corepack 与 `pnpm`
- PostgreSQL 17 或更高版本，或支持 Docker Compose 的容器环境
- 私有 S3 兼容对象存储（本地 Compose 可使用 MinIO）
- 支持 Playwright 的当前桌面浏览器
- 一个空的测试数据库和测试对象存储 bucket；不需要模型凭证

## Local Validation Setup

在项目根目录执行：

```powershell
docker compose up -d postgres object-storage
uv sync --project backend --all-groups
corepack enable
pnpm install --frozen-lockfile
$env:SHUTTLECUBE_DATABASE_URL = "postgresql+psycopg://shuttlecube:shuttlecube@localhost:5432/shuttlecube_test"
$env:SHUTTLECUBE_SECRET_KEY = "replace-with-a-long-local-test-secret"
$env:SHUTTLECUBE_S3_ENDPOINT = "http://localhost:9000"
$env:SHUTTLECUBE_S3_BUCKET = "shuttlecube-test"
$env:SHUTTLECUBE_S3_ACCESS_KEY = "local-test-access"
$env:SHUTTLECUBE_S3_SECRET_KEY = "local-test-secret"
$env:SHUTTLECUBE_TIMEZONE = "Asia/Shanghai"
uv run --project backend alembic upgrade head
uv run --project backend shuttlecube bootstrap-admin --username owner1
uv run --project backend shuttlecube bootstrap-admin --username owner2
pnpm api:generate
uv run --project backend uvicorn shuttlecube.app:create_app --factory --reload --port 8000
```

在第二个终端启动 React 管理端：

```powershell
pnpm --dir frontend dev
```

预期结果：

- FastAPI 在 `http://localhost:8000` 启动且健康检查通过。
- React 管理端在 Vite 开发地址启动，并通过开发代理访问 `/api/v1`，浏览器不发生跨域请求。
- 两个管理员账号可分别登录，审计中能区分操作人。
- 初始机构时区为 `Asia/Shanghai`，包含四片可用场地。
- 未登录访问业务页面或凭证均被拒绝。
- OpenAPI 生成的 TypeScript 客户端与当前契约一致，生成目录没有手工修改。
- 对象存储 bucket 为私有，付款凭证只能通过已鉴权的下载接口访问。
- AI 助手入口显示“规划中”，没有模型、队列、Worker、AI 环境变量或外部请求。

> 以上命令是计划中的目标运行接口；在实现阶段必须让它们真实可运行，或同步修订本指南与项目入口。

## Automated Quality Gates

```powershell
uv run --project backend ruff check backend
uv run --project backend mypy backend/src
uv run --project backend pytest backend/tests/unit
uv run --project backend pytest backend/tests/integration
uv run --project backend pytest backend/tests/contract
pnpm api:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm exec playwright install chromium
pnpm test:e2e
```

全部命令必须返回成功。数据库集成测试不得以 SQLite 替代 PostgreSQL，前端类型检查必须使用由 OpenAPI 生成的当前业务客户端；标为 future draft 的 Agent 路径不得生成或实现。

## Scenario 1: Unified Scheduling and Conflict Rejection

1. 以 `owner1` 登录，确认四片场地和默认营业时间。
2. 创建一个每周六 10:00—12:00、12 节、占用两片场地和一名教练的固定班。
3. 打开周排期，确认 12 个课程实例均显示且默认资源正确。
4. 在其中一次课程的相同时段，为同一场地创建散客预订。
5. 再分别尝试为同一教练、同一学员创建重叠私教。
6. 取消原课程并创建补排课程，再重试原时段订场。

**Expected outcomes**:

- 固定班、私教、订场、活动与停用记录在统一排期中可区分。
- 三种冲突均在保存前拒绝，并显示资源名称和重叠时间。
- 冲突写入失败后不产生任何部分资源占用。
- 取消保留原课程历史且释放资源；新订场通过其余检查后可保存。

## Scenario 2: Fixed Class, Attendance and Lesson Ledger

1. 创建学员与两个关联家长，再为学员创建上述固定班的中途报名。
2. 核对建议应收等于剩余课次乘以单价；修改实际应收并填写原因。
3. 打开一次已结束课程的考勤，保留 10 名学员默认正常出勤，将 1 人改为请假且不扣课，将 1 人改为缺席且扣课。
4. 完成考勤并查看每名学员的课时流水。
5. 为原班新增续期课程但不给请假学员重复增加课时或应收，确认其余额仍可用于续期课程；再验证原班不续时可以整体转移剩余权益。
6. 使用相同幂等键重复提交考勤完成命令。

**Expected outcomes**:

- 中途报名金额建议正确，人工调整留有原因和审计。
- 正常出勤和缺席学员各扣一节，请假学员按本次决定处理。
- 余额可由流水逐条复算，不能直接无记录修改。
- 请假未扣的余额不会生成独立补课单；续期只新增课程时余额和应收不变，整体转移不重复生成收入或应收。
- 重复提交返回原业务结果，不会二次扣课或二次生成教练费用。

## Scenario 3: Private Lesson, Venue Booking and Event

1. 为学员购买 10 节、绑定指定教练的私教课包。
2. 创建一节 90 分钟私教，选择教练和场地，完成后核对课包与教练费用。
3. 为散客创建连续 2 小时、两片场地的预订，核对价格规则建议金额，修改实际金额并登记原因。
4. 保持预订未付款但状态为已预订，尝试让临时活动使用相同场地。
5. 创建一个不记录参与人的包场活动，再创建一个需要参与人考勤的体验课。

**Expected outcomes**:

- 私教完成只扣一节课包并生成一条有效教练费用。
- 订场建议金额按时段和场地数量计算，人工调整可追溯。
- 未付款但确认的订场仍阻止资源重叠。
- 两类活动均可保存，只有选择参与人和考勤的活动要求相关资料。

## Scenario 4: Payments, Refunds and Attachments

1. 对固定班报名分两次登记收款，并分别核对累计实收、欠费和付款状态。
2. 上传一张图片凭证；退出登录后直接访问凭证地址。
3. 对该报名发起部分退款，填写实际退款、原因及需扣回课时。
4. 尝试退款超过可退余额，并使用同一幂等键重复提交合法退款。
5. 删除凭证，再检查资金记录和审计。

**Expected outcomes**:

- 两笔收款保持独立，应收汇总正确。
- 未登录不能访问凭证；凭证不是登记收款的必填项。
- 退款与原业务/收款、报名和课时流水关联，欠费及状态同步更新。
- 超额退款拒绝；重复请求不产生第二笔退款。
- 删除凭证不删除资金事实，并留下操作日志。

## Scenario 5: Coach Payroll

1. 完成固定班、私教和临时活动各一次，取消另一次已排业务。
2. 按教练和时间范围查询待结算费用。
3. 调整实际结算金额并填写原因，然后确认支付。
4. 以 `owner2` 同时尝试结算相同费用。

**Expected outcomes**:

- 仅已完成业务产生有效费用，取消业务不计入。
- 结算一次创建结算记录、锁定明细并生成一笔工资支出。
- 第二个并发结算被拒绝，不会重复支付。
- 结算人、时间、调整原因和支出均可追溯。

## Scenario 6: Dashboard, Reporting and Audit

1. 准备当日固定班、私教、订场、活动、待考勤、欠费和待结算数据。
2. 查看工作台与本月经营摘要。
3. 查看自定义期间收入、支出、利润、退款、欠费、教练费用和场地使用率。
4. 以两个账号分别修改排期、课时、金额和结算，再查询审计记录。

**Expected outcomes**:

- 工作台只显示摘要和快捷入口，全部待办数量与明细一致。
- 经营统计遵循收付实现口径，应收不直接计入收入。
- 退款、工资和日常费用只计入一次资金流出。
- 每项关键变更均显示正确操作人、时间、前后摘要和原因。

## Scenario 7: AI Extension Placeholder

1. 不配置任何模型密钥、Redis、Worker 或外部 AI 服务，正常启动完整系统。
2. 以 `owner1` 登录，在主导航或工作台打开 AI 助手入口。
3. 确认页面显示“规划中”，并说明未来可能支持定时提醒、自动任务和自然语言业务控制。
4. 使用浏览器网络面板点击并浏览占位页面，再返回排期、财务和工作台继续操作。

**Expected outcomes**:

- 占位入口与用户已确认的 shadcn/ui 页面风格一致，不改变现有导航与业务流程。
- 页面明确表示当前不可用，不提供可误操作的输入框、运行按钮或审批控件。
- 浏览过程中不存在模型、Agent、工具或外部网络请求，也不产生任何业务写入。
- 关闭或隐藏占位功能配置后，其余全部业务页面仍可使用。

## Performance and Concurrency Validation

准备至少 5,000 名联系人、250,000 条资源占用和 1,000,000 条流水/审计记录后执行：

- 100 次常用列表和工作台查询，至少 95 次在 2 秒内呈现可用结果。
- 100 次不同资源的排期保存，冲突反馈均在 2 秒内返回。
- 两个并发事务同时预订同一场地时，必须恰好一个成功、一个得到结构化冲突响应。
- 两个并发事务同时扣减同一课包或结算同一费用时，不得出现重复扣减、负余额或重复结算。

## Exit Criteria

- 七条场景全部通过。
- [spec.md](./spec.md) 中 SC-001 至 SC-011、SC-013 至 SC-015 可在测试环境验证；SC-012 作为上线后经营指标跟踪。
- [contracts/openapi.yaml](./contracts/openapi.yaml) 通过 OpenAPI 3.1 校验，已实现接口与契约一致。
- 课时、资金、教练费用、排期和审计均可从有效事实记录复核。
- 没有未解决的排期并发、超额退款、重复结算或凭证越权缺陷；AI 占位没有外部请求或业务副作用。
