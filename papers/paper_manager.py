"""
paper_manager.py — 文献管理器

维护 papers_list.json，提供文献的增删查改功能。
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional

_JSON_PATH = os.path.join(os.path.dirname(__file__), "papers_list.json")


def _load() -> dict:
    if not os.path.exists(_JSON_PATH):
        return {"papers": []}
    with open(_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    with open(_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 增 ──────────────────────────────────────────────────────────

def add(paper: Dict) -> bool:
    """
    添加一篇文献记录。

    paper 需包含的字段:
        title     - str  标题（必填，用作唯一标识）
        authors   - str  作者
        year      - str  年份
        file_path - str  本地 PDF 路径
        abstract  - str  摘要（可选）
        tags      - list 标签（可选）
        notes     - str  备注（可选）

    返回 True 表示新增，False 表示已存在同名文献并已更新。
    """
    data = _load()
    papers = data["papers"]

    existing = _find_index(papers, paper["title"])
    record = {
        "title":        paper.get("title", ""),
        "authors":      paper.get("authors", ""),
        "year":         paper.get("year", ""),
        "file_path":    paper.get("file_path", ""),
        "abstract":     paper.get("abstract", ""),
        "tags":         paper.get("tags", []),
        "notes":        paper.get("notes", ""),
        "downloaded_at": paper.get("downloaded_at", datetime.now().strftime("%Y-%m-%d")),
    }

    if existing >= 0:
        papers[existing] = record
        _save(data)
        return False
    else:
        papers.append(record)
        _save(data)
        return True


# ── 删 ──────────────────────────────────────────────────────────

def remove(title: str) -> bool:
    """按标题删除一篇文献。成功返回 True。"""
    data = _load()
    papers = data["papers"]
    idx = _find_index(papers, title)
    if idx < 0:
        return False
    papers.pop(idx)
    _save(data)
    return True


# ── 查 ──────────────────────────────────────────────────────────

def list_all() -> List[Dict]:
    """返回全部文献列表。"""
    return _load()["papers"]


def find(title: str) -> Optional[Dict]:
    """按标题模糊查找，返回第一篇匹配的文献。"""
    papers = _load()["papers"]
    idx = _find_index(papers, title)
    return papers[idx] if idx >= 0 else None


def search(keyword: str) -> List[Dict]:
    """在标题、作者、摘要、标签中搜索关键词，返回匹配的文献列表。"""
    papers = _load()["papers"]
    kw = keyword.lower()
    results = []
    for p in papers:
        search_text = f"{p.get('title','')} {p.get('authors','')} {p.get('abstract','')} {' '.join(p.get('tags',[]))}".lower()
        if kw in search_text:
            results.append(p)
    return results


def count() -> int:
    """返回文献总数。"""
    return len(_load()["papers"])


# ── 改 ──────────────────────────────────────────────────────────

def update(title: str, updates: Dict) -> bool:
    """按标题更新文献的指定字段。成功返回 True。"""
    data = _load()
    papers = data["papers"]
    idx = _find_index(papers, title)
    if idx < 0:
        return False
    for key in ("title", "authors", "year", "file_path", "abstract", "tags", "notes"):
        if key in updates:
            papers[idx][key] = updates[key]
    _save(data)
    return True


# ── 导出 ────────────────────────────────────────────────────────

def export_bibtex(title: str) -> Optional[str]:
    """按标题导出一篇文献的 BibTeX 条目。"""
    p = find(title)
    if not p:
        return None
    key = p["title"].split()[0].lower() + p.get("year", "")
    return (
        f"@article{{{key},\n"
        f"  title = {{{p['title']}}},\n"
        f"  author = {{{p.get('authors', '')}}},\n"
        f"  year = {{{p.get('year', '')}}},\n"
        f"}}"
    )


def export_all_bibtex() -> str:
    """导出全部文献的 BibTeX。"""
    return "\n\n".join(
        export_bibtex(p["title"]) for p in list_all()
    )


# ── 工具 ────────────────────────────────────────────────────────

def _find_index(papers: List[Dict], title: str) -> int:
    """按标题精确匹配，返回索引，未找到返回 -1。"""
    t = title.strip().lower()
    for i, p in enumerate(papers):
        if p.get("title", "").strip().lower() == t:
            return i
    return -1


# ── 命令行 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # 快速查看文献库
    all_papers = list_all()
    print(f"共 {len(all_papers)} 篇文献\n")
    for i, p in enumerate(all_papers, 1):
        print(f"[{i}] {p['title']}")
        print(f"    作者: {p.get('authors', 'N/A')}")
        print(f"    年份: {p.get('year', 'N/A')}")
        print(f"    文件: {p.get('file_path', 'N/A')}")
        if p.get('tags'):
            print(f"    标签: {', '.join(p['tags'])}")
        print()
