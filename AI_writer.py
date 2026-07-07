"""
AI_writer.py — DeepSeek API 对话

DeepSeek 兼容 OpenAI SDK，修改 base_url 即可使用。
"""

import os
from typing import Optional
from openai import OpenAI

from API_key.key_manager import key_get


# ── DeepSeek 配置 ──────────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def _get_client() -> OpenAI:
    api_key = key_get("deepseek")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def chat(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    向 DeepSeek 发送对话请求，返回生成文本。

    Args:
        prompt:        用户提示词
        system_prompt: 系统角色设定（可选）
        model:         模型名称
        temperature:   生成温度 0-2
        max_tokens:    最大输出 token

    Returns:
        DeepSeek 返回的文本
    """
    client = _get_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


# ── 测试 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    reply = chat("用一句话介绍你自己", max_tokens=200)
    print(reply)
