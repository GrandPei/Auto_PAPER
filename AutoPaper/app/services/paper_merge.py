"""
paper_merge.py — 论文融合模块

将多个搜索源的 Paper 按 DOI / Title / URL 去重合并，
保留各来源的最优字段（最长摘要、最大引用数、合并作者等）。

核心流程:
    list[Paper] → 分组(DOI|Title|URL) → 逐组合并 → 排序 → list[Paper]
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Iterable

from app.models.paper import Paper
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 标题规范化时忽略的无意义词
_STOP_WORDS: set[str] = {
    "a", "an", "the", "and", "or", "of", "in", "on", "to",
    "for", "with", "is", "are", "was", "were", "be", "been",
}


class PaperMerger:
    """论文融合器 — 多源 Paper 去重与字段合并。

    用法::

        merger = PaperMerger()
        merged = merger.merge(papers_from_multiple_sources)
    """

    # ── 公开方法 ────────────────────────────────────────────────

    def merge(self, papers: Iterable[Paper]) -> list[Paper]:
        """对论文列表做去重合并。

        匹配策略（按优先级）:
          1. DOI 精确匹配
          2. URL 精确匹配
          3. 规范化 Title 匹配（容错空格/标点/大小写）

        合并规则:
          - title: 保留最长版本
          - authors: 取并集，按首次出现顺序
          - year: 保留第一个非 None 值
          - abstract: 保留最长版本
          - citation_count: 保留最大值
          - venue: 保留最长版本
          - url: 保留第一个非空值
          - doi: 保留第一个非空值
          - source: 合并所有来源（逗号分隔）

        Args:
            papers: 待合并的 Paper 可迭代对象。

        Returns:
            去重合并后的 Paper 列表，按引用数降序排列。
        """
        paper_list = list(papers)
        if not paper_list:
            return []

        logger.info("开始论文融合 — 输入 %d 篇", len(paper_list))

        groups = self._group_papers(paper_list)
        merged = [self._merge_group(g) for g in groups.values()]

        # 按引用数降序
        merged.sort(key=lambda p: p.citation_count, reverse=True)

        logger.info(
            "论文融合完成 — %d 篇 → %d 篇（去重率 %.1f%%）",
            len(paper_list),
            len(merged),
            (1 - len(merged) / len(paper_list)) * 100,
        )
        return merged

    # ── 分组逻辑 ────────────────────────────────────────────────

    @staticmethod
    def _group_papers(papers: list[Paper]) -> OrderedDict[str, list[Paper]]:
        """将论文按 DOI / URL / Title 分组。

        返回 OrderedDict 保持插入顺序。
        """
        groups: OrderedDict[str, list[Paper]] = OrderedDict()

        for paper in papers:
            key = PaperMerger._resolve_key(paper, groups)
            if key in groups:
                groups[key].append(paper)
            else:
                groups[key] = [paper]

        return groups

    @staticmethod
    def _resolve_key(
        paper: Paper,
        existing_groups: OrderedDict[str, list[Paper]],
    ) -> str:
        """为 paper 确定分组键。

        优先按 DOI → URL → 规范化 Title 匹配已有分组。
        若均不匹配，以 DOI > URL > title 为自身的分组键。
        """
        # 1. DOI 匹配
        if paper.doi:
            doi_key = f"doi:{paper.doi.lower()}"
            if doi_key in existing_groups:
                return doi_key
            return doi_key

        # 2. URL 匹配
        if paper.url:
            url_key = f"url:{paper.url.rstrip('/')}"
            if url_key in existing_groups:
                return url_key

        # 3. 规范化 Title 匹配
        norm_title = PaperMerger._normalize_title(paper.title)
        if norm_title:
            for existing_key, group in existing_groups.items():
                for member in group:
                    if PaperMerger._normalize_title(member.title) == norm_title:
                        return existing_key

        # 4. 都不匹配 → 以规范化 title 新建分组
        if paper.url:
            return url_key
        if norm_title:
            return f"title:{norm_title}"
        # 兜底：用对象 id（确保不与其他 paper 合并）
        return f"id:{id(paper)}"

    # ── 合并逻辑 ────────────────────────────────────────────────

    @staticmethod
    def _merge_group(group: list[Paper]) -> Paper:
        """将一个分组内的多篇 Paper 合并为一条。"""
        if len(group) == 1:
            return group[0]

        # 按引用数降序排列论文，使高引用版本优先
        sorted_group = sorted(group, key=lambda p: p.citation_count, reverse=True)

        # title: 最长非空
        title = PaperMerger._best_str(
            sorted_group, key=lambda p: p.title, strategy="longest"
        )

        # authors: 合并并去重
        authors = PaperMerger._merge_authors(sorted_group)

        # year: 第一个非 None
        year = PaperMerger._first_non_none(sorted_group, key=lambda p: p.year)

        # abstract: 最长
        abstract = PaperMerger._best_str(
            sorted_group, key=lambda p: p.abstract, strategy="longest"
        )

        # citation_count: 最大值
        citation_count = max(p.citation_count for p in sorted_group)

        # venue: 最长
        venue = PaperMerger._best_str(
            sorted_group, key=lambda p: p.venue, strategy="longest"
        )

        # url: 第一个非空
        url = PaperMerger._first_non_empty(sorted_group, key=lambda p: p.url)

        # doi: 第一个非空（优先选择更规范的长格式）
        doi = PaperMerger._best_str(
            sorted_group, key=lambda p: p.doi, strategy="longest"
        )

        # source: 合并所有来源
        sources = OrderedDict.fromkeys(
            p.source for p in sorted_group if p.source
        )
        source = "+".join(sources)

        return Paper(
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            citation_count=citation_count,
            venue=venue,
            url=url,
            doi=doi,
            source=source,
        )

    # ── 工具方法 ────────────────────────────────────────────────

    @staticmethod
    def _normalize_title(title: str) -> str:
        """规范化标题用于模糊匹配。

        处理: 小写 → 去首尾空白 → 压缩空格 → 移除无意义词。
        """
        if not title:
            return ""
        text = title.lower().strip()
        text = re.sub(r"\s+", " ", text)
        text = text.rstrip(".,;:!?")

        # 移除无意义词（可选，对短标题跳过以避免过度压缩）
        words = text.split()
        if len(words) > 3:
            words = [w for w in words if w not in _STOP_WORDS]
        text = " ".join(words)

        return text

    @staticmethod
    def _best_str(
        papers: list[Paper],
        key,
        strategy: str = "longest",
    ) -> str:
        """从多篇论文中选出最优字符串字段。

        Args:
            papers: 已排序的论文列表（最优在前）。
            key: 字段提取函数，如 lambda p: p.title。
            strategy: "longest"（最长）或 "first"（第一个非空）。

        Returns:
            选出的字符串。
        """
        best = ""
        for p in papers:
            val = key(p).strip()
            if not val:
                continue
            if strategy == "first":
                return val
            if len(val) > len(best):
                best = val
        return best

    @staticmethod
    def _first_non_none(papers: list[Paper], key):
        """返回第一个非 None 的字段值。"""
        for p in papers:
            val = key(p)
            if val is not None:
                return val
        return None

    @staticmethod
    def _first_non_empty(papers: list[Paper], key) -> str:
        """返回第一个非空字符串字段值。"""
        for p in papers:
            val = key(p).strip()
            if val:
                return val
        return ""

    @staticmethod
    def _merge_authors(papers: list[Paper]) -> list[str]:
        """合并多个论文的作者列表，去重并保持大致顺序。

        策略: 优先保留引用数最高版本的作者顺序，
        然后将其他版本的新作者追加到末尾。
        """
        seen: set[str] = set()
        merged: list[str] = []

        for p in papers:
            for author in p.authors:
                # 小写比较去重
                key = author.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(author)

        return merged
