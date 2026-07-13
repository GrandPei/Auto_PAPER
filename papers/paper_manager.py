"""
paper_manager.py — 文献管理器

维护 papers_list.json，提供文献的增删查改功能。
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

_JSON_PATH = os.path.join(os.path.dirname(__file__), "papers_list.json")

# 文件名非法字符（与 paper_downloader.storage.file_store 保持一致）
_ILLEGAL_CHARS = r'[<>:"/\\|?*\x00-\x1f]'

# papers 数据根目录，默认为 papers/ 同级的 papers_data/
_PAPERS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "papers_data")

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


# ── 包装 ────────────────────────────────────────────────────────



def _sanitize_name(name: str, max_len: int = 200) -> str:
    """净化文件夹名称，替换非法字符。"""
    sanitized = re.sub(_ILLEGAL_CHARS, "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_ .")
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len]
    return sanitized


def _make_folder_name(title: str, authors: str = "", year: str = "") -> str:
    """生成规范的论文文件夹名：{第一作者姓氏}_{年份}_{标题}。"""
    # 提取第一作者姓氏
    first_author = "unknown"
    if authors:
        # 支持 "John Smith" 或 "Smith, John" 两种格式
        first_name = authors.split(",")[0].strip() if "," in authors else authors.split(";")[0].strip()
        parts = first_name.split()
        first_author = parts[-1] if parts else first_name

    year_str = str(year) if year else "nodate"
    title_part = title[:80] if title else "untitled"

    raw = f"{first_author}_{year_str}_{title_part}"
    return _sanitize_name(raw)


def wrap_paper(
    title: str,
    *,
    authors: str = "",
    year: str = "",
    pdf_path: str | Path | None = None,
    base_dir: str | Path | None = None,
    register: bool = True,
) -> Optional[str]:
    """将下载的论文文件包装成一个独立文件夹，便于存储管理。

    将 PDF 及同名的元数据文件（.json / .bib / .ris）移入
    以 ``{第一作者}_{年份}_{标题}`` 命名的文件夹中，
    并可选地注册到 ``papers_list.json``。

    Args:
        title:     论文标题（必填）。
        authors:   作者字符串，如 ``"John Smith; Jane Doe"``。
        year:      发表年份。
        pdf_path:  PDF 文件的本地路径。若为 None，则只创建空文件夹。
        base_dir:  存放文件夹的根目录。默认为 ``papers_data/``。
        register:  是否自动注册到文献库。默认 True。

    Returns:
        创建好的文件夹路径，失败时返回 None。

    Example::

        >>> wrap_paper(
        ...     title="Attention Is All You Need",
        ...     authors="Ashish Vaswani; Noam Shazeer",
        ...     year="2017",
        ...     pdf_path="/downloads/Vaswani_2017_Attention_Is_All_You_Need.pdf",
        ... )
        'papers_data/Vaswani_2017_Attention_Is_All_You_Need'
    """
    # ---- 确定目标根目录 ----
    root = Path(base_dir) if base_dir else Path(_PAPERS_DATA_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # ---- 生成文件夹名 ----
    folder_name = _make_folder_name(title, authors, year)
    folder_path = root / folder_name

    # 处理重名：追加数字后缀
    if folder_path.exists():
        counter = 1
        while (root / f"{folder_name}_{counter}").exists():
            counter += 1
        folder_path = root / f"{folder_name}_{counter}"

    folder_path.mkdir(parents=True, exist_ok=True)

    # ---- 移动文件 ----
    pdf_src = Path(pdf_path) if pdf_path else None
    moved_files: list[str] = []

    if pdf_src and pdf_src.exists():
        dest = folder_path / pdf_src.name
        shutil.move(str(pdf_src), str(dest))
        moved_files.append(str(dest))
    elif pdf_src:
        # PDF 路径已记录但文件不存在 —— 仍然记录但不移动
        pass

    # 同时移动同名的元数据文件（.json / .bib / .ris）
    if pdf_src:
        stem = pdf_src.stem  # 不含扩展名的文件名
        parent = pdf_src.parent
        for ext in (".json", ".bib", ".ris"):
            sidecar = parent / f"{stem}{ext}"
            if sidecar.exists():
                dest = folder_path / sidecar.name
                shutil.move(str(sidecar), str(dest))
                moved_files.append(str(dest))

    # ---- 注册到文献库 ----
    if register:
        record = {
            "title":    title,
            "authors":  authors,
            "year":     str(year) if year else "",
            "file_path": str(folder_path),
            "tags":     [],
            "notes":    "",
            "downloaded_at": datetime.now().strftime("%Y-%m-%d"),
        }
        add(record)

    return str(folder_path)


def wrap_from_download_result(
    result,
    *,
    base_dir: str | Path | None = None,
    register: bool = True,
) -> Optional[str]:
    """直接从 ``paper_downloader`` 的 DownloadResult 包装论文。

    这是 ``wrap_paper`` 的便捷封装，自动从 DownloadResult
    中提取标题、作者、年份和 PDF 路径。

    Args:
        result:    paper_downloader 返回的 DownloadResult 对象。
        base_dir:  存放文件夹的根目录。默认为 ``papers_data/``。
        register:  是否自动注册到文献库。默认 True。

    Returns:
        创建好的文件夹路径，失败时返回 None。
    """
    paper = result.paper
    authors_str = "; ".join(a.name for a in paper.authors)
    return wrap_paper(
        title=paper.title,
        authors=authors_str,
        year=str(paper.year) if paper.year else "",
        pdf_path=paper.pdf_path or result.pdf_path,
        base_dir=base_dir,
        register=register,
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
