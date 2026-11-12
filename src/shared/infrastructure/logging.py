"""Global logging configuration for the entire application.

Centralized setup used across all modules. Console output is human-readable
(coloured when attached to a TTY); file output is JSON for structured ingestion.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..utils.config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logs (file output)."""

    def format(self, record):
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": settings.app_name,
            "environment": settings.environment,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data

        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Simple readable formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True):
        """Initialize console formatter.

        Args:
            use_colors: Whether to use colored output
        """
        self.use_colors = use_colors and sys.stdout.isatty()
        fmt = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        super().__init__(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        """Format log record with optional colors."""
        levelname = record.levelname
        if self.use_colors:
            color = self.COLORS.get(levelname, self.RESET)
            record.levelname = f"{color}{levelname}{self.RESET}"

        result = super().format(record)

        # Reset levelname so other handlers see the plain value.
        if self.use_colors:
            record.levelname = levelname

        return result


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    use_json: bool = False,
    use_colors: bool = True,
) -> logging.Logger:
    """Configure global application logging.

    Called once at application startup.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        use_json: Use JSON formatting for console output (for production)
        use_colors: Use colored console output

    Returns:
        Root logger instance
    """
    level = log_level or settings.log_level

    log_file = log_file or settings.log_file
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    json_formatter = JSONFormatter()
    console_formatter = (
        JSONFormatter() if use_json else ConsoleFormatter(use_colors=use_colors)
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("pymongo").setLevel(logging.WARNING)

    root_logger.info(f"Logging configured - Level: {level}, File: {log_file or 'None'}")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get logger instance for a module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
