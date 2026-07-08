"""CrossRef provider for paper metadata retrieval via DOI.

CrossRef API: https://api.crossref.org/
REST endpoint: https://api.crossref.org/works
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from paper_downloader.models import Author, Paper, PaperSource
from paper_downloader.providers.base import (
    BaseProvider,
    ProviderError,
    ProviderNotFoundError,
)


class CrossRefProvider(BaseProvider):
    """Provider for CrossRef DOI registration agency.

    Retrieves paper metadata by DOI and supports title-to-DOI
    search using the CrossRef REST API.
    """

    BASE_URL: str = "https://api.crossref.org"

    def __init__(self, priority: int = 40) -> None:
        """Initialize the CrossRef provider.

        Args:
            priority: Cascade priority (default 40).
        """
        super().__init__(
            name="CrossRef",
            source=PaperSource.CROSSREF,
            priority=priority,
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an httpx async client.

        Returns:
            Configured httpx.AsyncClient instance.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Accept": "application/json",
                    "User-Agent": "PaperDownloader/0.1 (https://github.com/paper-downloader)",
                },
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _should_retry(exception: BaseException) -> bool:
        """Only retry on server errors and network errors."""
        if isinstance(exception, httpx.HTTPStatusError):
            return 500 <= exception.response.status_code < 600
        return isinstance(exception, httpx.RequestError)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=_should_retry,
        reraise=True,
    )
    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a GET request with retry logic.

        Args:
            url: Full URL to request.
            params: Query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            ProviderError: On API errors after retries.
        """
        client = await self._get_client()
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            logger.error("CrossRef HTTP error: {} - {}", e.response.status_code, url)
            raise
        except httpx.RequestError as e:
            logger.error("CrossRef request error: {}", type(e).__name__)
            raise

    async def search(
        self,
        title: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Search for papers by title to find DOIs.

        Args:
            title: Paper title to search for.
            max_results: Maximum results (default 5).

        Returns:
            List of Paper objects with DOI populated.
        """
        logger.info("CrossRef: searching for '{}'", title)
        try:
            data = await self._get(
                f"{self.BASE_URL}/works",
                params={
                    "query.title": title,
                    "rows": max_results,
                    "sort": "relevance",
                },
            )
            items: list[dict[str, Any]] = data.get("message", {}).get("items", [])
            logger.info("CrossRef: found {} results for '{}'", len(items), title)
            return [self._parse_work(item) for item in items]
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise ProviderError(self.name, f"Search failed for title: {title}")

    async def get_metadata(self, identifier: str) -> Paper:
        """Get metadata by DOI.

        Args:
            identifier: DOI string (e.g., "10.1038/nature14539").

        Returns:
            Fully populated Paper object.

        Raises:
            ProviderNotFoundError: If the DOI is not found.
        """
        logger.info("CrossRef: fetching metadata for DOI '{}'", identifier)
        try:
            data = await self._get(f"{self.BASE_URL}/works/{identifier}")
            work: dict[str, Any] = data.get("message", {})
            if not work:
                raise ProviderNotFoundError(self.name, identifier)
            return self._parse_work(work)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ProviderNotFoundError(self.name, identifier)
            raise ProviderError(self.name, f"Metadata fetch failed: {identifier}")

    async def get_pdf_url(self, paper: Paper) -> str | None:
        """CrossRef does not provide direct PDF URLs.

        This method relies on Unpaywall or other OA providers
        for PDF discovery.

        Args:
            paper: Paper object.

        Returns:
            Always None for CrossRef.
        """
        logger.info("CrossRef: PDF discovery not supported, use Unpaywall")
        return None

    async def download(self, paper: Paper, destination: str) -> Paper:
        """Download is delegated to the DownloadManager.

        Args:
            paper: Paper object.
            destination: Destination path.

        Returns:
            The paper object unchanged.
        """
        return paper

    def _parse_work(self, work: dict[str, Any]) -> Paper:
        """Parse a CrossRef work object into a Paper model.

        Args:
            work: Raw work data from the CrossRef API.

        Returns:
            Parsed Paper instance.
        """
        # Parse authors
        authors: list[Author] = []
        for author_data in work.get("author", []) or []:
            given = author_data.get("given", "")
            family = author_data.get("family", "")
            name = (
                f"{given} {family}".strip()
                if (given or family)
                else author_data.get("name", "Unknown")
            )
            affiliation_list = author_data.get("affiliation", [])
            affiliation = affiliation_list[0].get("name") if affiliation_list else None
            authors.append(
                Author(name=name, orcid=author_data.get("ORCID"), affiliation=affiliation)
            )

        # DOI
        doi: str | None = work.get("DOI")

        # Publisher
        publisher: str = work.get("publisher", "")

        # Journal/venue
        container_title: list[str] = work.get("container-title", []) or []
        journal: str = container_title[0] if container_title else ""

        # Use publisher as venue if no journal
        venue: str = journal if journal else publisher

        # Year
        year: int | None = None
        published = work.get("published-print") or work.get("published-online") or {}
        date_parts = published.get("date-parts", [[]])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        # ISSN
        issn_list: list[str] = work.get("ISSN", []) or []
        issn_list[0] if issn_list else None

        # License
        license_list: list[dict[str, Any]] = work.get("license", []) or []
        license_info: str | None = None
        if license_list:
            license_info = license_list[0].get("URL", "")

        # Abstract
        abstract: str = work.get("abstract", "") or ""

        # URL
        url: str = f"https://doi.org/{doi}" if doi else ""

        return Paper(
            title=work.get("title", ["Unknown Title"])[0] if work.get("title") else "Unknown Title",
            authors=authors,
            abstract=abstract,
            year=year,
            venue=venue,
            doi=doi,
            url=url,
            pdf_url=None,
            provider=PaperSource.CROSSREF,
            citation_count=work.get("is-referenced-by-count", 0),
            open_access=False,
            license=license_info or None,
        )
