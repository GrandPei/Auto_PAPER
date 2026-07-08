"""OpenAlex provider for paper metadata retrieval.

OpenAlex API: https://docs.openalex.org/
REST endpoint: https://api.openalex.org/works
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


class OpenAlexProvider(BaseProvider):
    """Provider for OpenAlex bibliometric database.

    Uses the official OpenAlex REST API to search for papers
    and retrieve metadata including open access PDF locations.
    """

    BASE_URL: str = "https://api.openalex.org"

    def __init__(self, email: str | None = None, priority: int = 10) -> None:
        """Initialize the OpenAlex provider.

        Args:
            email: Contact email for the polite pool (higher rate limits).
            priority: Cascade priority (default 10 = first to try).
        """
        super().__init__(
            name="OpenAlex",
            source=PaperSource.OPENALEX,
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
            headers: dict[str, str] = {
                "User-Agent": f"PaperDownloader/0.1 (mailto:{self._email or 'anonymous@example.com'})",
                "Accept": "application/json",
            }
            self._client = httpx.AsyncClient(
                headers=headers,
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
        """Only retry on server errors (5xx) and network errors, not client errors (4xx)."""
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
            ProviderError: On HTTP or request errors after retries.
        """
        client = await self._get_client()
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            logger.error("OpenAlex HTTP error: {} - {}", e.response.status_code, url)
            raise
        except httpx.RequestError as e:
            logger.error("OpenAlex request error: {} - {}", type(e).__name__, url)
            raise

    async def search(
        self,
        title: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Search for papers by title in OpenAlex.

        Args:
            title: Paper title to search for.
            max_results: Maximum results (default 5).

        Returns:
            List of Paper objects ordered by relevance.
        """
        logger.info("OpenAlex: searching for '{}'", title)
        try:
            data = await self._get(
                f"{self.BASE_URL}/works",
                params={
                    "search": title,
                    "per_page": max_results,
                    "sort": "relevance_score:desc",
                },
            )
            results: list[dict[str, Any]] = data.get("results", [])
            logger.info("OpenAlex: found {} results for '{}'", len(results), title)
            return [self._parse_work(work) for work in results]
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise ProviderError(
                self.name,
                f"Search failed for title: {title}",
            )

    async def get_metadata(self, identifier: str) -> Paper:
        """Get metadata by OpenAlex work ID or DOI.

        Args:
            identifier: OpenAlex work ID (e.g., "W2741809807") or DOI.

        Returns:
            Fully populated Paper object.

        Raises:
            ProviderNotFoundError: If the work is not found.
        """
        logger.info("OpenAlex: fetching metadata for '{}'", identifier)
        try:
            # Support both DOI and OpenAlex ID
            if identifier.startswith("10."):
                url = f"{self.BASE_URL}/works/doi:{identifier}"
            elif identifier.startswith("W"):
                url = f"{self.BASE_URL}/works/{identifier}"
            else:
                url = f"{self.BASE_URL}/works/doi:{identifier}"

            data = await self._get(url)
            return self._parse_work(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ProviderNotFoundError(self.name, identifier)
            raise ProviderError(self.name, f"Metadata fetch failed: {identifier}")

    async def get_pdf_url(self, paper: Paper) -> str | None:
        """Get the best open access PDF URL for a paper.

        Uses OpenAlex's best_oa_location data.

        Args:
            paper: Paper object with DOI set.

        Returns:
            Direct PDF URL or None.
        """
        if not paper.doi:
            logger.warning("OpenAlex: cannot get PDF URL - no DOI on paper")
            return None

        try:
            data = await self._get(f"{self.BASE_URL}/works/doi:{paper.doi}")
            oa_location = data.get("best_oa_location") or {}
            pdf_url = oa_location.get("pdf_url")
            if pdf_url:
                paper.pdf_url = pdf_url
                paper.open_access = True
                paper.license = oa_location.get("license")
                logger.info("OpenAlex: found OA PDF at {}", pdf_url)
            else:
                logger.info("OpenAlex: no OA PDF available for {}", paper.doi)
            return pdf_url
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.warning("OpenAlex: failed to get PDF URL for {}", paper.doi)
            return None

    async def download(self, paper: Paper, destination: str) -> Paper:
        """Download is handled by the DownloadManager, not individual providers.

        Args:
            paper: Paper object.
            destination: Destination path.

        Returns:
            The paper object unchanged.
        """
        # Download is delegated to the DownloadManager
        return paper

    def _parse_work(self, work: dict[str, Any]) -> Paper:
        """Parse an OpenAlex work object into a Paper model.

        Args:
            work: Raw work object from the OpenAlex API.

        Returns:
            Parsed Paper instance.
        """
        # Parse authors
        authors: list[Author] = []
        for authorship in work.get("authorships", []):
            author_info = authorship.get("author", {})
            institutions = authorship.get("institutions", [])
            affiliation = institutions[0].get("display_name") if institutions else None
            authors.append(
                Author(
                    name=author_info.get("display_name", "Unknown"),
                    orcid=author_info.get("orcid"),
                    affiliation=affiliation,
                )
            )

        # Extract best OA location
        best_oa = work.get("best_oa_location") or {}
        pdf_url: str | None = best_oa.get("pdf_url")
        oa_license: str | None = best_oa.get("license")
        is_oa: bool = bool(work.get("open_access", {}).get("is_oa", False))

        # Extract DOI
        doi: str | None = work.get("doi")
        if doi:
            # Remove "https://doi.org/" prefix if present
            doi = doi.replace("https://doi.org/", "")

        # Publication year
        year: int | None = work.get("publication_year")

        # Venue
        primary_location = work.get("primary_location", {}) or {}
        source = primary_location.get("source", {}) or {}
        venue: str = source.get("display_name", "")

        return Paper(
            title=work.get("title", "Unknown Title"),
            authors=authors,
            abstract="",  # OpenAlex doesn't include abstracts in search results
            year=year,
            venue=venue,
            doi=doi,
            url=work.get("id", ""),
            pdf_url=pdf_url,
            provider=PaperSource.OPENALEX,
            citation_count=work.get("cited_by_count", 0),
            open_access=is_oa,
            license=oa_license,
        )
