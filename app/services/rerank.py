"""
rerank.py — 论文相关性排序模块

使用 Deepseek 对论文按查询相关性进行 0-100 评分并排序。

核心流程:
    query + list[Paper] → Deepseek (json_mode) → 逐篇评分 → 按 score 降序
"""

from __future__ import annotations

import json

from app.llm.deepseek_client import DeepseekClient, DeepseekError
from app.models.paper import Paper
from app.models.rank_result import RankResult, ScoredItem
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 单次 API 调用最大评估论文数
_MAX_PAPERS_PER_BATCH = 25

# ── 系统提示词 ──────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一个学术论文评审专家，需要根据用户查询对一批论文进行相关性评分。

## 评分维度

对每篇论文从以下三个维度综合评估：

1. **标题匹配度**: 标题是否包含查询的核心概念、同义词、相关术语。
2. **摘要匹配度**: 摘要的研究内容、方法、结论是否与查询方向一致。
3. **关键词覆盖度**: 论文主题词与查询关键词的重叠程度。

## 评分标准 (0-100)

- **90-100**: 高度相关 — 标题和摘要直接对应查询主题，核心概念完全匹配。
- **70-89**: 较相关 — 研究方向一致，部分概念匹配，有参考价值。
- **50-69**: 部分相关 — 领域相关但侧重点不同，或方法/对象有差异。
- **30-49**: 弱相关 — 同一大学科，但具体方向差异较大。
- **0-29**: 不相关 — 与查询主题基本无关，或仅个别术语巧合重合。

## 输出格式

严格按以下 JSON schema 输出，不要包含任何 Markdown 标记或额外解释：

{
  "scored_items": [
    {
      "paper_index": 0,
      "score": 85,
      "reason": "标题直接研究GNN在药物发现中的应用，摘要方法与查询高度一致"
    }
  ]
}
"""


class RerankError(Exception):
    """重排序异常。"""


class PaperReranker:
    """论文相关性排序器 — 使用 Deepseek 批量评分。

    用法::

        client = DeepseekClient()
        reranker = PaperReranker(client)

        scored = await reranker.rerank("GNN drug discovery", papers)
        for item in scored:
            print(f"[{item.score}] {papers[item.paper_index].title}")
    """

    def __init__(self, client: DeepseekClient | None = None):
        """
        Args:
            client: DeepseekClient 实例，若为 None 则自动创建。
        """
        self._client = client or DeepseekClient()

    # ── 公开方法 ────────────────────────────────────────────────

    async def rerank(
        self,
        query: str,
        papers: list[Paper],
    ) -> list[ScoredItem]:
        """对论文列表按查询相关性评分并排序。

        自动分批处理（每批最多 25 篇），最后合并排序。

        Args:
            query: 用户查询字符串。
            papers: 待评分的 Paper 列表。

        Returns:
            按 score 降序排列的 ScoredItem 列表。

        Raises:
            RerankError: Deepseek 调用失败或 JSON 解析/校验失败。
        """
        if not papers:
            logger.info("重排序 — 输入为空，直接返回")
            return []

        logger.info("重排序 — query: %s | 论文数: %d", query[:80], len(papers))

        # 分批处理
        batches = self._split_batches(papers)
        all_items: list[ScoredItem] = []

        for batch_idx, batch in enumerate(batches):
            if len(batches) > 1:
                logger.debug("处理第 %d/%d 批 (%d 篇)", batch_idx + 1, len(batches), len(batch))

            items = await self._score_batch(query, batch, offset=batch_idx * _MAX_PAPERS_PER_BATCH)
            all_items.extend(items)

        # 按 score 降序排列
        all_items.sort(key=lambda x: x.score, reverse=True)

        logger.info(
            "重排序完成 — 最高分: %d | 最低分: %d | 平均分: %.1f",
            all_items[0].score if all_items else 0,
            all_items[-1].score if all_items else 0,
            sum(i.score for i in all_items) / len(all_items) if all_items else 0,
        )
        return all_items

    # ── 分批逻辑 ────────────────────────────────────────────────

    @staticmethod
    def _split_batches(papers: list[Paper]) -> list[list[Paper]]:
        """将论文列表拆分为多批。"""
        if len(papers) <= _MAX_PAPERS_PER_BATCH:
            return [papers]

        batches = []
        for i in range(0, len(papers), _MAX_PAPERS_PER_BATCH):
            batches.append(papers[i:i + _MAX_PAPERS_PER_BATCH])
        return batches

    # ── 评分核心 ────────────────────────────────────────────────

    async def _score_batch(
        self,
        query: str,
        batch: list[Paper],
        offset: int = 0,
    ) -> list[ScoredItem]:
        """对一批论文调用 Deepseek 进行评分。"""
        user_message = self._serialize_batch(query, batch, offset)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self._client.chat(
                messages,
                temperature=0.1,
                max_tokens=4096,
                json_mode=True,
            )
        except DeepseekError as exc:
            raise RerankError(
                f"Deepseek 调用失败 (status={exc.status_code}): {exc}"
            ) from exc

        raw_text = self._extract_content(response)
        logger.debug("重排序 LLM 原始响应: %s", raw_text[:500])

        return self._parse(raw_text)

    # ── 序列化 ──────────────────────────────────────────────────

    @staticmethod
    def _serialize_batch(query: str, batch: list[Paper], offset: int) -> str:
        """将查询与一批论文序列化为 LLM 输入文本。"""
        lines = [
            f"## 用户查询\n\n{query}\n",
            "## 待评分论文列表\n",
        ]

        for i, paper in enumerate(batch):
            paper_idx = offset + i
            abstract = paper.abstract[:300] if paper.abstract else "（无摘要）"
            year_str = str(paper.year) if paper.year else "未知"
            authors_short = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_short += " 等"

            lines.append(
                f"### [{paper_idx}] {paper.title}\n"
                f"- 年份: {year_str}\n"
                f"- 作者: {authors_short}\n"
                f"- 来源: {paper.source}\n"
                f"- 摘要: {abstract}\n"
            )

        lines.append(
            "请对以上每篇论文给出 0-100 的相关性评分，"
            "以 JSON 格式返回 scored_items 数组。"
        )
        return "\n".join(lines)

    # ── 解析 ────────────────────────────────────────────────────

    @staticmethod
    def _extract_content(response: dict) -> str:
        """从 chat completions 响应中提取 message content。"""
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RerankError(f"无法从响应中提取 content: {exc}") from exc

    @staticmethod
    def _parse(raw: str) -> list[ScoredItem]:
        """将 LLM 返回的 JSON 解析为 ScoredItem 列表。"""
        text = raw.strip()

        # 容错：去掉 Markdown 代码块包裹
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 2:
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RerankError(
                f"JSON 解析失败: {exc}\n原始文本: {text[:500]}"
            ) from exc

        if not isinstance(data, dict):
            raise RerankError(f"期望 JSON object，实际为 {type(data).__name__}")

        raw_items = data.get("scored_items", [])
        if not isinstance(raw_items, list):
            raise RerankError(f"scored_items 应为数组，实际为 {type(raw_items).__name__}")

        items: list[ScoredItem] = []
        for item in raw_items:
            try:
                items.append(ScoredItem.model_validate(item))
            except Exception as exc:
                logger.warning("跳过无效评分条目: %s — %s", exc, str(item)[:120])

        return items
