"""
download.py — 论文 PDF 下载服务

多渠道回退下载：Google Scholar → Semantic Scholar → arXiv

支持:
  - 单篇 / 批量异步下载
  - 失败自动重试（指数退避）
  - 结构化 DownloadResult 状态返回
"""

from __future__ import annotations

import asyncio
import os
import re
from difflib import SequenceMatcher
from typing import Tuple
from xml.etree import ElementTree

import requests

from app.core.config import settings
from app.models.download_result import BatchDownloadResult, DownloadResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 文件名安全清洗
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')


class DownloadError(Exception):
    """下载异常基类。"""


def _read_key_from_json(key_name: str) -> str:
    """从项目根目录 API_key/API_key.json 读取 Key 作为兜底。

    模块级函数，供 PaperDownloader 和 DeepseekClient 共用。
    """
    try:
        import json
        from pathlib import Path

        json_path = (
            Path(__file__).resolve().parents[2] / ".." / "API_key" / "API_key.json"
        ).resolve()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(key_name, "")
    except Exception:
        return ""


class PaperDownloader:
    """论文 PDF 下载器 — 多渠道回退 + 重试 + 批量。

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
        """
        Args:
            save_dir: 保存目录，默认从 settings.download_dir 读取。
            max_retries: 单篇下载最大重试次数。
        """
        self.save_dir = save_dir or str(settings.download_dir)
        self.max_retries = max_retries
        os.makedirs(self.save_dir, exist_ok=True)

    # ── 公开方法 ────────────────────────────────────────────────

    async def download_one(self, paper_title: str) -> DownloadResult:
        """下载单篇论文 PDF，失败自动重试。

        Args:
            paper_title: 论文标题。

        Returns:
            DownloadResult 实例。
        """
        logger.info("下载: %s", paper_title[:80])

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                ok, file_path, channel = await asyncio.to_thread(
                    self._download_sync, paper_title
                )
                if ok:
                    logger.info("下载成功 [%s]: %s", channel, file_path)
                    return DownloadResult(
                        paper_title=paper_title,
                        success=True,
                        file_path=file_path,
                        source_channel=channel,
                        retries_used=attempt,
                    )
                last_error = file_path  # 失败时 file_path 实际是 error msg
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.max_retries:
                delay = 2 ** attempt
                logger.warning(
                    "下载失败（%d/%d），%ds 后重试: %s",
                    attempt + 1, self.max_retries, delay, paper_title[:60],
                )
                await asyncio.sleep(delay)

        logger.error("下载重试耗尽: %s — %s", paper_title[:60], last_error)
        return DownloadResult(
            paper_title=paper_title,
            success=False,
            error=last_error,
            retries_used=self.max_retries,
        )

    async def download_batch(
        self,
        titles: list[str],
        max_concurrent: int = 3,
    ) -> BatchDownloadResult:
        """批量下载论文 PDF，并发控制。

        Args:
            titles: 论文标题列表。
            max_concurrent: 最大并发数。

        Returns:
            BatchDownloadResult 汇总。
        """
        logger.info("批量下载: %d 篇 (并发: %d)", len(titles), max_concurrent)

        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded(title: str) -> DownloadResult:
            async with semaphore:
                return await self.download_one(title)

        tasks = [bounded(t) for t in titles]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        logger.info(
            "批量下载完成 — 成功: %d | 失败: %d | 总计: %d",
            success_count, failure_count, len(results),
        )

        return BatchDownloadResult(
            total=len(results),
            success_count=success_count,
            failure_count=failure_count,
            results=list(results),
        )

    # ── 核心下载逻辑（同步，从 Auto_download.py 适配）────────────

    def _download_sync(self, paper_title: str) -> Tuple[bool, str, str]:
        """同步下载核心 — 多渠道回退。

        Returns:
            (success, file_path_or_error, channel_name)
        """
        safe_title = _ILLEGAL_CHARS.sub('_', paper_title)[:80]
        file_path = os.path.join(self.save_dir, f"{safe_title}.pdf")

        pdf_url = ""
        channel = ""

        # ── Channel 1: Google Scholar (SerpAPI) ──────────────────
        api_key = settings.serpapi_api_key or _read_key_from_json("serpapi")
        if api_key:
            try:
                from serpapi import GoogleSearch

                search = GoogleSearch({
                    "engine": "google_scholar",
                    "q": paper_title,
                    "api_key": api_key,
                    "hl": "en",
                    "num": 1,
                })
                results = search.get_dict()
                organic_results = results.get("organic_results", [])

                if organic_results:
                    paper = organic_results[0]
                    matched_title = paper.get("title", "")
                    similarity = SequenceMatcher(
                        None, paper_title.lower(), matched_title.lower()
                    ).ratio()

                    if similarity >= 0.6:
                        logger.debug("[Google Scholar] 匹配: %s (%.2f)", matched_title[:70], similarity)

                        for res in paper.get("resources", []):
                            if res.get("file_format", "").upper() == "PDF":
                                pdf_url = res.get("link", "")
                                if pdf_url:
                                    channel = "google_scholar"
                                    break

                        if not pdf_url:
                            direct_link = paper.get("link", "")
                            if "arxiv.org/abs/" in direct_link:
                                pdf_url = direct_link.replace("/abs/", "/pdf/") + ".pdf"
                                channel = "google_scholar"
                            elif "arxiv.org/pdf/" in direct_link:
                                pdf_url = direct_link
                                channel = "google_scholar"
                    else:
                        logger.debug(
                            "[Google Scholar] 标题不匹配 (%.2f)，跳过", similarity
                        )
            except Exception as exc:
                logger.debug("[Google Scholar] 异常: %s", exc)

        # ── Channel 2: Semantic Scholar ──────────────────────────
        if not pdf_url:
            logger.debug("[Semantic Scholar] 搜索中...")
            pdf_url = self._try_semantic_scholar(paper_title)
            if pdf_url:
                channel = "semantic_scholar"

        # ── Channel 3: arXiv ─────────────────────────────────────
        if not pdf_url:
            logger.debug("[arXiv] 搜索中...")
            pdf_url = self._try_arxiv(paper_title)
            if pdf_url:
                channel = "arxiv"

        # ── 无可用链接 ───────────────────────────────────────────
        if not pdf_url:
            return (
                False,
                f"所有渠道均未找到可下载的 PDF: '{paper_title[:80]}'",
                "",
            )

        # ── 执行下载 ─────────────────────────────────────────────
        return self._do_download(pdf_url, file_path, channel)

    @staticmethod
    def _try_semantic_scholar(title: str) -> str:
        """通过 Semantic Scholar API 查找 PDF 链接。"""
        try:
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": title,
                    "limit": 3,
                    "fields": "title,openAccessPdf,isOpenAccess",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for paper in data.get("data", []):
                s2_title = paper.get("title", "")
                sim = SequenceMatcher(
                    None, title.lower(), s2_title.lower()
                ).ratio()
                if sim >= 0.6 and paper.get("isOpenAccess"):
                    pdf_info = paper.get("openAccessPdf", {})
                    pdf_url = pdf_info.get("url", "")
                    if pdf_url:
                        logger.debug(
                            "[Semantic Scholar] 匹配: %s (%.2f)",
                            s2_title[:70], sim,
                        )
                        return pdf_url
        except Exception:
            pass
        return ""

    @staticmethod
    def _try_arxiv(title: str) -> str:
        """通过 arXiv API 搜索并返回 PDF 链接。"""
        try:
            resp = requests.get(
                "http://export.arxiv.org/api/query",
                params={
                    "search_query": f"ti:{title}",
                    "max_results": 3,
                },
                timeout=15,
            )
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                arxiv_title_el = entry.find("atom:title", ns)
                arxiv_title = (
                    arxiv_title_el.text.strip().replace("\n", " ")
                    if arxiv_title_el is not None and arxiv_title_el.text
                    else ""
                )
                sim = SequenceMatcher(
                    None, title.lower(), arxiv_title.lower()
                ).ratio()
                if sim >= 0.6:
                    for link in entry.findall("atom:link", ns):
                        if link.get("title") == "pdf":
                            pdf_url = link.get("href", "")
                            if pdf_url:
                                logger.debug(
                                    "[arXiv] 匹配: %s (%.2f)",
                                    arxiv_title[:70], sim,
                                )
                                return pdf_url
        except Exception:
            pass
        return ""

    @staticmethod
    def _do_download(
        pdf_url: str,
        file_path: str,
        channel: str,
    ) -> Tuple[bool, str, str]:
        """执行 PDF 下载并校验。

        Returns:
            (success, file_path_or_error, channel)
        """
        try:
            logger.debug("下载: %s", pdf_url[:100])
            resp = requests.get(pdf_url, timeout=60, stream=True)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type:
                return (False, f"下载链接返回网页而非 PDF: {pdf_url[:100]}", channel)

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = os.path.getsize(file_path)
            if file_size < 10000:
                os.remove(file_path)
                return (
                    False,
                    f"下载文件过小 ({file_size} bytes)，可能不是有效 PDF",
                    channel,
                )

            return (True, file_path, channel)
        except requests.exceptions.RequestException as exc:
            return (False, f"下载失败: {exc}", channel)
