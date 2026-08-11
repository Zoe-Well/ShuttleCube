from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shuttlecube.api.errors import install_error_handlers
from shuttlecube.api.middleware import install_middleware
from shuttlecube.api.v1.router import router
from shuttlecube.application.operations import (
    reconciliation_workflow as _reconciliation_workflow,  # noqa: F401
)
from shuttlecube.application.operations import (
    replacement_executor as _replacement_executor,  # noqa: F401
)
from shuttlecube.application.operations import revenue_workflow as _revenue_workflow  # noqa: F401
from shuttlecube.application.operations import workflows as _operations_workflows  # noqa: F401
from shuttlecube.application.operations.runner import OperationsRunner
from shuttlecube.application.operations.runtime import execute_persisted_run
from shuttlecube.application.operations.scheduling import schedule_due_scans
from shuttlecube.config import get_settings
from shuttlecube.domain import models as _models  # noqa: F401
from shuttlecube.infrastructure.database.session import SessionLocal, get_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    runner: OperationsRunner | None = None
    if settings.operations_runner_enabled and get_db not in app.dependency_overrides:
        runner = OperationsRunner(
            SessionLocal,
            lambda run_id: execute_persisted_run(SessionLocal, run_id),
            worker_id=f"api-{uuid4()}",
            poll_seconds=settings.operations_runner_poll_seconds,
            lease_duration=timedelta(seconds=settings.operations_runner_lease_seconds),
            startup_hooks=(lambda: schedule_due_scans(SessionLocal),),
            periodic_hooks=(lambda: schedule_due_scans(SessionLocal),),
            periodic_hook_seconds=60,
        )
        await runner.start()
        app.state.operations_runner = runner
    try:
        yield
    finally:
        if runner is not None:
            await runner.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    install_middleware(app)
    install_error_handlers(app)
    app.include_router(router)

    @app.get("/health", tags=["Platform"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    static_dir = settings.static_dir
    if static_dir and static_dir.is_dir():
        _install_static_frontend(app, static_dir)

    return app


def _install_static_frontend(app: FastAPI, static_dir: Path) -> None:
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="desktop-assets")

    @app.get("/{requested_path:path}", include_in_schema=False)
    def desktop_frontend(requested_path: str) -> FileResponse:
        requested = (static_dir / requested_path).resolve()
        if static_dir.resolve() in requested.parents and requested.is_file():
            return FileResponse(requested)
        return FileResponse(static_dir / "index.html")
