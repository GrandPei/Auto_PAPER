"""
Auto_search.py — 谷歌学术批量文献搜索工具

通过 SerpAPI 调用 Google Scholar，根据关键词搜索文献，
返回每篇文献的标题、作者、年份、摘要。
"""

import re
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


# ── 命令行演示 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    keyword = "large language model reasoning"
    num = 5

    print(f"搜索关键词: {keyword}")
    print(f"请求篇数: {num}\n")

    success, papers = search_papers(keyword, num)

    if not success:
        print(f"搜索失败: {papers[0].get('error', '未知错误')}")
    else:
        for i, p in enumerate(papers, 1):
            print(f"{'─' * 60}")
            print(f"[{i}] {p['title']}")
            print(f"    作者:   {p['authors'] or '未知'}")
            print(f"    年份:   {p['year'] or '未知'}")
            print(f"    摘要:   {p['abstract'][:200]}{'...' if len(p['abstract']) > 200 else ''}")
        print(f"{'─' * 60}")
        print(f"共返回 {len(papers)} 篇文献")
