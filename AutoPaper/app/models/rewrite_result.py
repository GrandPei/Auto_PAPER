"""
rewrite_result.py — 查询改写结果数据模型

QueryRewriter 的输出结构定义。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpandedQuery(BaseModel):
    """单条改写/扩展后的搜索查询。"""

    query: str = Field(
        ...,
        description="改写后的完整查询字符串，可直接送入搜索 API",
        min_length=1,
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="该查询的核心关键词",
    )

    rewrite_type: str = Field(
        default="expansion",
        description="改写类型: synonym | abbreviation | full_name | related_direction | expansion",
    )


class RewriteResult(BaseModel):
    """查询改写结果 — QueryRewriter 的完整输出。"""

    original_query: str = Field(
        ...,
        description="原始查询，从 QueryPlan 继承",
    )

    expanded_queries: list[ExpandedQuery] = Field(
        ...,
        description="5-10 条改写/扩展后的搜索查询",
        min_length=1,
    )

    synonyms: list[str] = Field(
        default_factory=list,
        description="识别到的近义词（组），如 '图神经网络 ↔ GNN ↔ 图卷积网络'",
    )

    alternative_keywords: list[str] = Field(
        default_factory=list,
        description="替代关键词列表，可用于扩大检索范围",
    )
