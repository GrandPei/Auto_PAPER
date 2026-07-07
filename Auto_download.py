"""
Auto_search copy.py — 谷歌学术文献搜索与PDF下载工具

通过 SerpAPI 调用 Google Scholar:
  1. 根据关键词搜索文献
  2. 根据论文名搜索并下载PDF到本地
"""

import os
import re
import requests
from difflib import SequenceMatcher
from typing import List, Dict, Tuple
from serpapi import GoogleSearch

from API_key.key_manager import key_get

# Google Scholar 每页最多返回 20 条，单次请求上限
_MAX_PER_PAGE = 20


def _extract_year(paper: dict) -> str:
    """从 publication_info.summary 或 year 字段中提取年份。"""
    year = paper.get("year", "")
    if year:
        return str(year)

    summary = paper.get("publication_info", {}).get("summary", "")
    # 匹配 4 位数字年份，如 "2017"
    match = re.search(r"\b(19|20)\d{2}\b", summary)
    return match.group(0) if match else ""


def _extract_authors(paper: dict) -> str:
    """从 publication_info.authors 中提取作者列表，返回逗号分隔字符串。"""
    authors = paper.get("publication_info", {}).get("authors", [])
    if not authors:
        return ""
    names = [a.get("name", "") for a in authors if a.get("name")]
    return ", ".join(names)


def search_papers(keyword: str, num: int = 10) -> Tuple[bool, List[Dict[str, str]]]:
    """
    根据关键词搜索谷歌学术文献，返回指定篇数的文献信息。

    Args:
        keyword: 搜索关键词，如 "large language model", "image segmentation"
        num:    需要返回的文献篇数（1-100，超过 100 最多返回 100）

    Returns:
        Tuple[bool, List[Dict]]:
            - success: 搜索是否成功
            - papers:  文献列表，每项包含:
                {
                    "title":    str,   # 标题
                    "authors":  str,   # 作者（逗号分隔）
                    "year":     str,   # 年份
                    "abstract": str,   # 摘要
                }

    Example:
        >>> ok, papers = search_papers("LLM attention mechanism", 5)
        >>> for p in papers:
        ...     print(p["title"], p["authors"], p["year"])
    """
    api_key = key_get("serpapi")
    if not api_key:
        return (False, [{"error": "未配置 serpapi API Key（检查 API_key/API_key.json）"}])

    num = max(1, min(num, 100))
    all_papers: List[Dict[str, str]] = []
    start = 0

    while len(all_papers) < num:
        search_params = {
            "engine":  "google_scholar",
            "q":       keyword,
            "api_key": api_key,
            "hl":      "zh-CN",
            "num":     min(_MAX_PER_PAGE, num - len(all_papers)),
            "start":   start,
        }

        try:
            search = GoogleSearch(search_params)
            results = search.get_dict()
        except Exception as e:
            return (False, [{"error": f"搜索请求失败: {e}"}])

        organic_results = results.get("organic_results", [])
        if not organic_results:
            break  # 没有更多结果

        for paper in organic_results:
            all_papers.append({
                "title":    paper.get("title", ""),
                "authors":  _extract_authors(paper),
                "year":     _extract_year(paper),
                "abstract": paper.get("snippet", ""),
            })

        # 检查是否有下一页
        pagination = results.get("pagination", {})
        next_page = pagination.get("nextPageUrl") or pagination.get("next")
        if not next_page:
            break
        start += len(organic_results)

    if not all_papers:
        return (False, [{"error": f"未找到与 '{keyword}' 相关的文献"}])

    return (True, all_papers[:num])


# ══════════════════════════════════════════════════════════════════
# PDF 下载（多渠道回退）
# ══════════════════════════════════════════════════════════════════

def _try_semantic_scholar(title: str) -> str:
    """通过 Semantic Scholar API 查找 PDF 链接。"""
    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "limit": 3, "fields": "title,openAccessPdf,isOpenAccess"},
            timeout=15,
        )
        data = resp.json()
        for paper in data.get("data", []):
            s2_title = paper.get("title", "")
            sim = SequenceMatcher(None, title.lower(), s2_title.lower()).ratio()
            if sim >= 0.6 and paper.get("isOpenAccess"):
                pdf_info = paper.get("openAccessPdf", {})
                pdf_url = pdf_info.get("url", "")
                if pdf_url:
                    print(f"  [Semantic Scholar] 匹配: {s2_title[:70]} ({sim:.2f})")
                    return pdf_url
    except Exception:
        pass
    return ""


