"""
download.py — 论文 PDF 下载服务

基于 PaperDownloader 企业级下载引擎：
  - 5 个 Provider 级联（OpenAlex → Semantic Scholar → arXiv → CrossRef → Unpaywall）
  - 智能标题匹配（RapidFuzz + Levenshtein）
  - 流式下载 + 进度条 + SHA256 校验
  - SQLite 缓存去重
  - JSON / BibTeX 元数据自动保存

支持:
  - 单篇 / 批量异步下载
  - 失败自动重试（指数退避）
  - 结构化 BatchDownloadResult 状态返回
"""

from __future__ import annotations

import asyncio
import os

from app.core.config import settings
from app.models.download_result import BatchDownloadResult as AutoBatchResult
from app.models.download_result import DownloadResult as AutoDownloadResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DownloadError(Exception):
    """下载异常基类。"""


class PaperDownloader:
    """论文 PDF 下载器 — 基于 PaperDownloader 引擎。

    底层使用 5 个 Provider 级联搜索 + 下载，相比旧版 Google Scholar 方案：
      - 不再依赖 SerpAPI 付费 API
      - 覆盖 OpenAlex、Semantic Scholar、arXiv、CrossRef、Unpaywall
      - 自动缓存，避免重复下载

    用法::

        downloader = PaperDownloader()
        result = await downloader.download_one("Attention Is All You Need")
        if result.success:
            print(f"已保存至: {result.file_path}")
    """

    def __init__(
        self,
        save_dir: str | None = None,
        max_retries: int = 3,
    ):
        """初始化下载器。

        Args:
            save_dir: 保存目录，默认从 settings.download_dir 读取。
            max_retries: 单篇下载最大重试次数。
        """
        self.save_dir = save_dir or str(settings.download_dir)
        self.max_retries = max_retries
        os.makedirs(self.save_dir, exist_ok=True)

        # 延迟导入，确保 paper_downloader 已安装
        from paper_downloader.config import get_settings as _get_pd_settings

        _pd_settings = _get_pd_settings()
        _pd_settings.download_dir = self.save_dir
        logger.info("PaperDownloader 引擎初始化完成，保存目录: %s", self.save_dir)

    # ── 公开方法 ────────────────────────────────────────────────

    async def download_one(self, paper_title: str) -> AutoDownloadResult:
        """下载单篇论文 PDF，失败自动重试。

        Args:
            paper_title: 论文标题。

        Returns:
            AutoDownloadResult 实例。
        """
        logger.info("下载: %s", paper_title[:80])

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                result = await self._async_download(paper_title)
                if result.success:
                    logger.info(
                        "下载成功 [%s]: %s",
                        result.source_channel,
                        result.file_path,
                    )
                    return result
                last_error = result.error
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.max_retries:
                delay = 2 ** attempt
                logger.warning(
                    "下载失败（%d/%d），%ds 后重试: %s",
                    attempt + 1,
                    self.max_retries,
                    delay,
                    paper_title[:60],
                )
                await asyncio.sleep(delay)

        logger.error("下载重试耗尽: %s — %s", paper_title[:60], last_error)
        return AutoDownloadResult(
            paper_title=paper_title,
            success=False,
            error=last_error,
            retries_used=self.max_retries,
        )

    async def download_batch(
        self,
        titles: list[str],
        max_concurrent: int = 3,
    ) -> AutoBatchResult:
        """批量下载论文 PDF，并发控制。

        Args:
            titles: 论文标题列表。
            max_concurrent: 最大并发数。

        Returns:
            AutoBatchResult 汇总。
        """
        logger.info("批量下载: %d 篇 (并发: %d)", len(titles), max_concurrent)

        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded(title: str) -> AutoDownloadResult:
            async with semaphore:
                return await self.download_one(title)

        tasks = [bounded(t) for t in titles]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        logger.info(
            "批量下载完成 — 成功: %d | 失败: %d | 总计: %d",
            success_count,
            failure_count,
            len(results),
        )

        return AutoBatchResult(
            total=len(results),
            success_count=success_count,
            failure_count=failure_count,
            results=list(results),
        )

    # ── 核心下载逻辑 — 委托给 PaperDownloader 引擎 ─────────────

    async def _async_download(self, paper_title: str) -> AutoDownloadResult:
        """异步执行 PaperDownloader API 下载。

        流程:
          1. 调用 download_paper_pdf(title) → 自动搜索 + 下载 + SHA256 校验
          2. 映射到 AutoPaper 的 DownloadResult 结构

        Args:
            paper_title: 论文标题。

        Returns:
            AutoDownloadResult
        """
        from paper_downloader import download_paper_pdf
        from paper_downloader.models import DownloadStatus

        pd_result = await download_paper_pdf(paper_title)

        # 映射 PaperDownloader 的 DownloadResult 到 AutoPaper 的 DownloadResult
        if pd_result.status in (DownloadStatus.SUCCESS, DownloadStatus.CACHED):
            return AutoDownloadResult(
                paper_title=pd_result.paper.title or paper_title,
                success=True,
                file_path=str(pd_result.pdf_path) if pd_result.pdf_path else "",
                retries_used=0,
                source_channel=pd_result.paper.provider.value,
            )
        else:
            return AutoDownloadResult(
                paper_title=paper_title,
                success=False,
                error=pd_result.error_message or f"下载失败: {pd_result.status.value}",
                retries_used=0,
            )
