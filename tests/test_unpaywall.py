"""Unpaywall 提供者的测试。"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from paper_downloader.models import Paper, PaperSource
from paper_downloader.providers.base import ProviderNotFoundError
from paper_downloader.providers.unpaywall import UnpaywallProvider


def _mock_response(
    doi: str = "10.1234/test",
    title: str = "Test Paper",
    is_oa: bool = True,
    pdf_url: str = "https://repository.example.com/test.pdf",
    license_str: str = "cc-by",
    repository: str = "repository",
) -> dict[str, Any]:
    """创建一个模拟的 Unpaywall API 响应。"""
    return {
        "doi": doi,
        "title": title,
        "year": 2023,
        "is_oa": is_oa,
        "journal_name": "Nature Communications",
        "best_oa_location": {
            "url_for_pdf": pdf_url if is_oa else None,
            "license": license_str if is_oa else None,
            "host_type": repository,
            "version": "publishedVersion",
            "url": f"https://{repository}.example.com/{doi}",
        }
        if is_oa
        else None,
        "z_authors": [
            {"given": "John", "family": "Smith"},
            {"given": "Jane", "family": "Doe"},
        ],
    }


@pytest.fixture
def provider() -> UnpaywallProvider:
    """创建一个用于测试的 Unpaywall 提供者。"""
    return UnpaywallProvider(email="test@example.com")


@pytest.mark.asyncio
async def test_search_returns_empty(
    provider: UnpaywallProvider,
) -> None:
    """Unpaywall 不支持按标题搜索。"""
    results = await provider.search("Anything")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_get_metadata_oa_paper(
    provider: UnpaywallProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """元数据中包含开放获取论文的 OA PDF URL。"""
    doi = "10.1234/oa-paper"
    httpx_mock.add_response(
        url=f"https://api.unpaywall.org/v2/{doi}?email=test%40example.com",
        json=_mock_response(doi=doi, is_oa=True, pdf_url="https://repo.example.com/paper.pdf"),
    )

    paper = await provider.get_metadata(doi)
    assert paper.doi == doi
    assert paper.open_access is True
    assert paper.pdf_url == "https://repo.example.com/paper.pdf"
    assert paper.license == "cc-by"
    assert paper.provider == PaperSource.UNPAYWALL


@pytest.mark.asyncio
async def test_get_metadata_closed_paper(
    provider: UnpaywallProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """非 OA 论文的元数据没有 PDF URL。"""
    doi = "10.1234/closed-paper"
    httpx_mock.add_response(
        url=f"https://api.unpaywall.org/v2/{doi}?email=test%40example.com",
        json=_mock_response(doi=doi, is_oa=False, pdf_url=""),
    )

    paper = await provider.get_metadata(doi)
    assert paper.open_access is False
    assert paper.pdf_url is None


@pytest.mark.asyncio
async def test_get_metadata_not_found(
    provider: UnpaywallProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """不存在的 DOI 抛出 ProviderNotFoundError。"""
    doi = "10.9999/missing"
    httpx_mock.add_response(
        url=f"https://api.unpaywall.org/v2/{doi}?email=test%40example.com",
        status_code=404,
        json={"error": "Not found"},
    )

    with pytest.raises(ProviderNotFoundError):
        await provider.get_metadata(doi)


@pytest.mark.asyncio
async def test_parse_authors(
    provider: UnpaywallProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """从 z_authors 字段解析作者。"""
    doi = "10.1234/authors"
    httpx_mock.add_response(
        url=f"https://api.unpaywall.org/v2/{doi}?email=test%40example.com",
        json=_mock_response(doi=doi),
    )

    paper = await provider.get_metadata(doi)
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "John Smith"
    assert paper.authors[1].name == "Jane Doe"


@pytest.mark.asyncio
async def test_get_pdf_url_with_doi(
    provider: UnpaywallProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """当论文有 DOI 时获取 PDF URL。"""
    doi = "10.1234/has-doi"
    paper = Paper(title="Test", doi=doi)
    httpx_mock.add_response(
        url=f"https://api.unpaywall.org/v2/{doi}?email=test%40example.com",
        json=_mock_response(doi=doi, pdf_url="https://repo.com/test.pdf"),
    )

    pdf_url = await provider.get_pdf_url(paper)
    assert pdf_url == "https://repo.com/test.pdf"
    assert paper.open_access is True


@pytest.mark.asyncio
async def test_get_pdf_url_no_doi(
    provider: UnpaywallProvider,
) -> None:
    """当论文没有 DOI 时返回 None。"""
    paper = Paper(title="Test")
    result = await provider.get_pdf_url(paper)
    assert result is None


@pytest.mark.asyncio
async def test_parse_response_venue_and_year(
    provider: UnpaywallProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """提取期刊和年份。"""
    doi = "10.1234/venue-test"
    httpx_mock.add_response(
        url=f"https://api.unpaywall.org/v2/{doi}?email=test%40example.com",
        json=_mock_response(doi=doi),
    )

    paper = await provider.get_metadata(doi)
    assert paper.venue == "Nature Communications"
    assert paper.year == 2023
