"""
deepseek_client.py — Deepseek API 异步客户端

OpenAI 兼容的 chat completions 封装，支持:
  - 同步 / 异步调用（chat）
  - 流式输出（stream_chat）
  - 自动重试（指数退避）
  - 超时控制
  - JSON mode
  - 自定义 temperature
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

import httpx

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 需要重试的 HTTP 状态码
_RETRYABLE_STATUS: set[int] = {429, 500, 502, 503, 504}


class DeepseekError(Exception):
    """Deepseek API 调用异常基类。"""

    def __init__(self, message: str, status_code: int | None = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class DeepseekClient:
    """Deepseek API 异步客户端。

    用法::

        client = DeepseekClient()
        response = await client.chat([{"role": "user", "content": "你好"}])
        print(response["choices"][0]["message"]["content"])
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ):
        """
        Args:
            api_key: Deepseek API Key，默认从 settings 读取。
            base_url: API 基础地址，默认从 settings 读取。
            model: 模型名，默认从 settings 读取。
            timeout: 请求超时秒数，默认从 settings 读取。
            max_retries: 最大重试次数，默认从 settings 读取。
        """
        # 优先级：显式传参 > API_key.json > .env/环境变量
        self.api_key = api_key or self._read_key_from_json("deepseek") or settings.deepseek_api_key

        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        self.timeout = timeout or settings.deepseek_timeout
        self.max_retries = max_retries if max_retries is not None else settings.deepseek_max_retries

        if not self.api_key:
            raise DeepseekError(
                "DEEPSEEK_API_KEY 未设置，请在 API_key/API_key.json 中填入 \"deepseek\" 字段。"
            )

    # ── 静态工具 ────────────────────────────────────────────────

    @staticmethod
    def _read_key_from_json(key_name: str) -> str:
        """从项目根目录 API_key/API_key.json 读取 Key 作为兜底。

        Args:
            key_name: JSON 中的 key 名，如 "deepseek", "serpapi"。

        Returns:
            Key 值，未找到返回空字符串。
        """
        try:
            import json
            from pathlib import Path

            # deepseek_client.py → app/llm/ → project root/
            json_path = (
                Path(__file__).resolve().parents[2] / "API_key" / "API_key.json"
            ).resolve()
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(key_name, "")
        except Exception:
            return ""

    # ── 公开方法 ────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        **kwargs,
    ) -> dict:
        """非流式对话补全。

        Args:
            messages: 消息列表，格式同 OpenAI chat completions。
            temperature: 采样温度 (0.0 ~ 2.0)。
            max_tokens: 最大生成 token 数。
            json_mode: 是否启用 JSON 模式（要求 prompt 中包含 "json" 字样）。
            **kwargs: 透传给 API 的额外参数（如 top_p、stop 等）。

        Returns:
            完整的 API 响应 dict。

        Raises:
            DeepseekError: 所有重试均失败时抛出。
        """
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            stream=False,
            **kwargs,
        )

        return await self._retry(lambda: self._request(payload))

    async def stream_chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """流式对话补全。

        Args:
            messages: 消息列表。
            temperature: 采样温度。
            max_tokens: 最大生成 token 数。
            json_mode: 是否启用 JSON 模式。
            **kwargs: 透传参数。

        Yields:
            逐条 SSE chunk dict。
        """
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            stream=True,
            **kwargs,
        )

        async for chunk in self._stream_request(payload):
            yield chunk

    # ── 内部方法 ────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        stream: bool,
        **kwargs,
    ) -> dict:
        """组装请求 payload。"""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return payload

    @property
    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def _request(self, payload: dict) -> dict:
        """发送一次非流式请求，返回解析后的 JSON。"""
        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=self._headers, json=payload)
            return self._handle_response(response, payload)

    async def _stream_request(self, payload: dict) -> AsyncGenerator[dict, None]:
        """发送流式请求，逐行 yield SSE chunk。"""
        url = f"{self.base_url}/chat/completions"
        # 流式传输需要更长超时
        stream_timeout = max(self.timeout, 120)

        async with httpx.AsyncClient(timeout=stream_timeout) as client:
            async with client.stream(
                "POST", url, headers=self._headers, json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise DeepseekError(
                        f"Deepseek API 返回 {response.status_code}: {body.decode()[:500]}",
                        status_code=response.status_code,
                        body=body.decode(),
                    )

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str == "[DONE]":
                        break
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.debug("无法解析 SSE 行: %s", data_str[:120])
                        continue

    def _handle_response(self, response: httpx.Response, payload: dict) -> dict:
        """处理非流式响应，成功返回 dict，失败抛异常。"""
        if response.status_code == 200:
            return response.json()

        body = response.text[:1000]
        status = response.status_code

        if status in _RETRYABLE_STATUS:
            raise DeepseekError(
                f"Deepseek API 返回 {status}（可重试）",
                status_code=status,
                body=body,
            )

        raise DeepseekError(
            f"Deepseek API 返回 {status}: {body}",
            status_code=status,
            body=body,
        )

    async def _retry(self, fn):
        """指数退避重试逻辑。

        Args:
            fn: 异步无参 callable，返回 dict。

        Returns:
            成功的响应 dict。

        Raises:
            DeepseekError: 超过最大重试次数。
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await fn()
            except DeepseekError as exc:
                last_exception = exc
                if exc.status_code not in _RETRYABLE_STATUS:
                    raise
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    logger.warning(
                        "Deepseek API 请求失败（%d/%d），%ds 后重试...",
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Deepseek API 重试耗尽（%d 次），状态码 %s",
                        self.max_retries,
                        exc.status_code,
                    )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    logger.warning(
                        "Deepseek API 网络错误（%d/%d），%ds 后重试...",
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Deepseek API 网络重试耗尽（%d 次）",
                        self.max_retries,
                    )

        raise DeepseekError(
            f"重试 {self.max_retries} 次后仍然失败: {last_exception}"
        )
