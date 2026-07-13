"""
query_rewrite.py — 查询改写器

对 QueryPlan 做术语扩展与查询重写：
  - 简称 ↔ 全称互映射
  - 近义词发现
  - 相关研究方向挖掘
  - 生成 5~10 条可直接送入搜索 API 的查询字符串

核心流程:
    QueryPlan → Deepseek (json_mode) → Pydantic 解析 → RewriteResult
"""

from __future__ import annotations

import json

from app.llm.deepseek_client import DeepseekClient, DeepseekError
from app.models.query_plan import QueryPlan
from app.models.rewrite_result import RewriteResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── 系统提示词 ──────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一个学术文献检索专家，专门对研究查询做术语扩展和多角度改写。

## 输入

你会收到一个结构化的查询计划，包含研究主题、领域、关键词和限定条件。

## 任务

对查询计划做以下扩展，并以 JSON 格式返回：

### 1. 术语扩展
- **简称 → 全称**: 找出所有缩写/简称，补充其完整形式（如 "GNN" → "Graph Neural Network / 图神经网络"）。
- **全称 → 简称**: 找出关键概念的常见缩写（如 "自然语言处理" → "NLP"）。
- **近义词**: 为核心概念找出学术同义词、替代说法（如 "药物发现" ↔ "药物研发" ↔ "药物设计" ↔ "drug discovery" ↔ "drug development"）。

### 2. 相关方向
- 根据研究主题，联想 1-3 个密切相关的研究方向或交叉领域。
- 将这些方向融入查询改写中。

### 3. 查询改写
- 生成 **5-10 条**适合学术搜索 API 的查询字符串。
- 每条查询应涵盖不同角度：术语变体、中英文混搭、宽泛/精确等。
- 每条查询标明 `rewrite_type`：
  - `"synonym"` — 使用近义词改写
  - `"abbreviation"` — 使用缩写改写
  - `"full_name"` — 使用全称改写
  - `"related_direction"` — 从相关方向切入
  - `"expansion"` — 综合扩展

### 4. 关键词提炼
- 汇总所有替代关键词到 `alternative_keywords`。
- 将术语映射关系整理到 `synonyms`（每条格式如 "GNN ↔ Graph Neural Network ↔ 图神经网络"）。

## 输出格式

严格按以下 JSON schema 输出，不要包含任何 Markdown 标记或额外解释：

{
  "expanded_queries": [
    {
      "query": "可直接搜索的完整查询字符串",
      "keywords": ["关键词1", "关键词2"],
      "rewrite_type": "synonym"
    }
  ],
  "synonyms": [
    "术语A ↔ 术语B ↔ 术语C"
  ],
  "alternative_keywords": [
    "替代关键词1",
    "替代关键词2"
  ]
}
"""


class QueryRewriteError(Exception):
    """查询改写异常。"""


class QueryRewriter:
    """查询改写器 — 封装 Deepseek 调用与术语扩展逻辑。

    用法::

        client = DeepseekClient()
        rewriter = QueryRewriter(client)

        plan = await planner.plan("近五年GNN在药物发现中的应用")
        result = await rewriter.rewrite(plan)
        for eq in result.expanded_queries:
            print(f"[{eq.rewrite_type}] {eq.query}")
    """

    def __init__(self, client: DeepseekClient | None = None):
        """
        Args:
            client: DeepseekClient 实例，若为 None 则自动创建。
        """
        self._client = client or DeepseekClient()

    # ── 公开方法 ────────────────────────────────────────────────

    async def rewrite(self, plan: QueryPlan) -> RewriteResult:
        """对查询计划做术语扩展与多角度改写。

        Args:
            plan: QueryPlanner 产出的结构化查询计划。

        Returns:
            RewriteResult 实例，包含 5-10 条改写查询。

        Raises:
            QueryRewriteError: LLM 调用失败或 JSON 解析/校验失败。
        """
        logger.info(
            "开始改写查询 — 主题: %s | 关键词: %s",
            plan.research_topic,
            ", ".join(plan.keywords[:5]),
        )

        user_message = self._serialize_plan(plan)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self._client.chat(
                messages,
                temperature=0.3,   # 中等温度 — 需要一定的创造性扩展
                max_tokens=3072,
                json_mode=True,
            )
        except DeepseekError as exc:
            raise QueryRewriteError(
                f"Deepseek 调用失败 (status={exc.status_code}): {exc}"
            ) from exc

        raw_text = self._extract_content(response)
        logger.debug("改写 LLM 原始响应: %s", raw_text[:500])

        result = self._parse(raw_text, plan.original_query)
        logger.info(
            "查询改写完成 — 生成 %d 条扩展查询 | 近义词组: %d",
            len(result.expanded_queries),
            len(result.synonyms),
        )
        return result

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _serialize_plan(plan: QueryPlan) -> str:
        """将 QueryPlan 序列化为 LLM 可理解的文本。"""
        parts = [
            f"研究主题: {plan.research_topic}",
        ]

        if plan.application_domain:
            parts.append(f"应用领域: {plan.application_domain}")

        if plan.constraints:
            parts.append("限定条件:")
            for c in plan.constraints:
                parts.append(f"  - {c}")

        if plan.keywords:
            parts.append(f"关键词: {', '.join(plan.keywords)}")

        if plan.sub_queries:
            parts.append("子问题:")
            for i, sq in enumerate(plan.sub_queries, 1):
                parts.append(f"  {i}. {sq.description}")
                if sq.keywords:
                    parts.append(f"     子关键词: {', '.join(sq.keywords)}")
                if sq.constraints:
                    parts.append(f"     子限定: {'; '.join(sq.constraints)}")

        return "\n".join(parts)

    @staticmethod
    def _extract_content(response: dict) -> str:
        """从 chat completions 响应中提取 message content。"""
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise QueryRewriteError(
                f"无法从响应中提取 content: {exc}"
            ) from exc

    @staticmethod
    def _parse(raw: str, original_query: str) -> RewriteResult:
        """将 LLM 返回的 JSON 字符串解析并校验为 RewriteResult。

        容错处理:
          - 首尾空白
          - Markdown ```json ... ``` 包裹
        """
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

        # 解析 JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise QueryRewriteError(
                f"JSON 解析失败: {exc}\n原始文本: {text[:500]}"
            ) from exc

        if not isinstance(data, dict):
            raise QueryRewriteError(
                f"期望 JSON object，实际为 {type(data).__name__}"
            )

        # 注入原始查询
        data["original_query"] = original_query

        # Pydantic 校验
        try:
            return RewriteResult.model_validate(data)
        except Exception as exc:
            raise QueryRewriteError(
                f"RewriteResult 校验失败: {exc}\n"
                f"数据: {json.dumps(data, ensure_ascii=False)[:500]}"
            ) from exc
