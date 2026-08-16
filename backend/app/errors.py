"""
One error envelope, matching api-contract/ERROR_validation.json exactly.

    {"error": {"code": ..., "message": ..., "fields": [...], "request_id": ...}}

The frontend's ApiError class reads `body.error.code` (see src/lib/api.ts). FastAPI's
default error body is `{"detail": [...]}`, which that class cannot parse -- it would
fall through to a synthesised `HTTP_422` code and the UI would show a generic failure
instead of the real reason. So every error path in this service, including FastAPI's
own request validation, is reshaped here.

`fields` is omitted when empty rather than sent as `[]`, because ERROR_leakage.json
and ERROR_validation.json carry different sub-shapes and inventing a third would be
worse than sending nothing.
"""
from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def envelope(code: str, message: str, fields: list | None = None) -> dict:
    """Key order matches the fixtures: code, message, fields, request_id."""
    err: dict = {"code": code, "message": message}
    if fields:
        err["fields"] = fields
    err["request_id"] = request_id()
    return {"error": err}


class ApiError(Exception):
    """Raise this anywhere; the handler below turns it into the envelope."""

    def __init__(self, status: int, code: str, message: str, fields: list | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields


def install(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status,
            content=envelope(exc.code, exc.message, exc.fields),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields = []
        for e in exc.errors():
            # loc is like ("query", "page_size") or ("body", "action")
            loc = [str(p) for p in e.get("loc", []) if p not in ("body", "query", "path")]
            item = {"field": ".".join(loc) or "request", "message": e.get("msg", "invalid")}
            if "input" in e:
                item["received"] = e["input"]
            fields.append(item)
        return JSONResponse(
            status_code=422,
            content=envelope("VALIDATION_ERROR", "Request failed field validation", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {
            400: "BAD_REQUEST",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            500: "INTERNAL_ERROR",
        }.get(exc.status_code, f"HTTP_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=envelope("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"),
        )
