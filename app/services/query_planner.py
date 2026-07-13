"""
query_planner.py — 查询计划器

将用户自然语言查询结构化：提取研究主题、应用领域、关键词、
限定条件，并拆分为可独立检索的子问题。

核心流程:
    user NL → Deepseek (json_mode) → Pydantic 解析 → QueryPlan
"""

from __future__ import annotations

import json

from app.llm.deepseek_client import DeepseekClient, DeepseekError
from app.models.query_plan import QueryPlan
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── 系统提示词 ──────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一个学术研究助手，专门将用户的自然语言查询转换为结构化的查询计划。

## 任务

分析用户输入，提取以下信息并以 JSON 格式返回：

1. **research_topic**: 用一句话精炼概括研究主题。
2. **application_domain**: 所属学科/应用领域（如 NLP、材料科学、生物信息、经济学 等）。
3. **constraints**: 用户明确或隐含的全局限定条件，包括但不限于：
   - 时间范围（如 "近五年"、"2020年之后"）
   - 方法论要求（如 "实证研究"、"综述"）
   - 地域限制（如 "中国"、"欧美"）
   - 语种要求（如 "中文文献为主"）
   - 研究对象/人群
   每条 constraint 用自然语言简短表达。
4. **keywords**: 中英文检索关键词列表，应覆盖核心概念、同义词、缩写。
5. **sub_queries**: 将原始问题拆分为 2-5 个可独立检索的子问题。
   每个子问题包含：
   - "description": 子问题的自然语言描述
   - "keywords": 该子问题的特定关键词
   - "constraints": 该子问题的特定限定条件
   如果原始问题足够聚焦、无法拆分，返回空数组。

## 输出格式

严格按以下 JSON schema 输出，不要包含任何 Markdown 标记或额外解释：

{
  "research_topic": "string",
  "application_domain": "string",
  "constraints": ["string"],
  "keywords": ["string"],
  "sub_queries": [
    {
      "description": "string",
      "keywords": ["string"],
      "constraints": ["string"]
    }
  ]
}
"""


class QueryPlannerError(Exception):
    """查询计划解析异常。"""


class QueryPlanner:
    """查询计划器 — 封装 Deepseek 调用与 Pydantic 解析。

    用法::

        client = DeepseekClient()
        planner = QueryPlanner(client)

        plan = await planner.plan("近五年图神经网络在药物发现中的应用")
        print(plan.research_topic)
        for sq in plan.sub_queries:
            print("  -", sq.description)
    """

    def __init__(self, client: DeepseekClient | None = None):
        """
        Args:
            client: DeepseekClient 实例，若为 None 则自动创建。
        """
        self._client = client or DeepseekClient()

    # ── 公开方法 ────────────────────────────────────────────────

    async def plan(self, query: str) -> QueryPlan:
        """分析用户查询，返回结构化 QueryPlan。

        Args:
            query: 用户自然语言查询。

        Returns:
            QueryPlan 实例。

        Raises:
            QueryPlannerError: LLM 调用失败或 JSON 解析/校验失败。
        """
        logger.info("开始规划查询: %s", query[:120])

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        try:
            response = await self._client.chat(
                messages,
                temperature=0.1,   # 低温度 → 更确定性的结构化输出
                max_tokens=2048,
                json_mode=True,
            )
        except DeepseekError as exc:
            raise QueryPlannerError(
                f"Deepseek 调用失败 (status={exc.status_code}): {exc}"
            ) from exc

        raw_text = self._extract_content(response)
        logger.debug("LLM 原始响应: %s", raw_text[:500])

        plan = self._parse(raw_text, query)
        logger.info(
            "查询规划完成 — 主题: %s | 子问题: %d 个",
            plan.research_topic,
            len(plan.sub_queries),
        )
        return plan

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _extract_content(response: dict) -> str:
        """从 chat completions 响应中提取 message content。"""
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise QueryPlannerError(
                f"无法从响应中提取 content: {exc}"
            ) from exc

    @staticmethod
    def _parse(raw: str, original_query: str) -> QueryPlan:
        """将 LLM 返回的 JSON 字符串解析并校验为 QueryPlan。

        对常见的格式瑕疵做容错处理：
          - 首尾空白
          - Markdown ```json ... ``` 包裹
        """
        text = raw.strip()

        # 容错：去掉 Markdown 代码块包裹
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ```json 和末行 ```
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            text = "\n".join(lines).strip()

        # 尝试解析 JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise QueryPlannerError(
                f"JSON 解析失败: {exc}\n原始文本: {text[:500]}"
            ) from exc

        if not isinstance(data, dict):
            raise QueryPlannerError(
                f"期望 JSON object，实际为 {type(data).__name__}"
            )

        # 注入原始查询
        data["original_query"] = original_query

        # Pydantic 校验
        try:
            return QueryPlan.model_validate(data)
        except Exception as exc:
            raise QueryPlannerError(
                f"QueryPlan 校验失败: {exc}\n数据: {json.dumps(data, ensure_ascii=False)[:500]}"
            ) from exc
