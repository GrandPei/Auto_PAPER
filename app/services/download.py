"""download.py — competition-facing PDF download service.

This service integrates the validated ``paper_downloader`` academic OA mode
into the main AutoPaper app. It focuses on legal PDF acquisition and validation:
arXiv, OpenAlex, Semantic Scholar, and CrossRef are tried as academic sources;
Google Scholar is intentionally excluded from the default app path.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.download_result import BatchDownloadResult as AutoBatchResult
from app.models.download_result import DownloadResult as AutoDownloadResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DownloadError(Exception):
    """下载异常基类。"""


class PaperDownloader:
    """论文 PDF 下载器 — 面向赛题主项目的下载服务。

    默认使用 ``academic_oa``：
      - arXiv
      - OpenAlex
      - Semantic Scholar
      - CrossRef

    用法::

        downloader = PaperDownloader()
        result = await downloader.download_one("PaSa: An LLM Agent for Comprehensive Academic Paper Search")
        if result.success:
            print(f"已保存至: {result.file_path}")
    """

    def __init__(
        self,
        save_dir: str | None = None,
        max_retries: int = 3,
        engine: str = "academic_oa",
        timeout: int = 45,
    ):
        """初始化下载器。

        Args:
            save_dir: 保存目录，默认从 settings.download_dir 读取。
            max_retries: 单篇下载最大重试次数。
            engine: paper_downloader 极简接口的引擎模式，默认 academic_oa。
            timeout: 单次搜索/下载超时基准秒数。
        """
        self.save_dir = save_dir or str(settings.download_dir)
        self.max_retries = max_retries
        self.engine = engine
        self.timeout = timeout
        os.makedirs(self.save_dir, exist_ok=True)
        logger.info(
            "PaperDownloader 下载服务初始化完成，保存目录: %s, engine=%s",
            self.save_dir,
            self.engine,
        )

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
            status="failed_after_retries",
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

    # ── 核心下载逻辑 — 委托给 paper_downloader academic_oa ─────

    async def _async_download(self, paper_title: str) -> AutoDownloadResult:
        """异步执行合法开放全文下载，并映射为主项目下载结果。"""
        return await asyncio.to_thread(self._download_sync, paper_title)

    def _download_sync(self, paper_title: str) -> AutoDownloadResult:
        from paper_downloader.src.downloaders.base_downloader import Downloader
        from paper_downloader.src.downloaders.pdf_processor import PDFProcessor
        from paper_downloader.src.interface import download_pdf

        raw = download_pdf(
            title=paper_title,
            output_dir=self.save_dir,
            engine=self.engine,
            timeout=self.timeout,
            rename=True,
        )

        paper_info: dict[str, Any] = raw.get("paper_info") or {}
        file_path = str(raw.get("file_path") or "")
        path = Path(file_path) if file_path else None
        file_size = path.stat().st_size if path and path.exists() else 0
        is_pdf_header = bool(path and Downloader.validate_pdf(path))
        is_pdf_deep = bool(path and Downloader.validate_pdf_deep(path))
        page_count = PDFProcessor.get_page_count(path) if path and path.exists() else None
        status = self._classify_status(
            success=bool(raw.get("success")),
            file_path=file_path,
            file_size=file_size,
            is_pdf_header=is_pdf_header,
            is_pdf_deep=is_pdf_deep,
            page_count=page_count,
            error=str(raw.get("error") or ""),
        )

        success = status in {"success_valid_pdf", "success_pdf_needs_review"}
        return AutoDownloadResult(
            paper_title=str(paper_info.get("title") or paper_title),
            success=success,
            file_path=file_path if success else "",
            error="" if success else str(raw.get("error") or status),
            retries_used=0,
            source_channel=str(raw.get("engine_used") or ""),
            status=status,
            file_size=file_size,
            page_count=page_count,
            doi=str(paper_info.get("doi") or ""),
            arxiv_id=str(paper_info.get("arxiv_id") or ""),
        )

    @staticmethod
    def _classify_status(
        *,
        success: bool,
        file_path: str,
        file_size: int,
        is_pdf_header: bool,
        is_pdf_deep: bool,
        page_count: int | None,
        error: str,
    ) -> str:
        if success and file_path and is_pdf_header and is_pdf_deep and (page_count or 0) > 0:
            return "success_valid_pdf"
        if success and file_path and is_pdf_header:
            return "success_pdf_needs_review"
        if success and file_path and not is_pdf_header:
            return "invalid_download_not_pdf"
        if "标题不匹配" in error or "not match" in error.lower():
            return "title_mismatch"
        if "未找到" in error or "not found" in error.lower():
            return "not_found"
        if "403" in error or "401" in error or "paywall" in error.lower() or "access" in error.lower():
            return "access_limited_or_paywalled"
        if "timeout" in error.lower() or "timed out" in error.lower():
            return "network_timeout"
        if "429" in error or "too many requests" in error.lower() or "rate limit" in error.lower():
            return "rate_limited"
        if file_size == 0 and file_path:
            return "empty_file"
        return "failed_needs_review"
