"""
paper.py — 论文数据模型

统一的论文表示，所有搜索源结果均转换为此结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """统一论文元数据模型。"""

    title: str = Field(
        ...,
        description="论文标题",
        min_length=1,
    )

    authors: list[str] = Field(
        default_factory=list,
        description="作者列表",
    )

    year: int | None = Field(
        default=None,
        description="发表年份",
    )

    abstract: str = Field(
        default="",
        description="摘要",
    )

    citation_count: int = Field(
        default=0,
        ge=0,
        description="引用次数",
    )

    venue: str = Field(
        default="",
        description="发表期刊/会议名称",
    )

    url: str = Field(
        default="",
        description="论文链接",
    )

    doi: str = Field(
        default="",
        description="DOI 标识符",
    )

    source: str = Field(
        default="",
        description="数据来源: semantic_scholar | openalex | arxiv",
    )
