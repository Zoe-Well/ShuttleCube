from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class BusinessError(Exception):
    def __init__(self, status: int, code: str, detail: str, **extra: Any) -> None:
        self.status, self.code, self.detail, self.extra = status, code, detail, extra


class ConcurrentChange(BusinessError):
    def __init__(self, detail: str = "记录已被其他操作修改，请刷新后重试") -> None:
        super().__init__(409, "concurrent_change", detail)


def problem(status: int, title: str, detail: str, request: Request, **extra: Any) -> JSONResponse:
    return JSONResponse(
        {
            "type": f"https://shuttlecube.local/problems/{title}",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": str(request.url.path),
            **extra,
        },
        status_code=status,
        media_type="application/problem+json",
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def business_handler(request: Request, exc: BusinessError) -> JSONResponse:
        return problem(exc.status, exc.code, exc.detail, request, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            serializable = dict(error)
            if context := serializable.get("ctx"):
                serializable["ctx"] = {key: str(value) for key, value in context.items()}
            errors.append(serializable)
        return problem(422, "validation_error", "请求内容不符合要求", request, errors=errors)
