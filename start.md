# 启动项目

在项目根目录打开两个 PowerShell 窗口。

后端（启动前会自动执行尚未应用的数据库迁移，迁移失败时不会继续启动）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1
```

前端：

```powershell
pnpm.cmd --dir frontend dev --port 5174
```

如需手动启动后端，必须先在 `backend` 目录执行：

```powershell
uv run alembic upgrade head
uv run uvicorn shuttlecube.app:create_app --factory --reload --port 8001
```

首次启用智能运营时，先完成数据库迁移，再在 `backend` 目录将现有负责人复核为当前场馆的首位运营负责人：

```powershell
uv run shuttlecube bootstrap-operations-owner --username <登录用户名>
```

该命令只允许初始化首位负责人，并自动启用确定性运营能力；模型和写工具仍保持关闭。负责人登录后可在“智能运营 → 运行设置”中受控调整场馆开关，并在“运营规则”中创建和激活规则版本。
