# ShuttleCube

羽毛球馆排期与运营管理系统，提供 React 管理界面、FastAPI 业务后端，以及 Windows 单机桌面运行模式。

## Windows 单机桌面版

桌面版不需要外部服务器，会把 React 前端、FastAPI 本地后端和 SQLite 一起安装到用户电脑。数据默认保存在 `%LOCALAPPDATA%\ShuttleCube\Data`，可在场馆设置中导出或恢复完整迁移文件夹。

构建和数据迁移说明见 [docs/desktop-deployment.md](docs/desktop-deployment.md)。
