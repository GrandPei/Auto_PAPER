"""
key_manager.py — 统一 API Key 管理

使用方式:
    from API_key.key_manager import key_get
    serpapi_key = key_get("serpapi")
    deepseek_key = key_get("deepseek")
"""

import json
import os

_JSON_PATH = os.path.join(os.path.dirname(__file__), "API_key.json")
_cache = None


def _load() -> dict:
    """加载 JSON 文件（仅首次读取，后续命中缓存）。"""
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = {}
    return _cache


def key_get(name: str) -> str:
    """
    获取指定服务的 API Key。

    查找顺序: JSON 文件 → 环境变量（{NAME}_API_KEY）→ 空字符串

    Args:
        name: 服务名，如 "serpapi"、"deepseek"

    Returns:
        API Key 字符串，未找到则返回 ""
    """
    keys = _load()
    if name in keys and keys[name]:
        return keys[name]

    env_var = f"{name.upper()}_API_KEY"
    return os.environ.get(env_var, "")
