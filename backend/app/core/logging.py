"""Logging setup: structured output, secret redaction and request logging (SPEC §32)."""

import json
import logging
import re
import sys
import time
import uuid
from collections.abc import Iterable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED = "***"
_MIN_SECRET_LENGTH = 4
_AUTH_PATTERN = re.compile(
    r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)([^\"',\s]+(?:\s+[^\"',\s]+)?)"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_STANDARD_RECORD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {
    "message",
    "asctime",
    "request_id",
    "color_message",  # uvicorn duplicates the message with ANSI colours
}

access_logger = logging.getLogger("app.access")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Mask known secret values, Authorization headers and bearer tokens."""
    for secret in secrets:
        if len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, REDACTED)
    text = _AUTH_PATTERN.sub(rf"\1{REDACTED}", text)
    return _BEARER_PATTERN.sub(rf"\1{REDACTED}", text)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in vars(record).items() if k not in _STANDARD_RECORD_ATTRS}


class RequestContextFilter(logging.Filter):
    """Attach the current request id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RedactionFilter(logging.Filter):
    """Remove secrets from the message, extra fields and exception text."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if len(s) >= _MIN_SECRET_LENGTH]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self._secrets)
        record.args = None
        for key, value in _extra_fields(record).items():
            if isinstance(value, str):
                setattr(record, key, redact(value, self._secrets))
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self._secrets)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            **_extra_fields(record),
        }
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            payload["exc_info"] = record.exc_text
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Readable development format: message followed by key=value extras."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = " ".join(f"{k}={v}" for k, v in _extra_fields(record).items())
        return f"{base} {extras}" if extras else base


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.is_production else TextFormatter())
    handler.addFilter(RequestContextFilter())
    handler.addFilter(RedactionFilter(settings.secret_values()))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # Uvicorn logs flow through our handler; its access log is replaced by ours.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True


def _incoming_request_id(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _REQUEST_ID_PATTERN.match(candidate) else None
    return None


class RequestLoggingMiddleware:
    """Log one line per request and return an `X-Request-ID` header.

    Only the path is logged, never the query string (it may carry tokens).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            access_logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
