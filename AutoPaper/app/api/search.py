"""
search.py — POST /search 端点

调用 AutoPaperPipeline 执行完整检索-分析-下载流程，
返回结构化论文列表。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    PaperItem,
    PipelineSummary,
    SearchRequest,
    SearchResponse,
)
from app.models.pipeline_result import PipelineResult
from app.services.pipeline import AutoPaperPipeline, PipelineError
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

# 流水线全局单例（延迟初始化）
_pipeline: AutoPaperPipeline | None = None


def get_pipeline() -> AutoPaperPipeline:
    """获取流水线单例。"""
    global _pipeline
    if _pipeline is None:
        _pipeline = AutoPaperPipeline()
    return _pipeline


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """学术论文检索与分析。

    执行完整流水线:
      查询结构化 → 术语扩展 → 多源搜索 →
      去重融合 → 相关性排序 → PDF 下载

    Args:
        request: 包含用户自然语言查询的请求体。

    Returns:
        SearchResponse: 包含论文列表、评分、下载状态的结构化响应。
    """
    logger.info("API 收到搜索请求: %s", request.query[:120])

    pipeline = get_pipeline()

    try:
        result: PipelineResult = await pipeline.run(
            request.query,
            search_limit=10,
            download_top=3,
        )
    except PipelineError as exc:
        logger.error("Pipeline 执行异常: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.error("未预期的 Pipeline 异常: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部错误: {exc}")

    # 构建响应
    papers = _build_papers(result)
    pipeline_summary = _build_summary(result)

    logger.info(
        "API 返回 — query: %s | 论文: %d 篇",
        request.query[:60],
        len(papers),
    )

    return SearchResponse(
        query=request.query,
        total=len(papers),
        papers=papers,
        pipeline=pipeline_summary,
    )


# ── 辅助函数 ──────────────────────────────────────────────────


def _build_papers(result: PipelineResult) -> list[PaperItem]:
    """从 PipelineResult 构建 PaperItem 列表。

    将 Paper + ScoredItem + DownloadResult 三个维度的数据
    合并为统一的 API 响应条目。
    """
    # 建立 download 结果索引 (title → DownloadResult)
    download_map: dict[str, bool] = {}
    download_path_map: dict[str, str] = {}
    if result.download:
        for dr in result.download.results:
            key = dr.paper_title.strip().lower()
            download_map[key] = dr.success
            download_path_map[key] = dr.file_path if dr.success else ""

    # 建立 score 索引 (paper_index → ScoredItem)
    score_map: dict[int, tuple[int, str]] = {}
    for item in result.scored_items:
        score_map[item.paper_index] = (item.score, item.reason)

    items: list[PaperItem] = []

    # 确定遍历顺序: 优先按评分排序, 未评分的按原始索引
    ordered_indices: list[int] = []
    if result.scored_items:
        ordered_indices = [s.paper_index for s in result.scored_items]
        # 补充未评分的论文
        scored_set = set(ordered_indices)
        for i in range(len(result.papers)):
            if i not in scored_set:
                ordered_indices.append(i)
    else:
        ordered_indices = list(range(len(result.papers)))

    for idx in ordered_indices:
        if idx >= len(result.papers):
            continue
        paper = result.papers[idx]

        # 评分信息
        score, reason = score_map.get(idx, (None, ""))

        # 下载状态
        title_key = paper.title.strip().lower()
        pdf_downloaded = download_map.get(title_key, False)
        pdf_path = download_path_map.get(title_key, "")

        items.append(PaperItem(
            title=paper.title,
            abstract=paper.abstract,
            authors=paper.authors,
            source=paper.source,
            year=paper.year,
            citation_count=paper.citation_count,
            venue=paper.venue,
            url=paper.url,
            doi=paper.doi,
            score=score,
            score_reason=reason,
            pdf_downloaded=pdf_downloaded,
            pdf_path=pdf_path,
        ))

    return items


def _build_summary(result: PipelineResult) -> PipelineSummary:
    """从 PipelineResult 构建流水线执行摘要。"""
    step_details = [
        {
            "step": s.step,
            "success": s.success,
            "error": s.error,
            "duration_ms": s.duration_ms,
        }
        for s in result.steps
    ]

    success_count = sum(1 for s in result.steps if s.success)
    total_duration = sum(s.duration_ms for s in result.steps)

    return PipelineSummary(
        total_steps=len(result.steps),
        success_steps=success_count,
        failed_steps=len(result.steps) - success_count,
        total_duration_ms=round(total_duration, 1),
        step_details=step_details,
    )
