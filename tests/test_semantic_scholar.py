"""Semantic Scholar 提供者的测试。"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from paper_downloader.models import Paper, PaperSource
from paper_downloader.providers.base import ProviderNotFoundError
from paper_downloader.providers.semantic_scholar import SemanticScholarProvider


def _mock_paper_data(
    title: str = "Test Paper",
    doi: str = "10.1234/test",
    s2_id: str = "abc123",
    has_pdf: bool = True,
    has_abstract: bool = True,
) -> dict[str, Any]:
    """创建模拟的 S2 论文数据。"""
    paper: dict[str, Any] = {
        "paperId": s2_id,
        "title": title,
        "year": 2023,
        "citationCount": 100,
        "url": f"https://www.semanticscholar.org/paper/{s2_id}",
        "externalIds": {"DOI": doi},
        "venue": {"name": "Nature Communications"},
        "authors": [
            {"authorId": "1", "name": "Alice Researcher"},
            {"authorId": "2", "name": "Bob Scientist"},
        ],
    }

    if has_abstract:
        paper["abstract"] = "This is the abstract text of the paper."

    if has_pdf:
        paper["openAccessPdf"] = {
            "url": f"https://example.com/{s2_id}.pdf",
            "status": "GOLD",
        }
    else:
        paper["openAccessPdf"] = None

    return paper


def _mock_search_response(papers: list[dict[str, Any]]) -> dict[str, Any]:
    """创建模拟的 S2 搜索响应。"""
    return {
        "total": len(papers),
        "offset": 0,
        "data": papers,
    }


@pytest.fixture
def provider() -> SemanticScholarProvider:
    """创建一个用于测试的 Semantic Scholar 提供者。"""
    return SemanticScholarProvider(api_key="test-key")


@pytest.mark.asyncio
async def test_search_returns_papers(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """搜索返回 Paper 对象列表。"""
    search_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"search?query=Test+Paper&limit=5&fields={search_fields}"
        ),
        json=_mock_search_response(
            [
                _mock_paper_data("Test Paper", doi="10.1234/paper1", s2_id="p1"),
                _mock_paper_data("Another Paper", doi="10.1234/paper2", s2_id="p2"),
            ]
        ),
    )

    results = await provider.search("Test Paper")
    assert len(results) == 2
    assert results[0].title == "Test Paper"
    assert results[0].provider == PaperSource.SEMANTIC_SCHOLAR


@pytest.mark.asyncio
async def test_search_empty_results(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """无结果时搜索返回空列表。"""
    search_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"search?query=NoSuchPaper&limit=5&fields={search_fields}"
        ),
        json={"total": 0, "data": []},
    )

    results = await provider.search("NoSuchPaper")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_parse_authors_and_abstract(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """正确解析作者和摘要。"""
    search_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"search?query=Test+Paper&limit=5&fields={search_fields}"
        ),
        json=_mock_search_response([_mock_paper_data("Test Paper")]),
    )

    results = await provider.search("Test Paper")
    paper = results[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Alice Researcher"
    assert paper.abstract == "This is the abstract text of the paper."
    assert paper.citation_count == 100
    assert paper.venue == "Nature Communications"


@pytest.mark.asyncio
async def test_paper_without_abstract(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """没有摘要的论文获得空字符串。"""
    search_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"search?query=No+Abstract&limit=5&fields={search_fields}"
        ),
        json=_mock_search_response([_mock_paper_data("No Abstract", has_abstract=False)]),
    )

    results = await provider.search("No Abstract")
    assert results[0].abstract == ""


@pytest.mark.asyncio
async def test_pdf_url_extracted(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """从论文数据中提取开放获取 PDF URL。"""
    search_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"search?query=OA+Paper&limit=5&fields={search_fields}"
        ),
        json=_mock_search_response([_mock_paper_data("OA Paper", s2_id="oa1")]),
    )

    results = await provider.search("OA Paper")
    paper = results[0]
    assert paper.pdf_url is not None
    assert "oa1" in paper.pdf_url
    assert paper.open_access is True


@pytest.mark.asyncio
async def test_paper_without_pdf(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """没有 OA PDF 的论文 pdf_url 为 None。"""
    search_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"search?query=Closed+Paper&limit=5&fields={search_fields}"
        ),
        json=_mock_search_response([_mock_paper_data("Closed Paper", has_pdf=False)]),
    )

    paper = (await provider.search("Closed Paper"))[0]
    assert paper.pdf_url is None
    assert paper.open_access is False


@pytest.mark.asyncio
async def test_get_metadata_by_doi(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """可以通过 DOI 获取元数据。"""
    paper_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url,license"
    )
    doi = "10.1234/test"
    httpx_mock.add_response(
        url=(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={paper_fields}"),
        json=_mock_paper_data(doi=doi),
    )

    paper = await provider.get_metadata(doi)
    assert paper.doi == doi
    assert paper.title == "Test Paper"


@pytest.mark.asyncio
async def test_get_metadata_not_found(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """不存在的论文抛出 ProviderNotFoundError。"""
    paper_fields = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url,license"
    )
    missing_doi = "10.9999/missing"
    httpx_mock.add_response(
        url=(
            f"https://api.semanticscholar.org/graph/v1/paper/"
            f"DOI:{missing_doi}?fields={paper_fields}"
        ),
        status_code=404,
        json={"error": "Not found"},
    )

    with pytest.raises(ProviderNotFoundError):
        await provider.get_metadata(missing_doi)


@pytest.mark.asyncio
async def test_get_pdf_url_by_doi(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """通过 DOI 获取 PDF URL。"""
    paper = Paper(title="Test", doi="10.1234/test")
    httpx_mock.add_response(
        url=(
            "https://api.semanticscholar.org/graph/v1/paper/"
            "DOI:10.1234/test?fields=openAccessPdf,externalIds"
        ),
        json={
            "openAccessPdf": {
                "url": "https://example.com/test.pdf",
                "status": "GOLD",
            },
            "externalIds": {"DOI": "10.1234/test"},
        },
    )

    pdf_url = await provider.get_pdf_url(paper)
    assert pdf_url == "https://example.com/test.pdf"


@pytest.mark.asyncio
async def test_close_client(provider: SemanticScholarProvider) -> None:
    """客户端可以干净地关闭。"""
    await provider._get_client()
    await provider.close()
    assert provider._client is None or provider._client.is_closed
