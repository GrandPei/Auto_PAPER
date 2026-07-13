"""
AutoPaper 交互式主菜单

集成四大模块:
  1. 智能检索 — Pipeline 全流程（查询分析 → 多源搜索 → 去重排序 → PDF 下载）
  2. 论文搜索 — SearchManager 多源并行搜索
  3. PDF 下载 — PaperDownloader 引擎（5 个 Provider 级联）
  4. AI 写作 — Deepseek 学术写作助手

启动方式:
    cd AutoPaper
    python main.py
"""

from __future__ import annotations

import asyncio
import time

from app.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# 菜单
# ══════════════════════════════════════════════════════════════════

def _menu() -> str:
    print()
    print("=" * 55)
    print("    AutoPaper — 学术论文智能辅助工具")
    print("=" * 55)
    print("  1. 智能检索（Pipeline 全流程）")
    print("  2. 论文搜索（多源并行关键词搜索）")
    print("  3. PDF 下载（标题 → 自动搜论文 → 下载）")
    print("  4. AI 学术写作")
    print("  0. 退出")
    print("=" * 55)

    while True:
        choice = input("  请选择 [0-4]: ").strip()
        if choice in ("0", "1", "2", "3", "4"):
            return choice
        print("  输入无效，请重新输入")


# ══════════════════════════════════════════════════════════════════
# 功能 1 — 智能检索（Pipeline 全流程）
# ══════════════════════════════════════════════════════════════════

def _interactive_pipeline() -> None:
    """Pipeline 全流程：查询分析 → 搜索 → 去重 → 排序 → 下载。"""
    print()
    print("─" * 55)
    print("  智能检索（Pipeline 全流程）")
    print("─" * 55)
    print("  流程: 查询分析 → 术语扩展 → 多源搜索 → 去重融合 →")
    print("        相关性排序 → PDF 下载")
    print()

    query = input("  请输入研究主题: ").strip()
    if not query:
        print("  主题不能为空，已取消。")
        return

    try:
        search_limit = int(input("  每源搜索篇数 (默认10): ").strip() or "10")
        download_top = int(input("  下载前 N 篇 PDF (默认3，0=不下载): ").strip() or "3")
    except ValueError:
        search_limit, download_top = 10, 3

    print(f"\n  正在执行智能检索: {query}")
    print(f"  (搜索={search_limit}篇/源, 下载Top{download_top})")
    print()

    asyncio.run(_run_pipeline(query, search_limit, download_top))


async def _run_pipeline(query: str, search_limit: int, download_top: int) -> None:
    """异步执行 Pipeline 并打印结果。"""
    from app.services.pipeline import AutoPaperPipeline

    pipeline = AutoPaperPipeline()
    t0 = time.perf_counter()

    try:
        result = await pipeline.run(
            query,
            search_limit=search_limit,
            download_top=download_top,
            download_concurrent=3,
        )
    except Exception as exc:
        logger.error("Pipeline 执行失败: %s", exc)
        print(f"\n  ✗ Pipeline 执行出错: {exc}")
        return

    elapsed = time.perf_counter() - t0

    # 打印步骤摘要
    print(f"\n  ═══ Pipeline 完成 (耗时 {elapsed:.1f}s) ═══")
    for step in result.steps:
        icon = "✓" if step.success else "✗"
        print(f"  {icon} {step.step}: {step.duration_ms:.0f}ms"
              + (f" — {step.error}" if step.error else ""))

    # 打印论文列表
    papers = result.papers
    if not papers:
        print("\n  ✗ 未找到相关论文。")
        return

    print(f"\n  共找到 {len(papers)} 篇论文:\n")
    for i, p in enumerate(papers):
        authors = ", ".join(p.authors[:3])
        if len(p.authors) > 3:
            authors += " 等"
        print(f"  [{i+1}] {p.title[:80]}")
        print(f"       {authors} | {p.year or '未知年份'} | 引用 {p.citation_count}")
        print(f"       {p.abstract[:120]}{'...' if len(p.abstract) > 120 else ''}")
        print()

    # 打印评分（若有）
    if result.scored_items:
        print("  ── 相关性评分 (Top 5) ──")
        for item in result.scored_items[:5]:
            if item.paper_index < len(papers):
                p = papers[item.paper_index]
                print(f"  [{item.score}分] {p.title[:60]}... — {item.reason}")

    # 打印下载结果
    if result.download:
        print(f"\n  ── PDF 下载 (成功 {result.download.success_count}/{result.download.total}) ──")
        for dr in result.download.results:
            icon = "✓" if dr.success else "✗"
            print(f"  {icon} {dr.paper_title[:60]}..."
                  + (f" → {dr.file_path}" if dr.success else f" — {dr.error}"))


# ══════════════════════════════════════════════════════════════════
# 功能 2 — 论文搜索（多源并行）
# ══════════════════════════════════════════════════════════════════

