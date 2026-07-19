"""
Download diagnostics for the paper_downloader module.

Run in PyCharm:
  1. Open Auto_PAPER-main as the project root.
  2. Open this file.
  3. Right click -> Run 'download_diagnostic'.

The script focuses only on legal PDF acquisition and validation for concrete
paper titles that are relevant to the competition references. It does not call
DeepSeek and does not test the paper-search Agent pipeline.

Each case uses engine="academic_oa", which tries arXiv, OpenAlex,
Semantic Scholar, and CrossRef. Google Scholar is intentionally excluded from
this diagnostic because it requires the optional scholarly package and is less
stable for repeatable competition tests.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from paper_downloader.src.downloaders.base_downloader import Downloader
from paper_downloader.src.downloaders.pdf_processor import PDFProcessor
from paper_downloader.src.interface import download_pdf


OUTPUT_ROOT = PROJECT_ROOT / "download_diagnostics"
PDF_DIR = OUTPUT_ROOT / "pdfs"


TEST_CASES = [
    {
        "case_id": "competition_ref_pasa",
        "query": "PaSa: An LLM Agent for Comprehensive Academic Paper Search",
        "engine": "academic_oa",
        "expected": "success",
        "note": "Competition reference [1], arXiv:2501.10120.",
    },
    {
        "case_id": "competition_ref_litsearch",
        "query": "LitSearch: A Retrieval Benchmark for Scientific Literature Search",
        "engine": "academic_oa",
        "expected": "success",
        "note": "Competition reference [2], arXiv:2407.18940.",
    },
    {
        "case_id": "competition_ref_spar",
        "query": "SPAR: Scholar Paper Retrieval with LLM-based Agents for Enhanced Academic Search",
        "engine": "academic_oa",
        "expected": "success",
        "note": "Competition reference [4], arXiv:2507.15245.",
    },
    {
        "case_id": "competition_ref_dsp",
        "query": "Demonstrate-Search-Predict: Composing Retrieval and Language Models for Knowledge-Intensive NLP",
        "engine": "academic_oa",
        "expected": "success",
        "note": "Competition reference [6], arXiv:2212.14024.",
    },
    {
        "case_id": "competition_ref_gritlm",
        "query": "GritLM: Generative Representational Instruction Tuning",
        "engine": "academic_oa",
        "expected": "success",
        "note": "Competition reference [8], arXiv:2402.09906.",
    },
]


@dataclass
class DiagnosticRow:
    case_id: str
    query: str
    engine: str
    expected: str
    success: bool
    status: str
    file_path: str
    file_size: int
    is_pdf_header: bool
    is_pdf_deep: bool
    page_count: int | None
    engine_used: str
    title: str
    doi: str
    arxiv_id: str
    pdf_url: str
    elapsed_sec: float
    error: str
    note: str


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[DiagnosticRow] = []
    print(f"Output directory: {OUTPUT_ROOT}")
    print(f"PDF directory:    {PDF_DIR}")
    print()

    for index, case in enumerate(TEST_CASES, 1):
        print(f"[{index}/{len(TEST_CASES)}] {case['case_id']}: {case['query']}")
        started = time.perf_counter()
        result = download_pdf(
            title=case["query"],
            output_dir=str(PDF_DIR),
            engine=case["engine"],
            timeout=45,
            rename=True,
            callback=lambda progress, message: print(f"  {progress:>4.0%} {message}"),
        )
        elapsed = time.perf_counter() - started
        row = build_row(case, result, elapsed)
        rows.append(row)
        print(f"  => {row.status} ({elapsed:.1f}s)")
        if row.file_path:
            print(f"     {row.file_path}")
        if row.error:
            print(f"     error: {shorten(row.error, 220)}")
        print()

    write_reports(rows)
    print("Reports written:")
    print(f"- {OUTPUT_ROOT / 'download_diagnostic_report.csv'}")
    print(f"- {OUTPUT_ROOT / 'download_diagnostic_report.json'}")


def build_row(case: dict[str, str], result: dict[str, Any], elapsed: float) -> DiagnosticRow:
    file_path = str(result.get("file_path") or "")
    path = Path(file_path) if file_path else None

    file_size = path.stat().st_size if path and path.exists() else 0
    is_pdf_header = bool(path and Downloader.validate_pdf(path))
    is_pdf_deep = bool(path and Downloader.validate_pdf_deep(path))
    page_count = PDFProcessor.get_page_count(path) if path and path.exists() else None

    paper_info = result.get("paper_info") or {}
    success = bool(result.get("success"))
    error = str(result.get("error") or "")
    status = classify_status(
        success=success,
        file_path=file_path,
        file_size=file_size,
        is_pdf_header=is_pdf_header,
        is_pdf_deep=is_pdf_deep,
        page_count=page_count,
        error=error,
    )

    return DiagnosticRow(
        case_id=case["case_id"],
        query=case["query"],
        engine=case["engine"],
        expected=case["expected"],
        success=success,
        status=status,
        file_path=file_path,
        file_size=file_size,
        is_pdf_header=is_pdf_header,
        is_pdf_deep=is_pdf_deep,
        page_count=page_count,
        engine_used=str(result.get("engine_used") or ""),
        title=str(paper_info.get("title") or ""),
        doi=str(paper_info.get("doi") or ""),
        arxiv_id=str(paper_info.get("arxiv_id") or ""),
        pdf_url=str(paper_info.get("pdf_url") or ""),
        elapsed_sec=round(elapsed, 2),
        error=error,
        note=case["note"],
    )


def classify_status(
    *,
    success: bool,
    file_path: str,
    file_size: int,
    is_pdf_header: bool,
    is_pdf_deep: bool,
    page_count: int | None,
    error: str,
) -> str:
    if success and file_path and is_pdf_header and is_pdf_deep and (page_count or 0) > 0:
        return "success_valid_pdf"
    if success and file_path and is_pdf_header:
        return "success_pdf_needs_review"
    if success and file_path and not is_pdf_header:
        return "invalid_download_not_pdf"
    if "标题不匹配" in error or "not match" in error.lower():
        return "title_mismatch"
    if "未找到" in error or "not found" in error.lower():
        return "not_found"
    if "403" in error or "401" in error or "paywall" in error.lower() or "access" in error.lower():
        return "access_limited_or_paywalled"
    if "timeout" in error.lower() or "timed out" in error.lower():
        return "network_timeout"
    if "429" in error or "too many requests" in error.lower() or "rate limit" in error.lower():
        return "rate_limited"
    if file_size == 0 and file_path:
        return "empty_file"
    return "failed_needs_review"


def write_reports(rows: list[DiagnosticRow]) -> None:
    csv_path = OUTPUT_ROOT / "download_diagnostic_report.csv"
    json_path = OUTPUT_ROOT / "download_diagnostic_report.json"

    fieldnames = list(DiagnosticRow.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    json_path.write_text(
        json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


if __name__ == "__main__":
    main()
