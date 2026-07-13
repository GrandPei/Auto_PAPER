"""
rank_result.py — 论文排序结果数据模型

PaperReranker 的输出结构定义。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoredItem(BaseModel):
    """单篇论文的相关性评分。"""

    paper_index: int = Field(
        ...,
        ge=0,
        description="论文在输入列表中的索引位置",
    )

    score: int = Field(
        ...,
        ge=0,
        le=100,
        description="0-100 相关性评分，100 为完全匹配",
    )

    reason: str = Field(
        default="",
        description="评分理由（一句话简述匹配/不匹配原因）",
    )


class RankResult(BaseModel):
    """论文排序结果。"""

    query: str = Field(
        ...,
        description="原始查询字符串",
    )

    scored_items: list[ScoredItem] = Field(
        default_factory=list,
        description="按 score 降序排列的评分列表",
    )