def _try_arxiv(title: str) -> str:
    """通过 arXiv API 搜索并返回 PDF 链接。"""
    try:
        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"ti:{title}", "max_results": 3},
            timeout=15,
        )
        from xml.etree import ElementTree
        root = ElementTree.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            arxiv_title = entry.find("atom:title", ns)
            arxiv_title = arxiv_title.text.strip().replace("\n", " ") if arxiv_title is not None else ""
            sim = SequenceMatcher(None, title.lower(), arxiv_title.lower()).ratio()
            if sim >= 0.6:
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf":
                        pdf_url = link.get("href", "")
                        if pdf_url:
                            print(f"  [arXiv] 匹配: {arxiv_title[:70]} ({sim:.2f})")
                            return pdf_url
    except Exception:
        pass
    return ""


def _do_download(pdf_url: str, file_path: str) -> Tuple[bool, str]:
    """执行 PDF 下载并校验。"""
    try:
        print(f"  下载: {pdf_url[:100]}...")
        resp = requests.get(pdf_url, timeout=60, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            return (False, f"下载链接返回网页而非 PDF: {pdf_url}")

        with open(file_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(file_path)
        if file_size < 10000:
            os.remove(file_path)
            return (False, f"下载文件过小 ({file_size} bytes)，可能不是有效 PDF")

        return (True, file_path)
    except requests.exceptions.RequestException as e:
        return (False, f"下载失败: {e}")


def download_paper_pdf(
    paper_title: str,
    save_dir: str = "",
) -> Tuple[bool, str]:
    """
    根据论文标题，依次尝试多渠道下载 PDF 到本地。

    渠道优先级: Google Scholar → Semantic Scholar → arXiv

    Args:
        paper_title: 论文标题
        save_dir:    保存目录，默认 ./papers/

    Returns:
        Tuple[bool, str]: (成功与否, 文件路径或错误信息)
    """
    if not save_dir:
        save_dir = os.path.join(os.path.dirname(__file__), "papers")
    os.makedirs(save_dir, exist_ok=True)

    safe_title = re.sub(r'[\\/:*?"<>|]', '_', paper_title)[:80]
    file_path = os.path.join(save_dir, f"{safe_title}.pdf")

    pdf_url = ""

    # ── Channel 1: Google Scholar ──────────────────────────────
    api_key = key_get("serpapi")
    if api_key:
        try:
            search = GoogleSearch({
                "engine": "google_scholar",
                "q": paper_title,
                "api_key": api_key,
                "hl": "en",
                "num": 1,
            })
            results = search.get_dict()
            organic_results = results.get("organic_results", [])

            if organic_results:
                paper = organic_results[0]
                matched_title = paper.get("title", "")
                similarity = SequenceMatcher(None, paper_title.lower(), matched_title.lower()).ratio()

                # 仅当标题匹配时才从此渠道获取 PDF
                if similarity >= 0.6:
                    print(f"  [Google Scholar] 匹配: {matched_title[:70]} ({similarity:.2f})")

                    for res in paper.get("resources", []):
                        if res.get("file_format", "").upper() == "PDF":
                            pdf_url = res.get("link", "")
                            if pdf_url: break

                    if not pdf_url:
                        direct_link = paper.get("link", "")
                        if "arxiv.org/abs/" in direct_link:
                            pdf_url = direct_link.replace("/abs/", "/pdf/") + ".pdf"
                        elif "arxiv.org/pdf/" in direct_link:
                            pdf_url = direct_link
                else:
                    print(f"  [Google Scholar] 标题不匹配 (sim={similarity:.2f})，切换渠道")
        except Exception as e:
            print(f"  [Google Scholar] 异常: {e}")

    # ── Channel 2: Semantic Scholar ────────────────────────────
    if not pdf_url:
        print(f"  [Semantic Scholar] 搜索中...")
        pdf_url = _try_semantic_scholar(paper_title)

    # ── Channel 3: arXiv ───────────────────────────────────────
    if not pdf_url:
        print(f"  [arXiv] 搜索中...")
        pdf_url = _try_arxiv(paper_title)

    # ── 无可用链接 ─────────────────────────────────────────────
    if not pdf_url:
        return (False, f"所有渠道均未找到可下载的 PDF: '{paper_title[:80]}'")

    # ── 下载 ───────────────────────────────────────────────────
    return _do_download(pdf_url, file_path)


# ── 命令行演示 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # 测试 PDF 下载
    print("=== PDF 下载测试 ===\n")
    ok, path = download_paper_pdf("A Baseline Analysis of Reward Models’ Ability To Accurately Analyze Foundation Models Under Distribution Shift")
    if ok:
        print(f"✓ 下载成功: {path}")
    else:
        print(f"✗ {path}")


