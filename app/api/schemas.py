"""
schemas.py — API 请求/响应 Pydantic 模型
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """POST /search 请求体。"""

    query: str = Field(
        ...,
        description="用户自然语言查询",
        min_length=1,
        max_length=1000,
        examples=["近五年图神经网络在药物发现中的应用"],
    )


class PaperItem(BaseModel):
    """单篇论文的 API 响应条目。"""

    title: str = Field(
        ...,
        description="论文标题",
    )

    abstract: str = Field(
        default="",
        description="摘要",
    )

    authors: list[str] = Field(
        default_factory=list,
        description="作者列表",
    )

    source: str = Field(
        default="",
        description="数据来源",
    )

    year: int | None = Field(
        default=None,
        description="发表年份",
    )

    citation_count: int = Field(
        default=0,
        description="引用次数",
    )

    venue: str = Field(
        default="",
        description="发表期刊/会议",
    )

    url: str = Field(
        default="",
        description="论文链接",
    )

    doi: str = Field(
        default="",
        description="DOI 标识符",
    )

    score: int | None = Field(
        default=None,
        description="相关性评分 (0-100)",
    )

    score_reason: str = Field(
        default="",
        description="评分理由",
    )

    pdf_downloaded: bool = Field(
        default=False,
        description="PDF 是否下载成功",
    )

    pdf_path: str = Field(
        default="",
        description="PDF 本地路径",
    )


class PipelineSummary(BaseModel):
    """流水线执行摘要。"""

    total_steps: int = Field(default=0)
    success_steps: int = Field(default=0)
    failed_steps: int = Field(default=0)
    total_duration_ms: float = Field(default=0.0)
    step_details: list[dict] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """POST /search 响应体。"""

    query: str = Field(
        ...,
        description="原始查询",
    )

    total: int = Field(
        default=0,
        description="返回论文总数",
    )

    papers: list[PaperItem] = Field(
        default_factory=list,
        description="论文列表（按相关性排序）",
    )

    pipeline: PipelineSummary = Field(
        default_factory=PipelineSummary,
        description="流水线执行摘要",
    )
