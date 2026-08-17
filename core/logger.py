"""Structured logging configuration for JARVIS."""

import logging
import sys
from typing import Optional
from core.config import get_settings


def configure_logging(level: Optional[str] = None) -> None:
    """Configure global logging format and handler."""
    log_level = level or get_settings().log_level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    log_format = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Reset root handlers
    root = logging.getLogger()
    root.setLevel(numeric_level)
    
    # Avoid duplicate handlers
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
        handler.setFormatter(formatter)
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Obtain a named logger instance."""
    return logging.getLogger(name)
