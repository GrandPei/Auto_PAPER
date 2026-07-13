"""
异步使用示例 — 使用 AsyncPaperDownloader 并发下载.

需要: pip install aiohttp

运行方式:
    python examples/async_usage.py
"""

import asyncio

from paper_downloader import AsyncPaperDownloader, Paper


async def main():
    titles = [
        "GPT-4 Technical Report",
        "LLaMA: Open and Efficient Foundation Language Models",
        "PaLM: Scaling Language Modeling with Pathways",
    ]

    # 创建异步下载器
    async with AsyncPaperDownloader(
        output_dir="./async_papers",
        max_concurrent_downloads=3,
    ) as dl:

        # 注册回调
        @dl.callbacks.on("on_download_complete")
        def on_done(paper: Paper):
            print(f"  ✓ {paper.title[:60]}")

        @dl.callbacks.on("on_download_error")
        def on_error(paper: Paper, error: Exception):
            print(f"  ✗ {paper.title[:40]}: {error}")

        # ── 方式 1: 异步批量下载 ──────────────────────────────
        print(f"异步批量下载 {len(titles)} 篇论文...")
        papers = await dl.batch_download_async(titles, output_dir="./async_papers")

        # ── 方式 2: 分步操作 ──────────────────────────────────
        print("\n分步操作: 搜索 → 下载")
        for title in titles[:2]:
            results = await dl.search_async(title, max_results=1)
            if results:
                print(f"  找到: {results[0].title[:60]}")

        # ── 结果 ──────────────────────────────────────────────
        ok = sum(1 for p in papers if p.has_pdf)
        print(f"\n完成: {ok}/{len(papers)} 成功")


if __name__ == "__main__":
    asyncio.run(main())
