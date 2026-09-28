"""Structured logging configuration using structlog with secret redaction."""

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

URI_CREDENTIAL_PATTERN = re.compile(r"://([^:@\s]+):([^@\s]+)@")

SECRET_FIELDS = {
    "api_key",
    "password",
    "token",
    "secret",
    "credential",
    "database_url",
    "neo4j_password",
    "openrouter_api_key",
}


class SecretRedactingProcessor:
    """Processor that redacts known secret fields and credentials before rendering."""

    def __init__(self, secret_keys: set[str] | None = None) -> None:
        self.secret_keys = {k.lower() for k in (secret_keys or SECRET_FIELDS)}

    def __call__(
        self,
        logger: WrappedLogger,
        method_name: str,
        event_dict: MutableMapping[str, Any],
    ) -> EventDict:
        for key in list(event_dict.keys()):
            key_lower = key.lower()
            matches_secret = key_lower in self.secret_keys or any(
                s in key_lower for s in ("password", "api_key", "secret", "token")
            )
            if matches_secret:
                event_dict[key] = "[REDACTED]"
            elif isinstance(event_dict[key], str):
                event_dict[key] = URI_CREDENTIAL_PATTERN.sub(
                    "://[REDACTED]:[REDACTED]@",
                    event_dict[key],
                )
        return dict(event_dict)


def configure_logging(app_env: str = "development", log_level: str = "INFO") -> None:
    """Configure structlog and standard logging based on application environment."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        SecretRedactingProcessor(),
    ]

    if app_env.lower() in ("production", "test"):
        final_renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        final_renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            final_renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
