"""
download_result.py — 下载状态数据模型

PaperDownloader 的输出结构定义。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DownloadResult(BaseModel):
    """单篇论文的下载结果。"""

    paper_title: str = Field(
        ...,
        description="论文标题",
    )

    success: bool = Field(
        ...,
        description="下载是否成功",
    )

    file_path: str = Field(
        default="",
        description="本地保存路径（成功时）",
    )

    error: str = Field(
        default="",
        description="错误信息（失败时）",
    )

    retries_used: int = Field(
        default=0,
        ge=0,
        description="实际使用的重试次数",
    )

    source_channel: str = Field(
        default="",
        description="最终成功的下载渠道: google_scholar | semantic_scholar | arxiv",
    )


class BatchDownloadResult(BaseModel):
    """批量下载汇总结果。"""

    total: int = Field(
        ...,
        ge=0,
        description="下载总数",
    )

    success_count: int = Field(
        default=0,
        ge=0,
        description="成功数",
    )

    failure_count: int = Field(
        default=0,
        ge=0,
        description="失败数",
    )

    results: list[DownloadResult] = Field(
        default_factory=list,
        description="每篇论文的详细下载结果",
    )
