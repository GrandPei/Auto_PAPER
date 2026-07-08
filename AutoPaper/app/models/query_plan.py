"""
query_plan.py — 查询计划数据模型

QueryPlanner 的输入 / 输出结构定义。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubQuery(BaseModel):
    """子查询 — 从原始问题中拆分出的独立研究方向。"""

    description: str = Field(
        ...,
        description="子问题的自然语言描述",
        min_length=1,
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="该子问题的中英文关键词列表",
    )

    constraints: list[str] = Field(
        default_factory=list,
        description="该子问题的额外限定条件（时间、方法、对象等）",
    )


class QueryPlan(BaseModel):
    """查询计划 — Deepseek 分析用户自然语言后产出的结构化查询方案。"""

    original_query: str = Field(
        ...,
        description="用户原始输入，原样保留",
    )

    research_topic: str = Field(
        ...,
        description="提炼后的研究主题（精炼的一句话概括）",
        min_length=1,
    )

    application_domain: str = Field(
        default="",
        description="应用领域，如 NLP / 生物信息 / 材料科学 / 经济学 等",
    )

    constraints: list[str] = Field(
        default_factory=list,
        description="全局限定条件列表（时间范围、方法论、地域、语种等）",
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="全局中英文检索关键词",
    )

    sub_queries: list[SubQuery] = Field(
        default_factory=list,
        description="拆分出的子问题列表；若无法拆分则为空",
    )
