"""
AI 项目集成示例 — 将 paper_downloader 作为 AI Agent 的论文获取工具.

演示场景:
    1. LLM 提取论文标题 → 自动下载 PDF → 返回本地路径
    2. 文献综述工具：搜索→下载→生成 BibTeX
    3. RAG 系统：获取论文 → 提取全文 → 构建索引

运行方式:
    python examples/integration_with_ai.py
"""

import json
import os
from typing import List

from paper_downloader import (
    PaperDownloader,
    Paper,
    search_papers,
    download_papers,
    get_paper_info,
    ReportGenerator,
)


# ═══════════════════════════════════════════════════════════════════
# 场景 1: LLM Tool — 论文下载工具函数
# ═══════════════════════════════════════════════════════════════════

def llm_tool_download_paper(title: str) -> str:
    """供 LLM Agent 调用的论文下载工具。

    Args:
        title: 论文标题。

    Returns:
        JSON 字符串: {"status": "success", "pdf_path": "...", "metadata": {...}}
    """
    try:
        paper = PaperDownloader().download_by_title(title)
        return json.dumps({
            "status": "success",
            "pdf_path": paper.pdf_path,
            "metadata": {
                "title": paper.title,
                "authors": "; ".join(paper.authors[:3]),
                "year": paper.year,
                "doi": paper.doi,
                "citation_count": paper.citation_count,
            },
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


# ═══════════════════════════════════════════════════════════════════
# 场景 2: 文献综述 — 搜索 → 下载 → BibTeX
# ═══════════════════════════════════════════════════════════════════

def literature_review(query: str, output_dir: str = "./literature_review",
                      max_papers: int = 5) -> str:
    """文献综述辅助：搜索主题 → 下载 → 生成 BibTeX。

    Args:
        query:      研究主题。
        output_dir: 输出目录。
        max_papers: 最大下载数。

    Returns:
        BibTeX 文件路径。
    """
    # 搜索
    papers = search_papers(query, max_results=max_papers)

    # 提取可下载的标题
    titles = [p.title for p in papers if p.title]

    # 下载
    downloaded = download_papers(titles, output_dir=output_dir)

    # 生成报告和 BibTeX
    gen = ReportGenerator(output_dir=output_dir)
    gen.export_json(downloaded)
    gen.export_csv(downloaded)
    bib_path = gen.export_bibtex(downloaded)

    # 输出摘要
    ok = sum(1 for p in downloaded if p.has_pdf)
    print(f"文献综述完成: {ok}/{len(downloaded)} 成功")

    return bib_path


# ═══════════════════════════════════════════════════════════════════
# 场景 3: RAG 系统 — 获取论文 → 提取文本
# ═══════════════════════════════════════════════════════════════════

def rag_paper_pipeline(paper_title: str) -> dict:
    """RAG 论文处理流水线：下载 → 提取文本。

    Args:
        paper_title: 论文标题。

    Returns:
        {"text": str, "metadata": dict, "pdf_path": str}
    """
    from paper_downloader.src.downloaders.pdf_processor import PDFProcessor

    # 下载
    paper = PaperDownloader().download_by_title(paper_title)

    if not paper.has_pdf or not paper.pdf_path:
        return {"text": "", "metadata": paper.to_dict(), "error": "下载失败"}

    # 提取文本
    text = PDFProcessor.extract_text(paper.pdf_path, max_pages=5)

    return {
        "text": text or "",
        "metadata": {
            "title": paper.title,
            "authors": "; ".join(paper.authors),
            "year": paper.year,
            "doi": paper.doi,
        },
        "pdf_path": paper.pdf_path,
    }


# ═══════════════════════════════════════════════════════════════════
# 场景 4: 自定义搜索引擎组合
# ═══════════════════════════════════════════════════════════════════

def multi_source_search(query: str) -> List[Paper]:
    """多源搜索 — 优先 arXiv，回退 CrossRef。"""
    # 先尝试 arXiv
    papers = search_papers(query, max_results=3, engines=["arxiv"])
    if papers:
        return papers
    # 回退到 CrossRef
    return search_papers(query, max_results=3, engines=["crossref"])


# ═══════════════════════════════════════════════════════════════════
# 演示
# ═══════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("AI 集成示例")
    print("=" * 60)

    # 场景 1: LLM Tool
    print("\n1. LLM Tool 调用演示:")
    result = llm_tool_download_paper("Attention Is All You Need")
    print(f"   {json.loads(result)}")

    # 场景 2: 文献综述
    print("\n2. 文献综述演示:")
    bib_path = literature_review("graph neural networks", max_papers=2)
    if os.path.exists(bib_path):
        print(f"   BibTeX: {bib_path}")

    # 场景 3: RAG
    print("\n3. RAG 流水线演示:")
    rag_result = rag_paper_pipeline("BERT: Pre-training")
    print(f"   文本长度: {len(rag_result['text'])} 字符")

    # 场景 4: 多源搜索
    print("\n4. 多源搜索演示:")
    results = multi_source_search("transformer architecture")
    for p in results[:3]:
        print(f"   [{p.source}] {p.title[:60]}")


if __name__ == "__main__":
    main()
