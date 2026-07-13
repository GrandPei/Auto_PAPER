"""
logger.py — 日志封装

基于 Python logging 标准库，从全局配置读取日志等级与格式。
"""

import logging
import sys

from app.core.config import settings


def get_logger(name: str | None = None) -> logging.Logger:
    """获取一个已配置好的 logger 实例。

    Args:
        name: logger 名称，通常传入 __name__。

    Returns:
        配置好的 Logger 实例。
    """
    _logger = logging.getLogger(name)

    if not _logger.handlers:
        _logger.setLevel(_resolve_level())

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(_resolve_level())

        formatter = logging.Formatter(
            fmt=settings.log_format,
            datefmt=settings.log_datefmt,
        )
        handler.setFormatter(formatter)

        _logger.addHandler(handler)
        _logger.propagate = False

    return _logger


def _resolve_level() -> int:
    """将配置字符串转为 logging 等级常量。"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(settings.log_level.upper(), logging.INFO)