def _interactive_search() -> None:
    """SearchManager 多源并行关键词搜索。"""
    print()
    print("─" * 55)
    print("  论文搜索（多源并行）")
    print("─" * 55)
    print("  搜索源: Semantic Scholar + OpenAlex + arXiv")
    print()

    keyword = input("  搜索关键词: ").strip()
    if not keyword:
        print("  关键词不能为空，已取消。")
        return

    try:
        limit = int(input("  每源返回篇数 (默认10): ").strip() or "10")
    except ValueError:
        limit = 10

    print(f"\n  正在并行搜索: {keyword} ...\n")
    asyncio.run(_run_search(keyword, limit))


async def _run_search(keyword: str, limit: int) -> None:
    """异步多源搜索并打印结果。"""
    from app.search.manager import SearchManager

    manager = SearchManager()
    papers = await manager.search_all(keyword, limit=limit)

    if not papers:
        print("  ✗ 未找到相关论文。")
        return

    print(f"  共找到 {len(papers)} 篇:\n")
    for i, p in enumerate(papers):
        authors = ", ".join(p.authors[:3])
        if len(p.authors) > 3:
            authors += " 等"
        print(f"  [{i+1}] {p.title}")
        print(f"       {authors} | {p.year or '未知'} | 引用 {p.citation_count}")
        print(f"       来源: {p.source} | {p.abstract[:120]}...")
        print()


# ══════════════════════════════════════════════════════════════════
# 功能 3 — PDF 下载
# ══════════════════════════════════════════════════════════════════

def _interactive_download() -> None:
    """直接 PDF 下载：输入标题 → 自动搜索 → 下载。"""
    print()
    print("─" * 55)
    print("  PDF 下载")
    print("─" * 55)
    print("  引擎: PaperDownloader — 5 个 Provider 级联")
    print("  OpenAlex → Semantic Scholar → arXiv → CrossRef → Unpaywall")
    print()

    title = input("  论文标题: ").strip()
    if not title:
        print("  标题不能为空，已取消。")
        return

    save_dir = input("  保存目录 (默认 ./papers): ").strip() or "./papers"

    print(f"\n  正在搜索并下载: {title}")
    print(f"  (这可能需要 10-30 秒)...\n")

    asyncio.run(_run_download(title, save_dir))


async def _run_download(title: str, save_dir: str) -> None:
    """异步下载 PDF 并打印结果。"""
    from paper_downloader import download_paper_pdf
    from paper_downloader.config import get_settings

    # 配置保存目录
    settings = get_settings()
    settings.download_dir = save_dir

    try:
        result = await download_paper_pdf(title)
    except Exception as exc:
        print(f"\n  ✗ 下载异常: {exc}")
        return

    if result.pdf_path:
        print(f"\n  ✓ 下载成功！")
        print(f"    文件: {result.pdf_path}")
        print(f"    来源: {result.paper.provider.value}")
        print(f"    标题: {result.paper.title}")
        print(f"    年份: {result.paper.year}")
        if result.paper.sha256:
            print(f"    SHA256: {result.paper.sha256[:32]}...")
    else:
        print(f"\n  ✗ 下载失败")
        if result.error_message:
            print(f"    原因: {result.error_message}")


# ══════════════════════════════════════════════════════════════════
# 功能 4 — AI 学术写作
# ══════════════════════════════════════════════════════════════════

def _interactive_writer() -> None:
    """AI 学术写作助手 — 逐轮对话。"""
    print()
    print("─" * 55)
    print("  AI 学术写作助手 (Deepseek)")
    print("─" * 55)
    print("  输入 'quit' 或空行退出对话")
    print()

    asyncio.run(_run_writer())


async def _run_writer() -> None:
    """交互式 AI 写作对话。"""
    from app.llm.deepseek_client import DeepseekClient

    client = DeepseekClient()
    history: list[dict[str, str]] = [
        {"role": "system", "content": "你是一个专业的学术写作助手，帮助用户润色论文、生成大纲、撰写段落。请用中文回复。"}
    ]

    while True:
        try:
            user_input = input("  你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        if not user_input or user_input.lower() == "quit":
            print("  再见！")
            break

        history.append({"role": "user", "content": user_input})

        print("  AI: ", end="", flush=True)
        try:
            response = await client.chat(history)
            print(response)
            history.append({"role": "assistant", "content": response})
        except Exception as exc:
            print(f"\n  ✗ AI 调用失败: {exc}")


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════

def main() -> None:
    """AutoPaper 交互式主菜单。"""
    from app.core.config import settings

    logger.info("AutoPaper 交互式菜单启动")
    logger.info("  日志级别: %s", settings.log_level)
    if not settings.deepseek_api_key:
        logger.warning("  DEEPSEEK_API_KEY 未设置！功能 1、4 将不可用。")

    while True:
        choice = _menu()
        if choice == "0":
            print("  再见！")
            break
        elif choice == "1":
            _interactive_pipeline()
        elif choice == "2":
            _interactive_search()
        elif choice == "3":
            _interactive_download()
        elif choice == "4":
            _interactive_writer()


if __name__ == "__main__":
    main()
