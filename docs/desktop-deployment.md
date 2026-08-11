# ShuttleCube 单机桌面版

## 运行结构

Windows 桌面版使用 pywebview 展示 React 页面，并在应用进程内启动仅监听 `127.0.0.1` 随机端口的 FastAPI 服务。Python、后端依赖、前端静态资源和数据库迁移均包含在安装包内，最终用户不需要安装 Python、Node.js、PostgreSQL 或 Docker。

桌面版不会监听局域网地址，也不依赖外部服务器。浏览器开发模式和 Docker Compose 服务器模式继续保留。

## 数据目录

默认数据目录为：

```text
%LOCALAPPDATA%\ShuttleCube\Data
├── manifest.json
├── database\shuttlecube.db
├── attachments\
├── backups\
└── settings\
```

- 数据目录与安装目录分离，应用升级和默认卸载不会删除业务数据。
- 首次桌面启动时，如开发版旧数据库存在且新目录为空，会通过 SQLite 在线备份 API 复制旧数据。
- 启动时自动执行 Alembic 数据库升级。
- 安装密钥、进程锁和待恢复数据保存在 `settings`，不会进入迁移包。

## 首次启动

全新数据库会显示初始化向导，要求创建场馆、初始场地和首个管理员。初始化接口仅在系统不存在任何用户时可执行，完成后不可再次调用。

## 数据迁移

“场馆设置 → 本机数据管理”提供：

- 导出迁移文件夹：使用 SQLite 一致性快照复制数据库，复制附件，清除会话，并生成 SHA-256 校验清单。
- 从迁移文件夹恢复：验证格式版本、数据库版本、完整性与每个文件的校验值，然后暂存数据。
- 重启恢复：启动前先备份当前数据，再替换数据库和附件，随后执行数据库升级。

迁移采用完整替换，不合并两台设备分别产生的数据。迁移后所有账号需要重新登录。

## 构建

首次构建需要 Windows、Python 3.14、Node.js、uv 和 Inno Setup 6：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-desktop.ps1 -Installer
```

输出位置：

```text
dist\desktop\ShuttleCube\ShuttleCube.exe
dist\installer\ShuttleCube-Setup-0.1.0-win-x64.exe
```

不传 `-Installer` 时只生成可执行程序目录。

构建脚本会在临时数据目录中自动启动新生成的桌面程序，验证数据库迁移、健康检查、前端资源和本地数据库创建均成功后再继续生成安装包；临时数据在检查结束后删除。

## 发布前检查

1. 在干净的 Windows 10/11 用户环境安装。
2. 验证首次启动初始化、登录、排期创建和关闭重启。
3. 导出迁移文件夹，在另一个空数据目录中恢复并核对数据与附件。
4. 检查未安装 WebView2 的设备能获得明确提示；正式发布时可增加 Evergreen Bootstrapper。
5. 正式签名安装包和主程序，降低 Windows SmartScreen 警告。
