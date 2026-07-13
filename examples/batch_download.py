"""
批量下载示例 — 从列表或文件批量下载论文.

运行方式:
    python examples/batch_download.py
    python examples/batch_download.py --file my_titles.txt
"""

import argparse

from paper_downloader import (
    download_papers,
    PaperDownloader,
    BatchProcessor,
    Paper,
)


def main():
    parser = argparse.ArgumentParser(description="批量下载论文")
    parser.add_argument("--file", type=str, help="包含标题列表的 TXT/CSV 文件")
    parser.add_argument("--output", type=str, default="./batch_papers", help="输出目录")
    args = parser.parse_args()

    # ── 方式 1: 从 Python 列表批量下载 ─────────────────────────
    titles = [
        "Attention Is All You Need",
        "BERT: Pre-training of Deep Bidirectional Transformers",
        "Deep Residual Learning for Image Recognition",
    ]

    # ── 方式 2: 从文件加载 ────────────────────────────────────
    if args.file:
        bp = BatchProcessor()
        titles = bp.from_file(args.file)
        print(f"从文件加载了 {len(titles)} 个标题")

    # ── 执行批量下载 ──────────────────────────────────────────
    print(f"开始批量下载 {len(titles)} 篇论文 → {args.output}")

    # 设置进度回调
    def on_progress(paper: Paper):
        status = "✓" if paper.has_pdf else "✗"
        print(f"  [{status}] {paper.title[:60]}")

    dl = PaperDownloader(output_dir=args.output, max_downloads=3)
    dl.set_progress_callback(on_progress)

    # 使用 download_papers 便捷函数
    papers = download_papers(titles, output_dir=args.output)

    # ── 生成报告 ──────────────────────────────────────────────
    from paper_downloader import ReportGenerator

    gen = ReportGenerator(output_dir=args.output)
    gen.export_json(papers)
    gen.export_csv(papers)
    gen.export_markdown(papers)

    # ── 摘要 ──────────────────────────────────────────────────
    ok = sum(1 for p in papers if p.has_pdf)
    print(f"\n完成: {ok}/{len(papers)} 成功")
    print(f"报告已保存到 {args.output}/")


if __name__ == "__main__":
    main()
