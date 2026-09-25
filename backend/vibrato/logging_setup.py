from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SENSITIVE_KEY = re.compile(r"(secret|token|password|passwd|api[_-]?key|authorization)", re.IGNORECASE)
_SENSITIVE_INLINE = re.compile(
    r"(?i)\b(secret|token|password|passwd|api[_-]?key|authorization)\b(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)


def redact(text: str) -> str:
    return _SENSITIVE_INLINE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: ("[REDACTED]" if _SENSITIVE_KEY.search(str(k)) else v) for k, v in record.args.items()
                }
            else:
                record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "fields", None)
        if isinstance(extra_fields, dict):
            payload["fields"] = {
                k: ("[REDACTED]" if _SENSITIVE_KEY.search(k) else v) for k, v in extra_fields.items()
            }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


_configured = False


def setup_logging(logs_dir: Path, level: str | None = None) -> None:
    global _configured
    if _configured:
        return
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("vibrato")
    root.setLevel(level or os.environ.get("VIBRATO_LOG_LEVEL", "INFO"))
    root.propagate = False
    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "vibrato.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(RedactingFilter())
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    console.addFilter(RedactingFilter())
    root.addHandler(file_handler)
    root.addHandler(console)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"vibrato.{name}")


def log_event(logger: logging.Logger, message: str, **fields: object) -> None:
    logger.info(message, extra={"fields": fields})
