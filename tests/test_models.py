"""Pydantic v2 数据模型的测试。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from paper_downloader.models import (
    Author,
    DownloadResult,
    DownloadStatus,
    Metadata,
    Paper,
    PaperSource,
)


class TestAuthor:
    """Author 模型的测试。"""

    def test_create_author_minimal(self) -> None:
        """仅使用姓名即可创建 Author。"""
        author = Author(name="John Smith")
        assert author.name == "John Smith"
        assert author.orcid is None
        assert author.affiliation is None
        assert author.email is None

    def test_create_author_full(self) -> None:
        """可以使用所有字段创建 Author。"""
        author = Author(
            name="Jane Doe",
            orcid="0000-0002-1825-0097",
            affiliation="MIT",
            email="jane@mit.edu",
        )
        assert author.name == "Jane Doe"
        assert author.orcid == "0000-0002-1825-0097"
        assert author.affiliation == "MIT"
        assert author.email == "jane@mit.edu"

    def test_author_frozen(self) -> None:
        """Author 模型是不可变的。"""
        author = Author(name="John Smith")
        with pytest.raises(ValidationError):
            author.name = "Changed"  # type: ignore[misc]

    def test_author_empty_name_raises(self) -> None:
        """作者姓名不能为空。"""
        with pytest.raises(ValidationError):
            Author(name="")

    def test_author_extra_fields_forbidden(self) -> None:
        """不允许额外的字段。"""
        with pytest.raises(ValidationError):
            Author(name="John", unknown_field="value")  # type: ignore[call-arg]


class TestPaperSource:
    """PaperSource 枚举的测试。"""

    def test_all_sources_defined(self) -> None:
        """所有预期的论文来源都已定义。"""
        sources = {s.value for s in PaperSource}
        expected = {
            "openalex",
            "semantic_scholar",
            "arxiv",
            "crossref",
            "unpaywall",
            "manual",
            "unknown",
        }
        assert sources == expected

    def test_source_string_conversion(self) -> None:
        """可以从字符串值创建 PaperSource。"""
        assert PaperSource("openalex") == PaperSource.OPENALEX
        assert PaperSource("arxiv") == PaperSource.ARXIV


class TestDownloadStatus:
    """DownloadStatus 枚举的测试。"""

    def test_all_statuses_defined(self) -> None:
        """所有预期的下载状态都已定义。"""
        statuses = {s.value for s in DownloadStatus}
        expected = {"success", "cached", "failed", "not_found", "timeout", "partial", "pending"}
        assert statuses == expected


class TestPaper:
    """Paper 模型的测试。"""

    def test_create_paper_minimal(self) -> None:
        """仅使用标题即可创建 Paper。"""
        paper = Paper(title="Test Paper")
        assert paper.title == "Test Paper"
        assert paper.authors == []
        assert paper.abstract == ""
        assert paper.provider == PaperSource.UNKNOWN

    def test_create_paper_full(self) -> None:
        """可以使用所有字段创建 Paper。"""
        paper = Paper(
            title="Attention Is All You Need",
            authors=[
                Author(name="Ashish Vaswani"),
                Author(name="Noam Shazeer"),
            ],
            abstract="The dominant sequence transduction models...",
            year=2017,
            venue="NeurIPS",
            doi="10.48550/arXiv.1706.03762",
            url="https://arxiv.org/abs/1706.03762",
            pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
            provider=PaperSource.ARXIV,
            citation_count=100000,
            open_access=True,
            license="CC BY 4.0",
            sha256="abc123def456",
        )
        assert paper.title == "Attention Is All You Need"
        assert len(paper.authors) == 2
        assert paper.year == 2017
        assert paper.venue == "NeurIPS"
        assert paper.doi == "10.48550/arXiv.1706.03762"
        assert paper.citation_count == 100000
        assert paper.open_access is True

    def test_paper_year_validation(self) -> None:
        """论文年份必须在 1500 到 2100 之间。"""
        with pytest.raises(ValidationError):
            Paper(title="Test", year=1499)
        with pytest.raises(ValidationError):
            Paper(title="Test", year=2101)

    def test_paper_citation_count_non_negative(self) -> None:
        """引用计数必须为非负数。"""
        with pytest.raises(ValidationError):
            Paper(title="Test", citation_count=-1)

    def test_paper_mutable(self) -> None:
        """Paper 模型默认是可变的。"""
        paper = Paper(title="Original")
        paper.title = "Updated"
        assert paper.title == "Updated"

    def test_paper_default_factory_lists(self) -> None:
        """每个 Paper 实例拥有自己的作者列表。"""
        p1 = Paper(title="P1")
        p2 = Paper(title="P2")
        p1.authors.append(Author(name="Author"))
        assert len(p2.authors) == 0


class TestMetadata:
    """Metadata 模型的测试。"""

    def test_create_metadata_minimal(self) -> None:
        """仅使用来源即可创建 Metadata。"""
        meta = Metadata(source=PaperSource.OPENALEX)
        assert meta.source == PaperSource.OPENALEX
        assert isinstance(meta.retrieved_at, datetime)
        assert meta.raw_response == {}

    def test_metadata_match_score_validation(self) -> None:
        """匹配分数必须在 0.0 到 1.0 之间。"""
        with pytest.raises(ValidationError):
            Metadata(source=PaperSource.OPENALEX, match_score=1.5)
        with pytest.raises(ValidationError):
            Metadata(source=PaperSource.OPENALEX, match_score=-0.1)

    def test_metadata_frozen(self) -> None:
        """Metadata 模型是不可变的。"""
        meta = Metadata(source=PaperSource.OPENALEX)
        with pytest.raises(ValidationError):
            meta.source = PaperSource.ARXIV  # type: ignore[misc]


class TestDownloadResult:
    """DownloadResult 模型的测试。"""

    def test_create_success_result(self) -> None:
        """成功下载的 DownloadResult。"""
        paper = Paper(title="Test Paper")
        result = DownloadResult(
            paper=paper,
            status=DownloadStatus.SUCCESS,
            pdf_path=Path("/papers/test.pdf"),
            download_time_seconds=2.5,
        )
        assert result.status == DownloadStatus.SUCCESS
        assert result.paper.title == "Test Paper"
        assert result.pdf_path == Path("/papers/test.pdf")
        assert result.error_message is None
        assert result.retry_count == 0

    def test_create_failure_result(self) -> None:
        """失败下载的 DownloadResult。"""
        paper = Paper(title="Unavailable Paper")
        result = DownloadResult(
            paper=paper,
            status=DownloadStatus.FAILED,
            error_message="Connection timeout after 3 retries",
            retry_count=3,
            download_time_seconds=30.0,
        )
        assert result.status == DownloadStatus.FAILED
        assert result.pdf_path is None
        assert result.error_message == "Connection timeout after 3 retries"
        assert result.retry_count == 3

    def test_download_result_negative_retries(self) -> None:
        """重试次数必须为非负数。"""
        paper = Paper(title="Test")
        with pytest.raises(ValidationError):
            DownloadResult(paper=paper, status=DownloadStatus.FAILED, retry_count=-1)

    def test_download_result_negative_time(self) -> None:
        """下载时间必须为非负数。"""
        paper = Paper(title="Test")
        with pytest.raises(ValidationError):
            DownloadResult(paper=paper, status=DownloadStatus.SUCCESS, download_time_seconds=-1.0)
