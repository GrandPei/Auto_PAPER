"""
arxiv.py — ArXiv 搜索引擎

API: https://export.arxiv.org/api/query

特点:
  - 免费，无需 API Key
  - 返回 Atom XML，需手动解析
  - 速率限制: 单次请求间隔 >= 3 秒（有礼貌即可）
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from app.models.paper import Paper
from app.search.base import BaseSearcher, SearchError
from app.utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://export.arxiv.org/api/query"

# Atom XML 命名空间
_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"


class ArxivSearcher(BaseSearcher):
    """ArXiv 异步搜索客户端。"""

    @property
    def source_name(self) -> str:
        return "arxiv"

    async def search(self, query: str, limit: int = 10) -> list[Paper]:
        """通过 ArXiv API 搜索论文。

        Args:
            query: 搜索查询词（支持 ArXiv 查询语法）。
            limit: 返回数量（最大 100）。

        Returns:
            Paper 对象列表。
        """
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 100),
            "sortBy": "relevance",
        }

        logger.debug("ArXiv 搜索: %s (limit=%d)", query, limit)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(_BASE_URL, params=params)

        if response.status_code != 200:
            raise SearchError(
                f"ArXiv API 返回 {response.status_code}: "
                f"{response.text[:500]}",
                source=self.source_name,
            )

        papers = self._parse_atom(response.text)
        logger.info("ArXiv 返回 %d 条结果", len(papers))
        return papers

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _parse_atom(xml_text: str) -> list[Paper]:
        """解析 ArXiv Atom XML 响应。"""
        # 注册命名空间，否则 find/findall 需要带 {ns} 前缀
        ns = {"atom": _ATOM_NS, "arxiv": _ARXIV_NS}

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise SearchError(
                f"ArXiv XML 解析失败: {exc}", source="arxiv"
            ) from exc

        entries = root.findall("atom:entry", ns)
        papers: list[Paper] = []

        for entry in entries:
            try:
                papers.append(ArxivSearcher._entry_to_paper(entry, ns))
            except Exception:
                logger.debug("跳过无法解析的 ArXiv 条目", exc_info=True)

        return papers

    @staticmethod
    def _entry_to_paper(entry: ET.Element, ns: dict) -> Paper:
        """解析单个 Atom entry → Paper。"""

        # 标题
        title_el = entry.find("atom:title", ns)
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""

        # 摘要
        summary_el = entry.find("atom:summary", ns)
        abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else ""

        # 作者
        authors: list[str] = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # 发表年份 — 从 published / updated 中提取
        year: int | None = None
        published_el = entry.find("atom:published", ns)
        if published_el is not None and published_el.text:
            try:
                year = datetime.fromisoformat(
                    published_el.text.replace("Z", "+00:00")
                ).year
            except (ValueError, TypeError):
                pass

        # URL / ID
        url = ""
        id_el = entry.find("atom:id", ns)
        if id_el is not None and id_el.text:
            url = id_el.text.strip()

        # DOI — 从 id URL 或 arxiv:doi 提取
        doi = ""
        doi_el = entry.find("arxiv:doi", ns)
        if doi_el is not None and doi_el.text:
            doi = doi_el.text.strip()

        # 期刊引用
        journal_el = entry.find("arxiv:journal_ref", ns)
        venue = ""
        if journal_el is not None and journal_el.text:
            venue = journal_el.text.strip()

        # ArXiv 没有 citation_count，保持默认 0

        return Paper(
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            citation_count=0,
            venue=venue,
            url=url,
            doi=doi,
            source="arxiv",
        )
