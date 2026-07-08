"""Semantic Scholar provider for paper metadata retrieval.

Semantic Scholar API: https://api.semanticscholar.org/
Graph API: https://api.semanticscholar.org/graph/v1
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


class SemanticScholarProvider(BaseProvider):
    """Provider for Semantic Scholar academic search engine.

    Uses the Semantic Scholar Graph API to search for papers
    and retrieve metadata including abstracts and open access PDFs.
    """

    BASE_URL: str = "https://api.semanticscholar.org/graph/v1"

    # Fields to request from the API
    SEARCH_FIELDS: str = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url"
    )

    PAPER_FIELDS: str = (
        "title,abstract,authors,citationCount,openAccessPdf,"
        "externalIds,venue,year,publicationTypes,url,license"
    )

    def __init__(
        self,
        api_key: str | None = None,
        priority: int = 20,
    ) -> None:
        """Initialize the Semantic Scholar provider.

        Args:
            api_key: API key for higher rate limits.
            priority: Cascade priority (default 20).
        """
        super().__init__(
            name="Semantic Scholar",
            source=PaperSource.SEMANTIC_SCHOLAR,
            priority=priority,
        )
        self._api_key: str | None = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an httpx async client.

        Returns:
            Configured httpx.AsyncClient instance.
        """
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {
                "Accept": "application/json",
            }
            if self._api_key:
                headers["x-api-key"] = self._api_key

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
        """Only retry on server errors and network errors, not 4xx."""
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
            logger.error("Semantic Scholar HTTP error: {} - {}", e.response.status_code, url)
            raise
        except httpx.RequestError as e:
            logger.error("Semantic Scholar request error: {} - {}", type(e).__name__, url)
            raise

    async def search(
        self,
        title: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Search for papers by title in Semantic Scholar.

        Args:
            title: Paper title to search for.
            max_results: Maximum results (default 5).

        Returns:
            List of Paper objects ordered by relevance.
        """
        logger.info("Semantic Scholar: searching for '{}'", title)
        try:
            data = await self._get(
                f"{self.BASE_URL}/paper/search",
                params={
                    "query": title,
                    "limit": max_results,
                    "fields": self.SEARCH_FIELDS,
                },
            )
            papers_data: list[dict[str, Any]] = data.get("data", [])
            logger.info("Semantic Scholar: found {} results for '{}'", len(papers_data), title)
            return [self._parse_paper(paper_data) for paper_data in papers_data]
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise ProviderError(
                self.name,
                f"Search failed for title: {title}",
            )

    async def get_metadata(self, identifier: str) -> Paper:
        """Get metadata by Semantic Scholar paper ID or DOI.

        Args:
            identifier: S2 paper ID (e.g., "649def34f8be52c8b66281af98ae884c09aef38b")
                or DOI (e.g., "10.1038/nature14539").

        Returns:
            Fully populated Paper object.

        Raises:
            ProviderNotFoundError: If the paper is not found.
        """
        logger.info("Semantic Scholar: fetching metadata for '{}'", identifier)

        # Determine if identifier is a DOI or S2 ID
        if identifier.startswith("10."):
            url = f"{self.BASE_URL}/paper/DOI:{identifier}"
        else:
            url = f"{self.BASE_URL}/paper/{identifier}"

        try:
            data = await self._get(
                url,
                params={"fields": self.PAPER_FIELDS},
            )
            return self._parse_paper(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ProviderNotFoundError(self.name, identifier)
            raise ProviderError(self.name, f"Metadata fetch failed: {identifier}")

    async def get_pdf_url(self, paper: Paper) -> str | None:
        """Get open access PDF URL for a paper.

        Args:
            paper: Paper object with identifier set.

        Returns:
            Direct PDF URL or None.
        """
        paper_id: str | None = None

        if paper.doi:
            paper_id = paper.doi
            url = f"{self.BASE_URL}/paper/DOI:{paper.doi}"
        elif paper.url and "semanticscholar.org" in paper.url:
            # Extract paper ID from URL
            paper_id = paper.url.rstrip("/").split("/")[-1]
            url = f"{self.BASE_URL}/paper/{paper_id}"
        else:
            logger.warning("Semantic Scholar: need DOI or paper URL to get PDF")
            return None

        try:
            data = await self._get(
                url,
                params={"fields": "openAccessPdf,externalIds"},
            )
            oa_pdf = data.get("openAccessPdf")
            if oa_pdf and oa_pdf.get("url"):
                pdf_url: str = oa_pdf["url"]
                paper.pdf_url = pdf_url
                paper.open_access = True
                logger.info("Semantic Scholar: found OA PDF at {}", pdf_url)
                return pdf_url

            logger.info("Semantic Scholar: no OA PDF available for {}", paper_id)
            return None
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.warning("Semantic Scholar: failed to get PDF URL for {}", paper_id)
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

    def _parse_paper(self, paper_data: dict[str, Any]) -> Paper:
        """Parse a Semantic Scholar paper object into a Paper model.

        Args:
            paper_data: Raw paper data from the S2 API.

        Returns:
            Parsed Paper instance.
        """
        # Parse authors
        authors: list[Author] = []
        for author_data in paper_data.get("authors", []):
            authors.append(
                Author(
                    name=author_data.get("name", "Unknown"),
                    orcid=None,
                    affiliation=None,
                )
            )

        # Extract DOI from externalIds
        external_ids: dict[str, Any] = paper_data.get("externalIds", {}) or {}
        doi: str | None = external_ids.get("DOI")

        # Open access PDF
        oa_pdf: dict[str, Any] | None = paper_data.get("openAccessPdf")
        pdf_url: str | None = oa_pdf.get("url") if oa_pdf else None
        is_oa: bool = pdf_url is not None

        # Venue
        venue_data = paper_data.get("venue", {}) or {}
        venue: str = venue_data.get("name", "") or ""

        # Use publication venue name extraction for journal/conference display_name
        journal_info = paper_data.get("journal") or {}
        if not venue and journal_info:
            venue = journal_info.get("name", "")

        return Paper(
            title=paper_data.get("title", "Unknown Title"),
            authors=authors,
            abstract=paper_data.get("abstract") or "",
            year=paper_data.get("year"),
            venue=venue,
            doi=doi,
            url=paper_data.get("url", ""),
            pdf_url=pdf_url,
            provider=PaperSource.SEMANTIC_SCHOLAR,
            citation_count=paper_data.get("citationCount", 0),
            open_access=is_oa,
            license=paper_data.get("license"),
        )
