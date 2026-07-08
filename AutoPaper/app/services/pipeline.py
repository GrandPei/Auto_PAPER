"""
pipeline.py — AutoPaper 主流水线

串联全部服务模块，形成端到端的论文检索-分析-下载流程。

流程:
    User Query
      → Planner (查询结构化)
      → Rewrite (术语扩展)
      → Search  (多源并行搜索)
      → Merge   (去重融合)
      → Rerank  (相关性排序)
      → Download (PDF 下载)
      → PipelineResult (JSON)

特性:
  - 全链路异步
  - 每一步记录日志 + 耗时
  - 单步异常不中断整体流程（优雅降级）
"""

from __future__ import annotations

import time

from app.llm.deepseek_client import DeepseekClient
from app.models.paper import Paper
from app.models.pipeline_result import PipelineResult, StepStatus
from app.models.query_plan import QueryPlan
from app.models.rank_result import ScoredItem
from app.models.rewrite_result import RewriteResult
from app.search.manager import SearchManager
from app.services.download import PaperDownloader
from app.services.paper_merge import PaperMerger
from app.services.query_planner import QueryPlanner, QueryPlannerError
from app.services.query_rewrite import QueryRewriter, QueryRewriteError
from app.services.rerank import PaperReranker, RerankError
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 默认配置
_DEFAULT_SEARCH_LIMIT = 10   # 每条 query 每个源返回的论文数
_DEFAULT_DOWNLOAD_TOP = 3    # 默认下载 top N 篇论文
_DEFAULT_DOWNLOAD_CONCUR = 3


class PipelineError(Exception):
    """流水线异常。"""


