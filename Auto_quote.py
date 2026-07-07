"""
Auto_quote.py — 谷歌学术自动引用生成工具

通过 SerpAPI 调用 Google Scholar，根据文献名和引用格式返回格式化引用文本。
"""

from typing import Tuple
from serpapi import GoogleSearch

from API_key.key_manager import key_get


# ── Google Scholar Cite 接口仅返回这三种格式 ──────────────────
# 格式名与 SerpAPI 返回的 citations[].style 精确对应
STYLE_GB_T = "GB/T 7714"
STYLE_MLA  = "MLA"
STYLE_APA  = "APA"
SUPPORTED_STYLES = [STYLE_GB_T, STYLE_MLA, STYLE_APA]


def get_citation(paper_title: str, citation_style: str = "GB/T 7714") -> Tuple[bool, str]:
    """
    传入单一文献名和引用格式，返回格式化引用文本。

    Args:
        paper_title:   文献标题（论文名）
        citation_style: 引用格式，仅支持: "GB/T 7714" / "MLA" / "APA"

    Returns:
        Tuple[bool, str]: (成功与否, 引用文本或错误信息)

    Example:
        >>> success, text = get_citation("Attention Is All You Need", "APA")
        >>> print(text)
        Vaswani, A., Shazeer, N., Parmar, N., ... (2017). Attention is all you need. NeurIPS.
    """
    api_key = key_get("serpapi")
    if not api_key:
        return (False, "错误: 未配置 serpapi API Key（检查 API_key/API_key.json）")

    # 格式名映射：支持简写 → 完整格式名
    style_map = {
        "GB/T": STYLE_GB_T, "GB/T 7714": STYLE_GB_T, "GBT": STYLE_GB_T,
        "MLA": STYLE_MLA,
        "APA": STYLE_APA,
    }
    target_style = style_map.get(citation_style.strip(), citation_style.strip())

    # ── Step 1: 搜索文献 ──────────────────────────────────────
    search_params = {
        "engine":  "google_scholar",
        "q":       paper_title,
        "api_key": api_key,
        "hl":      "zh-CN",
        "num":     1,
    }

    try:
        search = GoogleSearch(search_params)
        results = search.get_dict()
    except Exception as e:
        return (False, f"搜索请求失败: {e}")

    organic_results = results.get("organic_results", [])
    if not organic_results:
        return (False, f"未找到匹配的文献: '{paper_title}'")

    result_id = organic_results[0].get("result_id", "")
    if not result_id:
        return (False, "无法获取文献 ID，引用失败")

    # ── Step 2: 获取引用格式 ──────────────────────────────────
    cite_params = {
        "engine":  "google_scholar_cite",
        "q":       result_id,
        "api_key": api_key,
        "hl":      "zh-CN",
    }
    try:
        cite_results = GoogleSearch(cite_params).get_dict()
    except Exception as e:
        return (False, f"获取引用格式失败: {e}")

    citations = cite_results.get("citations", [])
    if not citations:
        return (False, "未获取到任何引用格式")

    # ── Step 3: 精确匹配（字段名是 title 不是 style）──────────
    for c in citations:
        if c.get("title", "") == target_style:
            return (True, c.get("snippet", ""))

    # 未匹配到目标格式
    available = [c.get("title", "?") for c in citations]
    return (False, f"未找到 '{target_style}' 格式，可用格式: {', '.join(available)}")


# ── 命令行演示 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    test_papers = [
        ("Attention Is All You Need", "APA"),
        ("Attention Is All You Need", "MLA"),
        ("Attention Is All You Need", "GB/T 7714"),
    ]

    for paper, style in test_papers:
        print(f"\n{'='*60}")
        print(f"文献: {paper}")
        print(f"格式: {style}")
        success, text = get_citation(paper, style)
        print(f"状态: {'成功' if success else '失败'}")
        print(f"引用:\n{text}")
        print(f"{'='*60}")
