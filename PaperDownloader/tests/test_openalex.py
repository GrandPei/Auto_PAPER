"""Tests for OpenAlex provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from paper_downloader.models import PaperSource
from paper_downloader.providers.base import ProviderNotFoundError
from paper_downloader.providers.openalex import OpenAlexProvider


def _mock_work_response(title: str = "Test Paper", doi: str = "10.1234/test") -> dict[str, Any]:
    """Create a mock OpenAlex work API response."""
    return {
        "id": f"https://openalex.org/W12345",
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "publication_year": 2023,
        "cited_by_count": 42,
        "open_access": {"is_oa": True},
        "best_oa_location": {
            "pdf_url": f"https://example.com/{title.lower().replace(' ', '_')}.pdf",
            "license": "CC BY 4.0",
        },
        "primary_location": {"source": {"display_name": "Nature"}},
        "authorships": [
            {
                "author": {
                    "display_name": "John Smith",
                    "orcid": "https://orcid.org/0000-0001-1234-5678",
                },
                "institutions": [{"display_name": "MIT"}],
            },
            {
                "author": {
                    "display_name": "Jane Doe",
                    "orcid": None,
                },
                "institutions": [],
            },
        ],
    }


def _mock_search_response(
    titles: list[str] | None = None,
) -> dict[str, Any]:
    """Create a mock OpenAlex search API response."""
    if titles is None:
        titles = ["First Paper", "Second Paper"]
    results = [_mock_work_response(title=t, doi=f"10.1234/test{i}") for i, t in enumerate(titles)]
    return {
        "meta": {"count": len(results), "per_page": 25},
        "results": results,
    }


@pytest.fixture
def provider() -> OpenAlexProvider:
    """Create an OpenAlex provider instance for testing."""
    return OpenAlexProvider(email="test@example.com")


@pytest.mark.asyncio
async def test_search_returns_papers(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Search returns a list of Paper objects."""
    httpx_mock.add_response(
        url="https://api.openalex.org/works?search=Test+Paper&per_page=5&sort=relevance_score%3Adesc",
        json=_mock_search_response(["Test Paper", "Another Paper"]),
    )

    results = await provider.search("Test Paper")
    assert len(results) == 2
    assert results[0].title == "Test Paper"
    assert results[0].provider == PaperSource.OPENALEX


@pytest.mark.asyncio
async def test_search_empty_results(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Search returns empty list when no results found."""
    httpx_mock.add_response(
        url="https://api.openalex.org/works?search=NoSuchPaper&per_page=5&sort=relevance_score%3Adesc",
        json={"meta": {"count": 0}, "results": []},
    )

    results = await provider.search("NoSuchPaper")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_parse_authors(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Paper authors are correctly parsed from API response."""
    httpx_mock.add_response(
        url="https://api.openalex.org/works?search=Paper+With+Authors&per_page=5&sort=relevance_score%3Adesc",
        json=_mock_search_response(["Paper With Authors"]),
    )

    results = await provider.search("Paper With Authors")
    paper = results[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "John Smith"
    assert paper.authors[0].orcid == "https://orcid.org/0000-0001-1234-5678"
    assert paper.authors[0].affiliation == "MIT"
    assert paper.authors[1].name == "Jane Doe"
    assert paper.authors[1].affiliation is None


@pytest.mark.asyncio
async def test_parse_paper_fields(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """All relevant fields are parsed from the work object."""
    httpx_mock.add_response(
        url="https://api.openalex.org/works?search=Test+Paper&per_page=5&sort=relevance_score%3Adesc",
        json=_mock_search_response(["Test Paper"]),
    )

    results = await provider.search("Test Paper")
    paper = results[0]

    assert paper.title == "Test Paper"
    assert paper.doi == "10.1234/test0"
    assert paper.year == 2023
    assert paper.venue == "Nature"
    assert paper.citation_count == 42
    assert paper.open_access is True
    assert paper.license == "CC BY 4.0"
    assert paper.pdf_url is not None


@pytest.mark.asyncio
async def test_get_metadata_by_doi(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Metadata can be retrieved by DOI."""
    doi = "10.1234/test"
    httpx_mock.add_response(
        url=f"https://api.openalex.org/works/doi:{doi}",
        json=_mock_work_response(doi=doi),
    )

    paper = await provider.get_metadata(doi)
    assert paper.doi == doi
    assert paper.title == "Test Paper"


@pytest.mark.asyncio
async def test_get_metadata_not_found(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """ProviderNotFoundError raised for non-existent DOI."""
    doi = "10.9999/nonexistent"
    httpx_mock.add_response(
        url=f"https://api.openalex.org/works/doi:{doi}",
        status_code=404,
        json={"error": "not found"},
    )

    with pytest.raises(ProviderNotFoundError):
        await provider.get_metadata(doi)


@pytest.mark.asyncio
async def test_get_pdf_url(
    provider: OpenAlexProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """PDF URL is extracted from best_oa_location."""
    from paper_downloader.models import Paper

    paper = Paper(title="Test", doi="10.1234/test")
    httpx_mock.add_response(
        url=f"https://api.openalex.org/works/doi:{paper.doi}",
        json=_mock_work_response(title="Test", doi=paper.doi),
    )

    pdf_url = await provider.get_pdf_url(paper)
    assert pdf_url is not None
    assert "example.com" in pdf_url
    assert paper.open_access is True
    assert paper.license == "CC BY 4.0"


@pytest.mark.asyncio
async def test_get_pdf_url_no_doi(
    provider: OpenAlexProvider,
) -> None:
    """Returns None when paper has no DOI."""
    from paper_downloader.models import Paper

    paper = Paper(title="Test")
    result = await provider.get_pdf_url(paper)
    assert result is None


@pytest.mark.asyncio
async def test_close_client(provider: OpenAlexProvider) -> None:
    """Client can be closed without errors."""
    # Force client creation
    await provider._get_client()
    await provider.close()
    assert provider._client is None or provider._client.is_closed
