"""
AutoPaper MVP — 主入口

启动方式:
    uv run python -m AutoPaper.main
    或
    cd AutoPaper && uv run uvicorn main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import search_router
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    logger.info("AutoPaper API 启动中...")

    from app.core.config import settings

    logger.info("配置加载完成 — log_level: %s", settings.log_level)
    if not settings.deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY 未设置！")

    yield

    logger.info("AutoPaper API 关闭。")


app = FastAPI(
    title="AutoPaper",
    description="学术论文自动化辅助工具 — 检索、分析、下载一站式 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(search_router)


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "ok", "service": "AutoPaper"}


def main() -> None:
    """CLI 启动入口（MVP 阶段仅做配置校验）。"""
    import uvicorn

    logger.info("=" * 50)
    logger.info("  AutoPaper MVP — 学术论文自动化辅助工具")
    logger.info("=" * 50)

    from app.core.config import settings

    logger.info("配置加载完成:")
    logger.info("  - log_level: %s", settings.log_level)
    logger.info("  - download_dir: %s", settings.download_dir)

    if not settings.deepseek_api_key:
        logger.warning(
            "DEEPSEEK_API_KEY 未设置，请在 .env 或环境变量中配置。"
        )
    else:
        logger.info("  - deepseek_api_key: ***%s", settings.deepseek_api_key[-4:])

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