class AutoPaperPipeline:
    """AutoPaper 主流水线 — 端到端论文检索-分析-下载。

    用法::

        pipeline = AutoPaperPipeline()
        result = await pipeline.run("近五年图神经网络在药物发现中的应用")
        print(f"找到 {len(result.top_papers)} 篇相关论文")
    """

    def __init__(
        self,
        *,
        client: DeepseekClient | None = None,
        search_manager: SearchManager | None = None,
        planner: QueryPlanner | None = None,
        rewriter: QueryRewriter | None = None,
        merger: PaperMerger | None = None,
        reranker: PaperReranker | None = None,
        downloader: PaperDownloader | None = None,
    ):
        """
        Args:
            client: DeepseekClient 实例，所有 LLM 服务共享。
            search_manager: SearchManager 实例。
            planner/rewriter/merger/reranker/downloader:
                各步骤服务，未指定则使用默认实例。
                注意: planner/rewriter/reranker 共享同一个 client。
        """
        _client = client or DeepseekClient()

        self.planner = planner or QueryPlanner(_client)
        self.rewriter = rewriter or QueryRewriter(_client)
        self.search_manager = search_manager or SearchManager()
        self.merger = merger or PaperMerger()
        self.reranker = reranker or PaperReranker(_client)
        self.downloader = downloader or PaperDownloader()

    # ── 主入口 ──────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        *,
        search_limit: int = _DEFAULT_SEARCH_LIMIT,
        download_top: int = _DEFAULT_DOWNLOAD_TOP,
        download_concurrent: int = _DEFAULT_DOWNLOAD_CONCUR,
    ) -> PipelineResult:
        """执行完整流水线。

        Args:
            query: 用户自然语言查询。
            search_limit: 每条改写 query 在每个源的返回数量。
            download_top: 下载排名前 N 篇论文的 PDF。
            download_concurrent: 批量下载最大并发数。

        Returns:
            PipelineResult — 包含所有步骤状态与输出。
        """
        logger.info("=" * 60)
        logger.info("AutoPaper Pipeline 启动")
        logger.info("Query: %s", query)
        logger.info("=" * 60)

        t_start = time.perf_counter()
        result = PipelineResult(query=query, success=False)

        # ── Step 1: Plan ──────────────────────────────────────────
        plan = await self._step_plan(query, result)

        # ── Step 2: Rewrite ────────────────────────────────────────
        rewrite = await self._step_rewrite(plan, query, result)

        # ── Step 3: Search ─────────────────────────────────────────
        all_papers = await self._step_search(rewrite, query, result, search_limit)

        # ── Step 4: Merge ──────────────────────────────────────────
        merged_papers = await self._step_merge(all_papers, result)

        # ── Step 5: Rerank ─────────────────────────────────────────
        scored_items = await self._step_rerank(merged_papers, query, result)

        # ── Step 6: Download ───────────────────────────────────────
        await self._step_download(
            merged_papers, scored_items, result,
            top=download_top,
            concurrent=download_concurrent,
        )

        # ── 汇总 ───────────────────────────────────────────────────
        elapsed = time.perf_counter() - t_start
        result.success = len(result.papers) > 0
        logger.info(
            "Pipeline 完成 — 耗时 %.2fs | 论文: %d 篇 | 下载: %s",
            elapsed,
            len(result.papers),
            f"{result.download.success_count}/{result.download.total}"
            if result.download else "跳过",
        )
        return result

    # ── Step 实现 — 每个 step 独立 try-except，返回默认值兜底 ───

    async def _step_plan(
        self, query: str, result: PipelineResult,
    ) -> QueryPlan | None:
        """Step 1: 查询结构化。"""
        t0 = time.perf_counter()
        logger.info("[Step 1/6] Planner — 分析查询意图...")

        try:
            plan = await self.planner.plan(query)
            result.plan = plan
            self._add_step(result, "plan", True, t0)
            logger.info(
                "[Step 1/6] 完成 — 主题: %s | 子问题: %d",
                plan.research_topic, len(plan.sub_queries),
            )
            return plan
        except QueryPlannerError as exc:
            logger.warning("[Step 1/6] 失败: %s", exc)
            self._add_step(result, "plan", False, t0, str(exc))
            return None

    async def _step_rewrite(
        self,
        plan: QueryPlan | None,
        query: str,
        result: PipelineResult,
    ) -> RewriteResult | None:
        """Step 2: 查询改写。"""
        t0 = time.perf_counter()
        logger.info("[Step 2/6] Rewriter — 术语扩展与查询改写...")

        if plan is None:
            logger.warning("[Step 2/6] 跳过 — Planner 失败，无 QueryPlan 输入")
            self._add_step(result, "rewrite", False, t0, "上游 Planner 失败")
            return None

        try:
            rewrite = await self.rewriter.rewrite(plan)
            result.rewrite = rewrite
            self._add_step(result, "rewrite", True, t0)
            logger.info(
                "[Step 2/6] 完成 — 生成 %d 条扩展查询 | 近义词组: %d",
                len(rewrite.expanded_queries), len(rewrite.synonyms),
            )
            return rewrite
        except QueryRewriteError as exc:
            logger.warning("[Step 2/6] 失败: %s", exc)
            self._add_step(result, "rewrite", False, t0, str(exc))
            return None

    async def _step_search(
        self,
        rewrite: RewriteResult | None,
        query: str,
        result: PipelineResult,
        limit: int,
    ) -> list[Paper]:
        """Step 3: 多源并行搜索。"""
        t0 = time.perf_counter()
        logger.info("[Step 3/6] Search — 多源并行搜索...")

        # 确定搜索 queries — 优先使用改写结果
        if rewrite and rewrite.expanded_queries:
            search_queries = [eq.query for eq in rewrite.expanded_queries]
        else:
            search_queries = [query]

        logger.info(
            "[Step 3/6] 共 %d 条搜索 query (limit=%d/源)",
            len(search_queries), limit,
        )

        try:
            search_results = await self.search_manager.search_multi(
                search_queries, limit=limit,
            )

            # 汇总所有 query 的论文
            all_papers: list[Paper] = []
            for q, papers in search_results.items():
                all_papers.extend(papers)

            self._add_step(result, "search", True, t0)
            logger.info(
                "[Step 3/6] 完成 — 共返回 %d 篇（含重复）",
                len(all_papers),
            )
            return all_papers
        except Exception as exc:
            logger.warning("[Step 3/6] 失败: %s", exc)
            self._add_step(result, "search", False, t0, str(exc))
            return []

    async def _step_merge(
        self,
        papers: list[Paper],
        result: PipelineResult,
    ) -> list[Paper]:
        """Step 4: 去重融合。"""
        t0 = time.perf_counter()
        logger.info("[Step 4/6] Merge — 论文去重融合（输入 %d 篇）...", len(papers))

        if not papers:
            logger.warning("[Step 4/6] 跳过 — 无论文可合并")
            self._add_step(result, "merge", False, t0, "上游 Search 无结果")
            return []

        try:
            merged = self.merger.merge(papers)
            result.papers = merged
            self._add_step(result, "merge", True, t0)
            logger.info(
                "[Step 4/6] 完成 — %d 篇 → %d 篇（去重率 %.1f%%）",
                len(papers), len(merged),
                (1 - len(merged) / len(papers)) * 100 if papers else 0,
            )
            return merged
        except Exception as exc:
            logger.warning("[Step 4/6] 失败: %s，使用原始列表", exc)
            self._add_step(result, "merge", False, t0, str(exc))
            result.papers = papers  # 降级：直接用未合并的
            return papers

    async def _step_rerank(
        self,
        papers: list[Paper],
        query: str,
        result: PipelineResult,
    ) -> list[ScoredItem]:
        """Step 5: 相关性排序。"""
        t0 = time.perf_counter()
        logger.info("[Step 5/6] Rerank — 相关性评分排序（%d 篇）...", len(papers))

        if not papers:
            logger.warning("[Step 5/6] 跳过 — 无论文可排序")
            self._add_step(result, "rerank", False, t0, "上游无论文")
            return []

        try:
            scored = await self.reranker.rerank(query, papers)
            result.scored_items = scored
            self._add_step(result, "rerank", True, t0)

            if scored:
                logger.info(
                    "[Step 5/6] 完成 — Top 3: %s",
                    ", ".join(
                        f"[{s.score}] {papers[s.paper_index].title[:40]}..."
                        if s.paper_index < len(papers) else f"[{s.score}]"
                        for s in scored[:3]
                    ),
                )
            return scored
        except RerankError as exc:
            logger.warning("[Step 5/6] 失败: %s", exc)
            self._add_step(result, "rerank", False, t0, str(exc))
            return []

    async def _step_download(
        self,
        papers: list[Paper],
        scored_items: list[ScoredItem],
        result: PipelineResult,
        top: int,
        concurrent: int,
    ) -> None:
        """Step 6: PDF 下载。"""
        t0 = time.perf_counter()
        logger.info("[Step 6/6] Download — PDF 下载 (top %d)...", top)

        if not papers:
            logger.warning("[Step 6/6] 跳过 — 无论文可下载")
            self._add_step(result, "download", False, t0, "上游无论文")
            return

        # 确定要下载的论文 — 按评分排名取 top N
        target_titles: list[str] = []
        if scored_items:
            for item in scored_items[:top]:
                if item.paper_index < len(papers):
                    target_titles.append(papers[item.paper_index].title)
        else:
            # 无评分 → 按原始顺序取 top N
            target_titles = [p.title for p in papers[:top]]

        if not target_titles:
            logger.warning("[Step 6/6] 跳过 — 无有效标题")
            self._add_step(result, "download", False, t0, "无有效下载目标")
            return

        try:
            batch_result = await self.downloader.download_batch(
                target_titles, max_concurrent=concurrent,
            )
            result.download = batch_result
            self._add_step(result, "download", True, t0)
            logger.info(
                "[Step 6/6] 完成 — 成功: %d | 失败: %d",
                batch_result.success_count, batch_result.failure_count,
            )
        except Exception as exc:
            logger.warning("[Step 6/6] 失败: %s", exc)
            self._add_step(result, "download", False, t0, str(exc))

    # ── 工具方法 ────────────────────────────────────────────────

    @staticmethod
    def _add_step(
        result: PipelineResult,
        step: str,
        success: bool,
        t0: float,
        error: str = "",
    ) -> None:
        """向 result 追加一个步骤状态记录。"""
        duration_ms = (time.perf_counter() - t0) * 1000
        result.steps.append(StepStatus(
            step=step,
            success=success,
            error=error,
            duration_ms=round(duration_ms, 1),
        ))
