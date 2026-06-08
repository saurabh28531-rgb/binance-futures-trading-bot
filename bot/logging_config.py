import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

from bot.config import config

# Log directory sits at project root level
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


class RequestIdFilter(logging.Filter):
    """
    Logging filter that injects request_id into every log record.

    If a log record does not have a request_id set, it defaults to '-'.
    This ensures every log line has a consistent format whether or not
    a request_id has been set for that context.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def setup_logger(name: str) -> logging.Logger:
    """
    Set up and return a logger with both file and console handlers.

    File handler    → DEBUG level and above (everything)
    Console handler → Level from config (default INFO)

    Every log line includes a request_id field for traceability.
    Credentials are never logged — enforced by never passing them
    to any logger call in the codebase.

    Args:
        name: Logger name, typically the module name e.g. 'bot.client'

    Returns:
        Configured logger instance
    """
    # Create logs directory if it does not exist yet
    os.makedirs(LOG_DIR, exist_ok=True)

    # Log file name includes date so each day gets its own file
    log_filename = os.path.join(
        LOG_DIR,
        f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
    )

    # Get or create logger
    logger = logging.getLogger(name)

    # Only configure if not already configured
    # Prevents duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Add request ID filter to logger
    logger.addFilter(RequestIdFilter())

    # Log format — timestamp | level | module | request_id | message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler — captures everything DEBUG and above
    # Rotates after 5MB, keeps last 3 files
    file_handler = RotatingFileHandler(
        filename=log_filename,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler — level driven by config
    # Default INFO, can be changed to DEBUG via LOG_LEVEL in .env
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.log_level, logging.INFO))
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger