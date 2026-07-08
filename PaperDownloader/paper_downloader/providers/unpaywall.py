"""Unpaywall provider for open access PDF discovery via DOI.

Unpaywall API: https://unpaywall.org/products/api
REST endpoint: https://api.unpaywall.org/v2/{doi}?email={email}
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


class UnpaywallProvider(BaseProvider):
    """Provider for Unpaywall open access PDF discovery.

    Takes a DOI as input and returns open access PDF location
    along with license and repository information.
    """

    BASE_URL: str = "https://api.unpaywall.org/v2"

    def __init__(self, email: str | None = None, priority: int = 50) -> None:
        """Initialize the Unpaywall provider.

        Args:
            email: Contact email (required for fair-use API access).
            priority: Cascade priority (default 50).
        """
        super().__init__(
            name="Unpaywall",
            source=PaperSource.UNPAYWALL,
            priority=priority,
        )
        self._email: str | None = email
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
                    "User-Agent": "PaperDownloader/0.1",
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
            logger.error("Unpaywall HTTP error: {} - {}", e.response.status_code, url)
            raise
        except httpx.RequestError as e:
            logger.error("Unpaywall request error: {}", type(e).__name__)
            raise

    async def search(
        self,
        title: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Unpaywall does not support title search; use search_by_doi instead.

        Args:
            title: Paper title (ignored for Unpaywall).
            max_results: Ignored.

        Returns:
            Empty list (title search not supported).
        """
        logger.warning("Unpaywall: title search not supported, use DOI")
        return []

    async def get_metadata(self, identifier: str) -> Paper:
        """Get open access metadata by DOI.

        Args:
            identifier: DOI string (e.g., "10.1038/nature14539").

        Returns:
            Paper object with OA PDF URL if available.

        Raises:
            ProviderNotFoundError: If the DOI is not found.
        """
        logger.info("Unpaywall: looking up DOI '{}'", identifier)
        params: dict[str, str] = {"email": self._email or "anonymous@example.com"}
        try:
            data = await self._get(
                f"{self.BASE_URL}/{identifier}",
                params=params,
            )
            return self._parse_response(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ProviderNotFoundError(self.name, identifier)
            raise ProviderError(self.name, f"Lookup failed for DOI: {identifier}")

    async def get_pdf_url(self, paper: Paper) -> str | None:
        """Get open access PDF URL for a DOI.

        If the paper already has a pdf_url set, it is returned directly.
        Otherwise the Unpaywall API is queried.

        Args:
            paper: Paper object with DOI set.

        Returns:
            PDF URL or None.
        """
        if not paper.doi:
            logger.warning("Unpaywall: no DOI on paper, cannot look up")
            return None

        if paper.pdf_url:
            return paper.pdf_url

        try:
            metadata = await self.get_metadata(paper.doi)
            if metadata.pdf_url:
                paper.pdf_url = metadata.pdf_url
                paper.open_access = metadata.open_access
                paper.license = metadata.license
                logger.info("Unpaywall: found OA PDF at {}", metadata.pdf_url)
                return metadata.pdf_url
        except (ProviderError, ProviderNotFoundError):
            logger.info("Unpaywall: no OA PDF for DOI {}", paper.doi)

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

    def _parse_response(self, data: dict[str, Any]) -> Paper:
        """Parse an Unpaywall API response into a Paper model.

        Args:
            data: Raw API response data.

        Returns:
            Parsed Paper instance.
        """
        doi: str | None = data.get("doi")
        title: str = data.get("title", "Unknown Title")
        is_oa: bool = data.get("is_oa", False)

        # Best OA location
        best_location: dict[str, Any] | None = data.get("best_oa_location")
        pdf_url: str | None = None
        oa_license: str | None = None

        if best_location:
            pdf_url = best_location.get("url_for_pdf")
            oa_license = best_location.get("license")
            best_location.get("host_type", "")
            best_location.get("version", "")

        # Authors from z_authors
        authors: list[Author] = []
        for author_data in data.get("z_authors", []) or []:
            given = author_data.get("given", "")
            family = author_data.get("family", "")
            name = f"{given} {family}".strip() or author_data.get("name", "Unknown")
            authors.append(Author(name=name))

        # Year
        year: int | None = data.get("year")

        # Venue
        venue: str = data.get("journal_name", "") or ""

        return Paper(
            title=title,
            authors=authors,
            abstract="",
            year=year,
            venue=venue,
            doi=doi,
            url=f"https://doi.org/{doi}" if doi else "",
            pdf_url=pdf_url,
            provider=PaperSource.UNPAYWALL,
            citation_count=0,
            open_access=is_oa,
            license=oa_license,
        )
