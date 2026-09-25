import json
import logging

import pytest

from app.core.logging import REDACTED, JsonFormatter, RedactionFilter, TextFormatter, redact

pytestmark = pytest.mark.unit

SECRET = "sk-live-abcdef123456"


def make_record(msg: str, *args: object, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, msg, args or None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_redact_masks_secret_values() -> None:
    assert redact(f"key={SECRET}", [SECRET]) == f"key={REDACTED}"


def test_redact_ignores_very_short_secrets() -> None:
    # Masking "ab" would destroy unrelated text.
    assert redact("tab table", ["ab"]) == "tab table"


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "{'authorization': 'Bearer abc.def.ghi'}",
        "calling with bearer abc123TOKEN",
    ],
)
def test_redact_masks_authorization_headers_and_bearer_tokens(text: str) -> None:
    result = redact(text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in result
    assert "abc.def.ghi" not in result
    assert "abc123TOKEN" not in result
    assert REDACTED in result


def test_filter_masks_message_args_and_extra_fields() -> None:
    record = make_record("using key %s", SECRET, header=f"Bearer {SECRET}")
    assert RedactionFilter([SECRET]).filter(record)
    assert SECRET not in record.getMessage()
    assert SECRET not in str(record.header)  # type: ignore[attr-defined]


def test_filter_masks_exception_text() -> None:
    try:
        raise RuntimeError(f"connection failed with {SECRET}")
    except RuntimeError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    RedactionFilter([SECRET]).filter(record)
    assert record.exc_text is not None
    assert SECRET not in record.exc_text


def test_json_formatter_includes_extra_fields() -> None:
    record = make_record("node finished", recipe_id="r1", duration_ms=12.5)
    record.request_id = "req-123"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "node finished"
    assert payload["recipe_id"] == "r1"
    assert payload["duration_ms"] == 12.5
    assert payload["request_id"] == "req-123"


def test_text_formatter_appends_extra_fields() -> None:
    record = make_record("hello", job_id="j1")
    record.request_id = None
    assert "job_id=j1" in TextFormatter().format(record)
