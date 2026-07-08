"""Tests for Semantic Scholar provider."""

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
    """Create mock S2 paper data."""
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
    """Create mock S2 search response."""
    return {
        "total": len(papers),
        "offset": 0,
        "data": papers,
    }


@pytest.fixture
def provider() -> SemanticScholarProvider:
    """Create a Semantic Scholar provider for testing."""
    return SemanticScholarProvider(api_key="test-key")


@pytest.mark.asyncio
async def test_search_returns_papers(
    provider: SemanticScholarProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Search returns a list of Paper objects."""
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
    """Search returns empty list when no results."""
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
    """Authors and abstract are parsed correctly."""
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
    """Paper without abstract gets empty string."""
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
    """Open access PDF URL is extracted from paper data."""
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
    """Paper without OA PDF has None pdf_url."""
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
    """Metadata can be retrieved by DOI."""
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
    """ProviderNotFoundError raised for non-existent paper."""
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
    """PDF URL is fetched by DOI."""
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
    """Client can be closed cleanly."""
    await provider._get_client()
    await provider.close()
    assert provider._client is None or provider._client.is_closed
