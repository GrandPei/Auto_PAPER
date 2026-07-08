"""Tests for CrossRef provider."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from paper_downloader.models import PaperSource
from paper_downloader.providers.base import ProviderNotFoundError
from paper_downloader.providers.crossref import CrossRefProvider


def _mock_work(
    title: str = "Test Paper",
    doi: str = "10.1234/test",
    publisher: str = "Nature Publishing Group",
    journal: str = "Nature Communications",
    year: int = 2023,
) -> dict[str, Any]:
    """Create a mock CrossRef work object."""
    return {
        "DOI": doi,
        "title": [title],
        "abstract": "<p>This is a test abstract.</p>",
        "publisher": publisher,
        "container-title": [journal],
        "author": [
            {
                "given": "John",
                "family": "Smith",
                "ORCID": "https://orcid.org/0000-0001-1234-5678",
                "affiliation": [{"name": "MIT"}],
            },
            {
                "given": "Jane",
                "family": "Doe",
                "affiliation": [],
            },
        ],
        "published-print": {
            "date-parts": [[year, 6, 15]],
        },
        "ISSN": ["2041-1723"],
        "is-referenced-by-count": 50,
        "license": [
            {
                "URL": "https://creativecommons.org/licenses/by/4.0/",
                "start": {"date-parts": [[year, 6, 15]]},
            }
        ],
    }


def _mock_search_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a mock CrossRef search response."""
    return {
        "status": "ok",
        "message": {
            "total-results": len(items),
            "items": items,
        },
    }


@pytest.fixture
def provider() -> CrossRefProvider:
    """Create a CrossRef provider for testing."""
    return CrossRefProvider()


@pytest.mark.asyncio
async def test_search_by_title(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Search by title returns Paper objects with DOI."""
    httpx_mock.add_response(
        url=("https://api.crossref.org/works?query.title=Test+Paper&rows=5&sort=relevance"),
        json=_mock_search_response(
            [
                _mock_work("Test Paper", doi="10.1234/test"),
                _mock_work("Another Paper", doi="10.1234/another"),
            ]
        ),
    )

    results = await provider.search("Test Paper")
    assert len(results) == 2
    assert results[0].doi == "10.1234/test"
    assert results[0].provider == PaperSource.CROSSREF


@pytest.mark.asyncio
async def test_search_parses_publisher_and_journal(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Publisher and journal are parsed from work data."""
    httpx_mock.add_response(
        url=("https://api.crossref.org/works?query.title=Test&rows=5&sort=relevance"),
        json=_mock_search_response(
            [
                _mock_work("Test", publisher="IEEE", journal="IEEE Transactions"),
            ]
        ),
    )

    paper = (await provider.search("Test"))[0]
    assert paper.venue == "IEEE Transactions"


@pytest.mark.asyncio
async def test_parse_authors(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Authors are correctly parsed with affiliations."""
    httpx_mock.add_response(
        url=("https://api.crossref.org/works?query.title=Author+Test&rows=5&sort=relevance"),
        json=_mock_search_response([_mock_work("Author Test")]),
    )

    paper = (await provider.search("Author Test"))[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "John Smith"
    assert paper.authors[0].affiliation == "MIT"
    assert paper.authors[1].name == "Jane Doe"


@pytest.mark.asyncio
async def test_parse_issn_and_license(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """ISSN and license info are extracted."""
    httpx_mock.add_response(
        url=("https://api.crossref.org/works?query.title=License+Test&rows=5&sort=relevance"),
        json=_mock_search_response([_mock_work("License Test")]),
    )

    paper = (await provider.search("License Test"))[0]
    assert paper.license is not None
    assert "creativecommons" in paper.license


@pytest.mark.asyncio
async def test_get_metadata_by_doi(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Metadata can be retrieved by DOI."""
    doi = "10.1234/test"
    httpx_mock.add_response(
        url=f"https://api.crossref.org/works/{doi}",
        json={
            "status": "ok",
            "message": _mock_work(doi=doi),
        },
    )

    paper = await provider.get_metadata(doi)
    assert paper.doi == doi
    assert paper.citation_count == 50


@pytest.mark.asyncio
async def test_get_metadata_not_found(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """ProviderNotFoundError for non-existent DOI."""
    doi = "10.9999/missing"
    httpx_mock.add_response(
        url=f"https://api.crossref.org/works/{doi}",
        status_code=404,
        json={"status": "error"},
    )

    with pytest.raises(ProviderNotFoundError):
        await provider.get_metadata(doi)


@pytest.mark.asyncio
async def test_get_pdf_url_returns_none(
    provider: CrossRefProvider,
) -> None:
    """CrossRef does not provide PDF URLs."""
    from paper_downloader.models import Paper

    paper = Paper(title="Test", doi="10.1234/test")
    result = await provider.get_pdf_url(paper)
    assert result is None


@pytest.mark.asyncio
async def test_empty_search_results(
    provider: CrossRefProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """Empty search returns empty list."""
    httpx_mock.add_response(
        url=("https://api.crossref.org/works?query.title=NoMatch&rows=5&sort=relevance"),
        json={"status": "ok", "message": {"total-results": 0, "items": []}},
    )

    results = await provider.search("NoMatch")
    assert len(results) == 0
