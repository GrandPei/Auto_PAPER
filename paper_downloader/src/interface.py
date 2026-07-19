"""
interface.py — 统一极简下载接口

为 AI 项目和其他第三方调用者提供最简洁的论文下载入口。
所有函数返回纯字典，无需了解内部 Paper 模型。

Usage::

    from paper_downloader.src.interface import download_pdf, batch_download_pdf, search_papers

    # 下载单篇
    result = download_pdf("Attention Is All You Need")
    if result["success"]:
        print(result["file_path"])

    # 批量下载
    results = batch_download_pdf(["GPT-4", "BERT", "ResNet"])
    for r in results:
        print(r["success"], r["file_path"])

    # 搜索
    papers = search_papers("diffusion models", max_results=5)
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from paper_downloader.src.core.downloader import PaperDownloader
from paper_downloader.src.models.paper import Paper
from paper_downloader.src.exceptions import (
    PaperDownloaderError,
    PaperNotFoundError,
    DownloadError,
)


# ── 全局单例 ──────────────────────────────────────────────────────

_downloaders: dict[tuple[str, ...], PaperDownloader] = {}


def _get_downloader(engine: str = "auto", timeout: int = 30) -> PaperDownloader:
    """获取或创建全局下载器实例。"""
    engines = _resolve_engines(engine)
    key = tuple(engines)
    if key not in _downloaders:
        _downloaders[key] = PaperDownloader(
            engines=engines,
            max_downloads=3,
        )
    downloader = _downloaders[key]
    _apply_runtime_api_settings(downloader)
    downloader._config.setdefault("timeout", {})["search"] = timeout
    downloader._config.setdefault("timeout", {})["download"] = timeout * 2
    return downloader


def _resolve_engines(engine: str) -> List[str]:
    """解析引擎选择到引擎列表。

    Args:
        engine: "arxiv" | "openalex" | "semantic_scholar" | "crossref" |
                "scholar" | "academic_oa" | "auto"

    Returns:
        引擎名称列表。auto 按优先级尝试所有已注册引擎。
    """
    engine_map = {
        "arxiv":   ["arxiv"],
        "crossref": ["crossref"],
        "scholar": ["google_scholar"],
        "openalex": ["openalex"],
        "semantic_scholar": ["semantic_scholar"],
        # Competition-friendly mode: stable academic APIs plus OA PDF sources,
        # without Google Scholar's optional dependency and scraping limits.
        "academic_oa": ["arxiv", "openalex", "semantic_scholar", "crossref"],
        "auto":    ["arxiv", "openalex", "semantic_scholar", "crossref", "google_scholar"],
    }
    return engine_map.get(engine, engine_map["auto"])


def _apply_runtime_api_settings(downloader: PaperDownloader) -> None:
    """Load optional API settings without requiring them for local tests."""
    semantic_key = _read_key("semantic_scholar") or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
    if semantic_key:
        downloader._config.setdefault("semantic_scholar", {})["api_key"] = semantic_key

    contact_email = (
        _read_key("contact_email")
        or os.environ.get("OPENALEX_EMAIL", "")
        or os.environ.get("CONTACT_EMAIL", "")
    )
    if contact_email:
        downloader._config["contact_email"] = contact_email


def _read_key(name: str) -> str:
    try:
        import json

        key_path = Path(__file__).resolve().parents[2] / "API_key" / "API_key.json"
        if not key_path.exists():
            return ""
        data = json.loads(key_path.read_text(encoding="utf-8"))
        return str(data.get(name) or "")
    except Exception:
        return ""


# ── 公共 API ──────────────────────────────────────────────────────

def download_pdf(
    title: str,
    output_dir: str = "./papers",
    engine: str = "auto",
    timeout: int = 30,
    rename: bool = True,
    callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """根据论文标题下载 PDF。

    最简调用::

        result = download_pdf("Attention Is All You Need")
        if result["success"]:
            print(result["file_path"])

    Args:
        title:      论文标题。
        output_dir: PDF 输出目录，默认 "./papers"。
        engine:     搜索引擎，"arxiv" | "openalex" | "semantic_scholar" |
                    "crossref" | "scholar" | "auto"。
                    默认 "auto" 按优先级自动尝试。
        timeout:    超时秒数，默认 30。
        rename:     是否按元数据重命名 PDF，默认 True。
        callback:   进度回调，签名 (progress: float, message: str) -> None。
                    progress 范围 0.0 ~ 1.0。

    Returns:
        Dict: {
            "success":      bool,        # 是否成功
            "file_path":    str | None,  # 下载的 PDF 路径
            "paper_info":   dict | None,  # 论文元数据
            "error":        str | None,  # 错误信息
            "engine_used":  str | None,  # 实际使用的搜索引擎
        }
    """
    result: Dict[str, Any] = {
        "success": False,
        "file_path": None,
        "paper_info": None,
        "error": None,
        "engine_used": None,
    }

    if not title or not title.strip():
        result["error"] = "标题不能为空"
        return result

    _report(callback, 0.0, f"开始搜索: {title[:60]}")

    # 尝试每个引擎（auto 模式）
    engines = _resolve_engines(engine)
    errors: list[str] = []  # 收集所有引擎的错误

    for eng_name in engines:
        try:
            dl = _get_downloader(eng_name, timeout)
            _report(callback, 0.2, f"使用 {eng_name} 搜索中...")

            papers = dl.search(title, max_results=3, engines=[eng_name])
            if not papers:
                errors.append(f"[{eng_name}] 未找到结果")
                continue

            _report(callback, 0.4, f"找到论文，匹配标题...")

            # 按标题相似度选最佳匹配
            best_paper, score = dl._find_best_match(title, papers, min_similarity=0.60, strict=True)
            if best_paper is None:
                closest = papers[0].title[:80] if papers else "N/A"
                errors.append(
                    f"[{eng_name}] 标题不匹配 (相似度 {score:.0%}): 最近似 \"{closest}\""
                )
                continue

            paper = best_paper
            used_engine = paper.source or eng_name
            _report(callback, 0.6, f"匹配 (相似度 {score:.0%}): {paper.title[:50]}")

            # 下载
            results = dl.download(paper, output_dir=output_dir, rename=rename)

            if results and results[0].has_pdf:
                p = results[0]
                result["success"] = True
                result["file_path"] = p.pdf_path
                result["paper_info"] = _paper_to_dict(p)
                result["engine_used"] = used_engine

                _report(callback, 1.0, f"下载完成: {p.pdf_path}")
                return result

            # PDF 下载失败但论文存在
            errors.append(
                f"[{eng_name}] 找到论文但 PDF 下载失败\n"
                f"  论文: {paper.title[:80]}\n"
                f"  DOI: {paper.doi or 'N/A'}  来源: {paper.source or eng_name}"
            )
            continue

        except PaperNotFoundError:
            errors.append(f"[{eng_name}] 未找到匹配的论文")
            continue
        except Exception as exc:
            errors.append(f"[{eng_name}] 错误: {exc}")
            continue

    # 构建综合错误信息
    if errors:
        result["error"] = (
            f"所有 {len(errors)} 个引擎均失败:\n" +
            "\n".join(f"  {e.split(chr(10))[0]}" for e in errors)
        )
    else:
        result["error"] = "所有搜索引擎均未找到该论文"
    _report(callback, 1.0, result["error"])
    return result


def batch_download_pdf(
    titles: List[str],
    output_dir: str = "./papers",
    engine: str = "auto",
    max_concurrent: int = 3,
    skip_existing: bool = True,
    callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[Dict[str, Any]]:
    """批量下载多篇论文 PDF。

    Args:
        titles:         论文标题列表。
        output_dir:     输出目录。
        engine:         搜索引擎，"auto" 自动选择。
        max_concurrent: 最大并发数，默认 3。
        skip_existing:  跳过输出目录中已有的 PDF，默认 True。
        callback:       进度回调，签名 (current: int, total: int, message: str) -> None。

    Returns:
        List[Dict]: 每篇论文的结果（与 download_pdf 返回格式相同）。
    """
    if not titles:
        return []

    total = len(titles)
    results: List[Dict[str, Any]] = [{
        "success": False, "file_path": None,
        "paper_info": None, "error": "未处理", "engine_used": None,
    } for _ in range(total)]

    _report_batch(callback, 0, total, f"批量下载 {total} 篇...")

    # 预扫描已有 PDF
    existing_stems: set = set()
    if skip_existing:
        out = Path(output_dir)
        if out.exists():
            existing_stems = {p.stem.lower() for p in out.glob("*.pdf")}

    def _download_one(idx: int, title: str) -> None:
        """下载单篇并写入结果。"""
        if skip_existing:
            import re
            stem = re.sub(r'[<>:"/\\|?*]', '_', title[:50]).strip().lower()
            if any(stem in ex for ex in existing_stems):
                results[idx]["success"] = True
                results[idx]["error"] = "已存在（跳过）"
                _report_batch(callback, idx + 1, total, f"跳过: {title[:50]}")
                return

        r = download_pdf(
            title=title,
            output_dir=output_dir,
            engine=engine,
            rename=True,
        )
        results[idx] = r
        status = "OK" if r["success"] else "FAIL"
        _report_batch(callback, idx + 1, total, f"[{status}] {title[:50]}")

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(_download_one, i, t): i
            for i, t in enumerate(titles)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass  # 已在线程内处理

    _report_batch(callback, total, total, "批量下载完成")
    return results


def search_papers(
    query: str,
    max_results: int = 5,
    engine: str = "auto",
) -> List[Dict[str, Any]]:
    """搜索论文（仅获取信息，不下载 PDF）。

    Args:
        query:       搜索关键词或标题。
        max_results: 最大返回数，默认 5。
        engine:      搜索引擎，"auto" 自动选择。

    Returns:
        List[Dict]: 论文信息列表，每项包含:
            - title, authors, year, abstract
            - doi, arxiv_id
            - pdf_url, url
            - source, citation_count, journal
    """
    dl = _get_downloader(engine)
    engines = _resolve_engines(engine)

    try:
        papers = dl.search(query, max_results=max_results, engines=engines)
        return [_paper_to_dict(p) for p in papers]
    except Exception:
        return []


# ── 工具 ──────────────────────────────────────────────────────────

def _paper_to_dict(paper: Paper) -> Dict[str, Any]:
    """将 Paper 对象转为纯字典。"""
    return {
        "title":          paper.title,
        "authors":        paper.authors,
        "first_author":   paper.first_author,
        "year":           paper.year,
        "abstract":       paper.abstract,
        "doi":            paper.doi,
        "arxiv_id":       paper.arxiv_id,
        "pdf_url":        paper.pdf_url,
        "url":            paper.url,
        "source":         paper.source,
        "citation_count": paper.citation_count,
        "journal":        paper.journal,
        "file_path":      paper.pdf_path,
        "file_size":      paper.file_size,
        "downloaded_at":  paper.downloaded_at,
    }


def _report(
    callback: Optional[Callable[[float, str], None]],
    progress: float,
    message: str,
) -> None:
    """调用单篇进度回调（安全）。"""
    if callback is None:
        return
    try:
        callback(progress, message)
    except Exception:
        pass


def _report_batch(
    callback: Optional[Callable[[int, int, str], None]],
    current: int,
    total: int,
    message: str,
) -> None:
    """调用批量进度回调（安全）。"""
    if callback is None:
        return
    try:
        callback(current, total, message)
    except Exception:
        pass
