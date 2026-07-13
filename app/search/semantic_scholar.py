"""
semantic_scholar.py — Semantic Scholar 搜索引擎

API: https://api.semanticscholar.org/graph/v1/paper/search

速率限制:
  - 无 API Key: 100 次 / 5 分钟
  - 有 API Key: 提升至更高额度
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.models.paper import Paper
from app.search.base import BaseSearcher, SearchError
from app.utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = (
    "title,authors,year,abstract,citationCount,"
    "venue,url,externalIds,journal"
)


class SemanticScholarSearcher(BaseSearcher):
    """Semantic Scholar 异步搜索客户端。"""

    @property
    def source_name(self) -> str:
        return "semantic_scholar"

    async def search(self, query: str, limit: int = 10) -> list[Paper]:
        """通过 Semantic Scholar API 搜索论文。

        Args:
            query: 搜索查询词。
            limit: 返回数量（最大 100）。

        Returns:
            Paper 对象列表。
        """
        url = f"{_BASE_URL}/paper/search"
        headers: dict = {"Accept": "application/json"}

        # 可选 API Key
        api_key = settings.semantic_scholar_api_key
        if api_key:
            headers["x-api-key"] = api_key

        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": _FIELDS,
        }

        logger.debug("Semantic Scholar 搜索: %s (limit=%d)", query, limit)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code != 200:
            raise SearchError(
                f"Semantic Scholar API 返回 {response.status_code}: "
                f"{response.text[:500]}",
                source=self.source_name,
            )

        data = response.json()
        papers = [self._to_paper(item) for item in data.get("data", [])]
        logger.info("Semantic Scholar 返回 %d 条结果", len(papers))
        return papers

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _to_paper(item: dict) -> Paper:
        """将 API 响应条目转为 Paper 模型。"""
        authors = [a.get("name", "") for a in item.get("authors", [])]

        # 期刊/会议名
        venue = ""
        journal = item.get("journal") or {}
        venue = journal.get("name", "")
        if not venue:
            pub_venue = item.get("publicationVenue") or item.get("venue") or {}
            venue = pub_venue.get("name", "")

        # DOI
        external_ids = item.get("externalIds") or {}
        doi = external_ids.get("DOI", "")

        return Paper(
            title=item.get("title", ""),
            authors=authors,
            year=item.get("year"),
            abstract=item.get("abstract", ""),
            citation_count=item.get("citationCount", 0),
            venue=venue,
            url=item.get("url", ""),
            doi=doi,
            source="semantic_scholar",
        )
