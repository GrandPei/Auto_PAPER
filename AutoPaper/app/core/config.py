"""
config.py — Pydantic Settings 配置管理

所有配置均可通过 .env 文件或环境变量读取。

优先级: 环境变量 > .env 文件 > 默认值
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AutoPaper 全局配置。

    所有字段均可在 .env 中设置，字段名自动转为大写 + 环境变量名。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────

    deepseek_api_key: str = Field(
        default="",
        description="Deepseek API Key（必填）",
    )

    semantic_scholar_api_key: Optional[str] = Field(
        default=None,
        description="Semantic Scholar API Key（可选，免费 API 也无需 Key，但填写可提升速率限制）",
    )

    serpapi_api_key: Optional[str] = Field(
        default=None,
        description="SerpAPI Key（可选，用于 Google Scholar PDF 搜索渠道）",
    )

    # ── 外部数据源 ────────────────────────────────────────────

    openalex_email: Optional[str] = Field(
        default=None,
        description="OpenAlex 礼貌邮箱（推荐填写，以在请求量较大时获得更好的服务）",
    )

    arxiv_contact: Optional[str] = Field(
        default=None,
        description="ArXiv API 联系邮箱（可选）",
    )

    # ── Deepseek ───────────────────────────────────────────────

    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="Deepseek API 基础地址",
    )

    deepseek_model: str = Field(
        default="deepseek-chat",
        description="Deepseek 默认模型",
    )

    deepseek_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="请求失败时最大重试次数",
    )

    deepseek_timeout: int = Field(
        default=60,
        ge=10,
        le=600,
        description="单次请求超时时间（秒）",
    )

    # ── 下载与存储 ────────────────────────────────────────────

    download_dir: Path = Field(
        default=Path("./papers"),
        description="论文 PDF 下载目录",
    )

    # ── 日志 ──────────────────────────────────────────────────

    log_level: str = Field(
        default="INFO",
        description="日志等级: DEBUG | INFO | WARNING | ERROR | CRITICAL",
    )

    log_format: str = Field(
        default="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        description="日志格式",
    )

    log_datefmt: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="日志时间格式",
    )


# ── 全局单例 ──────────────────────────────────────────────────

settings = Settings()
