"""
base.py — 搜索引擎抽象接口

所有搜索源必须实现 BaseSearcher。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.paper import Paper


class BaseSearcher(ABC):
    """学术搜索引擎抽象基类。

    子类需实现:
      - source_name (property)
      - search(query, limit) → list[Paper]
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """搜索源标识符，如 'semantic_scholar'。"""
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[Paper]:
        """按查询词搜索论文。

        Args:
            query: 搜索查询字符串。
            limit: 返回结果数量上限。

        Returns:
            Paper 对象列表。
        """
        ...


class SearchError(Exception):
    """搜索异常基类。"""

    def __init__(self, message: str, source: str = ""):
        super().__init__(message)
        self.source = source
