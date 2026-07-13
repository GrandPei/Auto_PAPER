"""
manager.py — 搜索管理器

协调多搜索源并行查询，汇总统一结果。

核心流程:
    多个 query → 多个 source 并行 → 去重 → 排序 → list[Paper]
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from app.models.paper import Paper
from app.search.arxiv import ArxivSearcher
from app.search.base import BaseSearcher, SearchError
from app.search.openalex import OpenAlexSearcher
from app.search.semantic_scholar import SemanticScholarSearcher
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SearchManager:
    """搜索协调器 — 并行调度多个搜索源，汇总结论。

    用法::

        manager = SearchManager()
        papers = await manager.search_all("graph neural networks", limit=10)

        # 也可以对多条查询分别搜索
        results = await manager.search_multi(
            ["GNN drug discovery", "molecular graph representation"],
            limit=5,
        )
    """

    def __init__(self, *searchers: BaseSearcher):
        """
        Args:
            searchers: BaseSearcher 实例。若未指定，则默认注册全部三个源。
        """
        self._searchers: list[BaseSearcher] = list(searchers) if searchers else [
            SemanticScholarSearcher(),
            OpenAlexSearcher(),
            ArxivSearcher(),
        ]

    # ── 公开方法 ────────────────────────────────────────────────

    async def search_all(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Paper]:
        """对所有搜索源并行执行同一查询。

        Args:
            query: 搜索查询字符串。
            limit: 每个源的返回数量上限。

        Returns:
            去重合并后的 Paper 列表，按引用数降序排列。
        """
        logger.info("并行搜索 %d 个源: %s", len(self._searchers), query)

        tasks = [s.search(query, limit=limit) for s in self._searchers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_papers: list[Paper] = []
        for searcher, result in zip(self._searchers, results):
            if isinstance(result, Exception):
                logger.warning(
                    "[%s] 搜索失败: %s",
                    searcher.source_name,
                    result,
                )
            else:
                all_papers.extend(result)

        merged = self._deduplicate(all_papers)
        logger.info(
            "并行搜索完成 — 共 %d 条（去重后 %d 条）",
            len(all_papers),
            len(merged),
        )
        return merged

    async def search_multi(
        self,
        queries: list[str],
        limit: int = 10,
    ) -> dict[str, list[Paper]]:
        """对多条查询分别执行并行搜索。

        Args:
            queries: 搜索查询字符串列表。
            limit: 每个查询在每个源的返回数量上限。

        Returns:
            {query: [Paper, ...]} 映射。
        """
        logger.info("多查询搜索: %d 条 query", len(queries))

        tasks = {q: self.search_all(q, limit=limit) for q in queries}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)

        result: dict[str, list[Paper]] = {}
        for query, papers in zip(tasks.keys(), gathered):
            if isinstance(papers, Exception):
                logger.warning("查询 [%s] 搜索失败: %s", query[:60], papers)
                result[query] = []
            else:
                result[query] = papers

        return result

    @property
    def searchers(self) -> list[BaseSearcher]:
        """已注册的搜索源列表。"""
        return list(self._searchers)

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(papers: list[Paper]) -> list[Paper]:
        """按 DOI / title 去重，保留引用数最高的版本，按引用数降序排列。

        去重优先级: DOI > 规范化 title。
        """
        # 第一轮: 按 DOI 去重
        doi_map: OrderedDict[str, Paper] = OrderedDict()
        no_doi: list[Paper] = []

        for p in papers:
            if p.doi:
                existing = doi_map.get(p.doi)
                if existing is None or p.citation_count > existing.citation_count:
                    doi_map[p.doi] = p
            else:
                no_doi.append(p)

        # 第二轮: 无 DOI 的按规范化 title 去重
        seen_titles: set[str] = set()
        title_deduped: list[Paper] = []

        for p in no_doi:
            key = SearchManager._normalize_title(p.title)
            if key not in seen_titles:
                seen_titles.add(key)
                title_deduped.append(p)
            else:
                # 标题相同但已有更高引用的记录则替换
                for existing in title_deduped:
                    if SearchManager._normalize_title(existing.title) == key:
                        if p.citation_count > existing.citation_count:
                            title_deduped.remove(existing)
                            title_deduped.append(p)
                        break

        # 合并并排序
        merged = list(doi_map.values()) + title_deduped
        merged.sort(
            key=lambda p: (p.citation_count, p.year or 0),
            reverse=True,
        )
        return merged

    @staticmethod
    def _normalize_title(title: str) -> str:
        """规范化标题用于去重比较。"""
        return title.lower().strip().rstrip(".")
