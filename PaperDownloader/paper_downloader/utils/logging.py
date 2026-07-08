"""Logging configuration using Loguru."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: str | Path = "paper_downloader.log",
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """Configure Loguru logger with console and file sinks.

    Args:
        level: Minimum log level for console output.
        log_file: Path to the log file.
        rotation: When to rotate the log file (e.g., "10 MB", "1 day").
        retention: How long to keep old log files.
    """
    # Remove default handler
    logger.remove()

    # Console sink with colorized output
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File sink for persistent logs
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=rotation,
        retention=retention,
        compression="gz",
        backtrace=True,
        diagnose=True,
    )

    logger.info("Logging configured (level={}, file={})", level, log_file)
