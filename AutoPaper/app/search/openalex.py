"""
openalex.py — OpenAlex 搜索引擎

API: https://api.openalex.org/works

特点:
  - 完全免费，无需 API Key
  - 推荐填写邮箱以获得更好的速率限制
  - 摘要以 inverted index 格式返回，需重建
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.models.paper import Paper
from app.search.base import BaseSearcher, SearchError
from app.utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.openalex.org"


class OpenAlexSearcher(BaseSearcher):
    """OpenAlex 异步搜索客户端。"""

    @property
    def source_name(self) -> str:
        return "openalex"

    async def search(self, query: str, limit: int = 10) -> list[Paper]:
        """通过 OpenAlex API 搜索论文。

        Args:
            query: 搜索查询词。
            limit: 返回数量（最大 200）。

        Returns:
            Paper 对象列表。
        """
        url = f"{_BASE_URL}/works"
        headers: dict = {"Accept": "application/json"}

        # 礼貌邮箱
        email = settings.openalex_email
        if email:
            headers["mailto"] = email

        params = {
            "search": query,
            "per_page": min(limit, 200),
        }

        logger.debug("OpenAlex 搜索: %s (limit=%d)", query, limit)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code != 200:
            raise SearchError(
                f"OpenAlex API 返回 {response.status_code}: "
                f"{response.text[:500]}",
                source=self.source_name,
            )

        data = response.json()
        papers = [self._to_paper(item) for item in data.get("results", [])]
        logger.info("OpenAlex 返回 %d 条结果", len(papers))
        return papers

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _to_paper(item: dict) -> Paper:
        """将 API 响应条目转为 Paper 模型。"""
        # 作者
        authors = []
        for authorship in item.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        # 发表年份
        year = item.get("publication_year")

        # 摘要重建
        abstract = OpenAlexSearcher._rebuild_abstract(
            item.get("abstract_inverted_index")
        )

        # 引用数
        citation_count = item.get("cited_by_count", 0)

        # 期刊/会议
        primary_location = item.get("primary_location") or {}
        source_info = primary_location.get("source") or {}
        venue = source_info.get("display_name", "")

        # URL
        url = item.get("open_access", {}).get("oa_url", "")
        if not url:
            url = primary_location.get("landing_page_url", "")

        # DOI
        doi = item.get("doi", "")

        return Paper(
            title=item.get("title", ""),
            authors=authors,
            year=year,
            abstract=abstract,
            citation_count=citation_count,
            venue=venue,
            url=url,
            doi=doi,
            source="openalex",
        )

    @staticmethod
    def _rebuild_abstract(inverted_index: dict | None) -> str:
        """从 OpenAlex 的 inverted index 格式重建摘要文本。

        inverted_index 格式:
            {"word1": [pos0, pos5], "word2": [pos1], ...}

        还原为按位置排序的纯文本。
        """
        if not inverted_index:
            return ""

        # 收集所有 (position, word) 对
        positioned: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                positioned.append((pos, word))

        # 按位置排序
        positioned.sort(key=lambda x: x[0])

        return " ".join(word for _, word in positioned)
