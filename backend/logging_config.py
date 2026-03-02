"""Structured logging configuration for production deployment.

Provides JSON logging for Render and other cloud platforms.
All logs go to stdout for container collection.
"""

import logging
import logging.handlers
import sys
from typing import Optional
import json

import config


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for cloud-native environments."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON."""
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "session_id"):
            log_obj["session_id"] = record.session_id

        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id

        return json.dumps(log_obj)


def setup_logging(name: Optional[str] = None) -> logging.Logger:
    """Configure structured logging.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name or __name__)
    logger.setLevel(config.LOG_LEVEL)

    # Remove existing handlers (idempotent)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # StreamHandler to stdout (required for containerized environments)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(config.LOG_LEVEL)

    if config.IS_PRODUCTION:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger by name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Module-level logger for this module
logger = setup_logging(__name__)
