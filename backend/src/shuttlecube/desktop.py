from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path
from secrets import token_urlsafe
from types import TracebackType
from typing import BinaryIO

from shuttlecube.config import DEFAULT_DATABASE_PATH
from shuttlecube.infrastructure.database.migrations import run_migrations
from shuttlecube.infrastructure.desktop.paths import (
    DesktopDataPaths,
    default_desktop_data_root,
    migrate_legacy_database,
    sqlite_url,
)
from shuttlecube.infrastructure.desktop.transfer import apply_pending_import


def _resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(str(bundled))
    return Path(__file__).resolve().parents[3]


def _frontend_root(resource_root: Path) -> Path:
    bundled = resource_root / "frontend_dist"
    if bundled.is_dir():
        return bundled
    return resource_root / "frontend" / "dist"


def _backend_root(resource_root: Path) -> Path:
    bundled = resource_root / "backend_resources"
    if bundled.is_dir():
        return bundled
    return resource_root / "backend"


class SingleInstance:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stream: BinaryIO | None = None

    def __enter__(self) -> SingleInstance:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                flags = fcntl.LOCK_EX | fcntl.LOCK_NB  # type: ignore[attr-defined]
                fcntl.flock(stream.fileno(), flags)  # type: ignore[attr-defined]
        except OSError as exc:
            stream.close()
            raise RuntimeError("ShuttleCube 已经在运行") from exc
        self.stream = stream
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.stream is not None:
            self.stream.close()


def _installation_secret(paths: DesktopDataPaths) -> str:
    target = paths.settings / "secret-key"
    if target.is_file():
        return target.read_text(encoding="utf-8").strip()
    secret = token_urlsafe(48)
    target.write_text(secret, encoding="utf-8")
    return secret


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


class DesktopBridge:
    def __init__(self) -> None:
        self.restart_requested = False

    @staticmethod
    def _choose_folder() -> str | None:
        import webview

        window = webview.windows[0]
        dialog_type = getattr(webview, "FOLDER_DIALOG", None)
        if dialog_type is None:
            dialog_type = webview.FileDialog.FOLDER
        result = window.create_file_dialog(dialog_type)
        if not result:
            return None
        return str(result[0])

    def choose_export_directory(self) -> str | None:
        return self._choose_folder()

    def choose_import_directory(self) -> str | None:
        return self._choose_folder()

    def restart_app(self) -> bool:
        import webview

        self.restart_requested = True
        webview.windows[0].destroy()
        return True


def _configure_environment(paths: DesktopDataPaths, resource_root: Path) -> None:
    os.environ["SHUTTLECUBE_ENVIRONMENT"] = "desktop"
    os.environ["SHUTTLECUBE_DESKTOP_MODE"] = "true"
    os.environ["SHUTTLECUBE_DATA_DIR"] = str(paths.root)
    os.environ["SHUTTLECUBE_DATABASE_URL"] = sqlite_url(paths.database)
    os.environ["SHUTTLECUBE_STATIC_DIR"] = str(_frontend_root(resource_root))
    os.environ["SHUTTLECUBE_ARTIFACT_STORAGE"] = "local"
    os.environ["SHUTTLECUBE_LOCAL_ARTIFACT_DIR"] = str(paths.attachments)
    os.environ["SHUTTLECUBE_SECRET_KEY"] = _installation_secret(paths)


def _prepare_data(paths: DesktopDataPaths, resource_root: Path) -> None:
    paths.ensure()
    apply_pending_import(paths)
    migrate_legacy_database(DEFAULT_DATABASE_PATH, paths.database)
    run_migrations(sqlite_url(paths.database), _backend_root(resource_root))
    paths.manifest.write_text(
        json.dumps(
            {"format_version": 1, "app_version": "0.1.0", "database": "database/shuttlecube.db"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _wait_until_ready(url: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("本地服务启动超时")


def _restart_process() -> None:
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable], close_fds=True)
    else:
        subprocess.Popen([sys.executable, "-m", "shuttlecube.desktop"], close_fds=True)


def main() -> None:
    data_root = Path(os.environ.get("SHUTTLECUBE_DATA_DIR", default_desktop_data_root()))
    paths = DesktopDataPaths.from_root(data_root)
    resource_root = _resource_root()
    restart_requested = False
    with SingleInstance(paths.lock_file):
        paths.ensure()
        _configure_environment(paths, resource_root)
        _prepare_data(paths, resource_root)

        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("请安装 ShuttleCube desktop 依赖后再启动桌面版") from exc

        # Imports happen after desktop environment variables are configured because
        # the database engine is initialized when the application module loads.
        from shuttlecube.app import create_app

        port = _available_port()
        url = f"http://127.0.0.1:{port}"
        config = uvicorn.Config(
            create_app(),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name="shuttlecube-local-api", daemon=True)
        thread.start()
        _wait_until_ready(url)
        if os.environ.get("SHUTTLECUBE_DESKTOP_SMOKE_TEST") == "true":
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    if response.status != 200 or b"ShuttleCube" not in response.read():
                        raise RuntimeError("桌面前端资源检查失败")
            finally:
                server.should_exit = True
                thread.join(timeout=10)
            return

        try:
            import webview
        except ImportError as exc:
            server.should_exit = True
            thread.join(timeout=10)
            raise SystemExit("请安装 ShuttleCube desktop 依赖后再启动桌面版") from exc
        bridge = DesktopBridge()
        webview.create_window(
            "ShuttleCube 场馆运营管理",
            url,
            js_api=bridge,
            width=1440,
            height=920,
            min_size=(1100, 720),
        )
        try:
            webview.start()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        restart_requested = bridge.restart_requested
    if restart_requested:
        _restart_process()


def _report_startup_error(exc: Exception) -> None:
    data_root = Path(os.environ.get("SHUTTLECUBE_DATA_DIR", default_desktop_data_root()))
    log = DesktopDataPaths.from_root(data_root).settings / "desktop-error.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
    if os.environ.get("SHUTTLECUBE_DESKTOP_SMOKE_TEST") != "true" and os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            f"ShuttleCube 启动失败。错误详情已保存到：\n{log}",
            "ShuttleCube",
            0x10,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        _report_startup_error(error)
        raise SystemExit(1) from error
