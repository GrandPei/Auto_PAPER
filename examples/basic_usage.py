"""
基本使用示例 — 单篇论文搜索与下载.

运行方式:
    python examples/basic_usage.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper_downloader import (
    download_paper,
    search_papers,
    get_paper_info,
    set_config,
    Paper,
)


def main():
    # ── 配置 ──────────────────────────────────────────────────
    set_config(output_dir="./downloaded_papers", max_downloads=2)

    # ── 1. 搜索论文 ──────────────────────────────────────────
    print("=" * 60)
    print("1. 搜索论文: 'attention mechanism'")
    try:
        papers = search_papers("attention mechanism", max_results=3)
        for i, paper in enumerate(papers, 1):
            print(f"\n  [{i}] {paper.citation}")
            print(f"      标题: {paper.title}")
            print(f"      DOI:  {paper.doi or 'N/A'}")
            print(f"      来源: {paper.source}")
    except Exception as exc:
        print(f"  搜索失败: {exc}")

    # ── 2. 获取论文信息 ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("2. 获取论文信息: DOI 10.1038/nature14539")
    info = get_paper_info("10.1038/nature14539")
    if info:
        print(f"  标题: {info.title}")
        print(f"  作者: {', '.join(info.authors[:3])}")
        print(f"  引用: {info.citation_count or 'N/A'}")
    else:
        print("  未找到（可能需要网络）")

    # ── 3. 下载示例 ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("3. 下载论文: 'Attention Is All You Need'")
    print("  (需要网络连接，按 Ctrl+C 跳过)")
    try:
        paper = download_paper(
            "Attention Is All You Need",
            output_dir="./downloaded_papers",
        )
        print(f"\n  结果: {paper}")
        if paper.has_pdf:
            print(f"  PDF:  {paper.pdf_path}")
            print(f"  大小: {paper.file_size} bytes")
    except KeyboardInterrupt:
        print("\n  已跳过")
    except Exception as exc:
        print(f"  下载失败: {exc}")


if __name__ == "__main__":
    main()
