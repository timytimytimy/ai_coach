from __future__ import annotations

import logging
import os
import re
from typing import Any


_BASE64_SNIPPET_RE = re.compile(r"(base64,)[A-Za-z0-9+/=\s]{32,}")


def redact_large_log_blobs(value: Any) -> Any:
    if isinstance(value, str):
        return _BASE64_SNIPPET_RE.sub(r"\1...", value)
    if isinstance(value, tuple):
        return tuple(redact_large_log_blobs(item) for item in value)
    if isinstance(value, list):
        return [redact_large_log_blobs(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_large_log_blobs(item) for key, item in value.items()}
    return value


class Base64RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_large_log_blobs(record.msg)
        if record.args:
            record.args = redact_large_log_blobs(record.args)
        return True


def setup_logging() -> None:
    level_name = (os.environ.get("SSC_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        root.setLevel(level)
    redaction_filter = Base64RedactionFilter()
    for handler in root.handlers:
        handler.addFilter(redaction_filter)
