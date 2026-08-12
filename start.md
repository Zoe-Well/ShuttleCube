# 启动项目

## 浏览器开发模式

下面的方式是在当前电脑上分别启动开发用后端和前端，并通过浏览器访问。它不是已经打包好的桌面版，也不是必须部署到远程服务器；开发时前后端都运行在本机即可。

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

## 桌面版开发测试模式（无需打包）

需要测试 Windows 桌面窗口、首次启动向导、本机数据库、数据迁移或桌面版 API Key 加密存储时，可以直接从源码启动桌面版，无需先生成安装包。

首次运行或依赖发生变化时，在项目根目录执行：

```powershell
pnpm.cmd install
uv sync --project backend --extra desktop
```

启动前先构建桌面版使用的前端静态资源：

```powershell
pnpm.cmd --dir frontend build
```

建议为开发测试指定独立数据目录，避免与已经安装的正式桌面版共用业务数据。以下环境变量只影响当前 PowerShell 窗口：

```powershell
$env:SHUTTLECUBE_DATA_DIR = Join-Path (Get-Location) ".desktop-dev-data"
uv run --project backend shuttlecube-desktop
```

启动后会自动完成以下工作：

- 在桌面窗口中打开 React 页面，不需要另外启动前端开发服务器；
- 在应用内部启动仅监听 `127.0.0.1` 随机端口的 FastAPI 后端；
- 创建或打开独立的 SQLite 数据库并自动执行数据库迁移；
- 全新数据目录首次启动时显示场馆和管理员初始化向导。

关闭桌面窗口后，本地后端会一并停止。再次测试时重新执行前端构建和桌面启动命令即可；如果只修改了后端代码，可以直接重新启动桌面版。

运行源码桌面版需要 Windows、WebView2、Node.js/pnpm、Python 3.14 和 uv。给普通使用者交付时仍应使用 `scripts/build-desktop.ps1 -Installer` 生成安装包，最终用户不需要安装这些开发工具。
