"""
pipeline_result.py — 流水线执行结果数据模型

AutoPaperPipeline 的完整输出结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.download_result import BatchDownloadResult
from app.models.paper import Paper
from app.models.query_plan import QueryPlan
from app.models.rank_result import ScoredItem
from app.models.rewrite_result import RewriteResult


class StepStatus(BaseModel):
    """单个流水线步骤的执行状态。"""

    step: str = Field(
        ...,
        description="步骤名: plan | rewrite | search | merge | rerank | download",
    )

    success: bool = Field(
        ...,
        description="该步骤是否成功执行",
    )

    error: str = Field(
        default="",
        description="失败时的错误信息",
    )

    duration_ms: float = Field(
        default=0.0,
        description="步骤耗时（毫秒）",
    )


class PipelineResult(BaseModel):
    """AutoPaper 流水线完整执行结果。"""

    query: str = Field(
        ...,
        description="原始用户查询",
    )

    success: bool = Field(
        default=False,
        description="流水线整体是否成功（至少搜索步骤成功）",
    )

    steps: list[StepStatus] = Field(
        default_factory=list,
        description="各步骤执行状态",
    )

    # ── 各步骤输出 ──────────────────────────────────────────

    plan: QueryPlan | None = Field(
        default=None,
        description="步骤1: 查询计划",
    )

    rewrite: RewriteResult | None = Field(
        default=None,
        description="步骤2: 查询改写结果",
    )

    papers: list[Paper] = Field(
        default_factory=list,
        description="步骤4: 去重合并后的论文列表",
    )

    scored_items: list[ScoredItem] = Field(
        default_factory=list,
        description="步骤5: 相关性评分排序结果",
    )

    download: BatchDownloadResult | None = Field(
        default=None,
        description="步骤6: 批量下载结果",
    )

    @property
    def top_papers(self) -> list[Paper]:
        """按评分排序后的 top papers 快捷访问。"""
        if not self.scored_items or not self.papers:
            return self.papers

        result: list[Paper] = []
        for item in self.scored_items:
            if item.paper_index < len(self.papers):
                result.append(self.papers[item.paper_index])
        return result
