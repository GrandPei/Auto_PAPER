"""arXiv provider for paper metadata and PDF retrieval.

arXiv API: https://info.arxiv.org/help/api/
Uses the official arXiv OAI-PMH and query API.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from xml.etree import ElementTree

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


@dataclass
class ArxivEntry:
    """Parsed arXiv API entry."""

    arxiv_id: str = ""
    title: str = ""
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    published: str = ""
    updated: str = ""
    doi: str | None = None
    pdf_url: str = ""
    category: str = ""
    version: str = ""
    comment: str = ""
    journal_ref: str = ""


class ArxivProvider(BaseProvider):
    """Provider for arXiv preprint repository.

    Uses the official arXiv API to search for papers and retrieve
    metadata including PDF links, abstracts, and classification.
    """

    BASE_URL: str = "http://export.arxiv.org/api/query"

    _ARXIV_NS: dict[str, str] = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    def __init__(self, priority: int = 30) -> None:
        """Initialize the arXiv provider.

        Args:
            priority: Cascade priority (default 30).
        """
        super().__init__(
            name="arXiv",
            source=PaperSource.ARXIV,
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
                headers={"Accept": "application/atom+xml"},
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
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=_should_retry,
        reraise=True,
    )
    async def _query(self, params: dict[str, str]) -> str:
        """Query the arXiv API with retry logic.

        Args:
            params: Query parameters.

        Returns:
            Raw XML response text.

        Raises:
            ProviderError: On API errors after retries.
        """
        client = await self._get_client()
        try:
            response = await client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.error("arXiv HTTP error: {} - {}", e.response.status_code, self.BASE_URL)
            raise
        except httpx.RequestError as e:
            logger.error("arXiv request error: {}", type(e).__name__)
            raise

    async def search(
        self,
        title: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Search for papers by title on arXiv.

        Args:
            title: Paper title to search for.
            max_results: Maximum results (default 5).

        Returns:
            List of Paper objects ordered by relevance.
        """
        logger.info("arXiv: searching for '{}'", title)
        try:
            xml_text = await self._query(
                {
                    "search_query": f"ti:{title}",
                    "start": "0",
                    "max_results": str(max_results),
                    "sortBy": "relevance",
                }
            )
            entries = self._parse_feed(xml_text)
            logger.info("arXiv: found {} results for '{}'", len(entries), title)
            return [self._entry_to_paper(entry) for entry in entries]
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise ProviderError(self.name, f"Search failed for title: {title}")

    async def search_by_author(
        self,
        author: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Search for papers by author name on arXiv.

        Args:
            author: Author name to search for.
            max_results: Maximum results (default 5).

        Returns:
            List of Paper objects.
        """
        logger.info("arXiv: searching by author '{}'", author)
        try:
            xml_text = await self._query(
                {
                    "search_query": f"au:{author}",
                    "start": "0",
                    "max_results": str(max_results),
                    "sortBy": "relevance",
                }
            )
            entries = self._parse_feed(xml_text)
            return [self._entry_to_paper(entry) for entry in entries]
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise ProviderError(self.name, f"Author search failed: {author}")

    async def get_metadata(self, identifier: str) -> Paper:
        """Get metadata by arXiv ID.

        Args:
            identifier: arXiv ID (e.g., "1706.03762" or "1706.03762v7").

        Returns:
            Fully populated Paper object.

        Raises:
            ProviderNotFoundError: If the paper is not found.
        """
        logger.info("arXiv: fetching metadata for '{}'", identifier)
        try:
            # Strip version suffix for query
            clean_id = identifier.split("v")[0].strip()
            xml_text = await self._query(
                {
                    "id_list": clean_id,
                    "max_results": "1",
                }
            )
            entries = self._parse_feed(xml_text)
            if not entries:
                raise ProviderNotFoundError(self.name, identifier)
            return self._entry_to_paper(entries[0])
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise ProviderError(self.name, f"Metadata fetch failed: {identifier}")

    async def get_pdf_url(self, paper: Paper) -> str | None:
        """Get the PDF URL for an arXiv paper.

        Constructs the standard arXiv PDF URL from the paper ID.

        Args:
            paper: Paper object with arXiv URL or ID.

        Returns:
            Direct PDF URL or None.
        """
        # Try to extract arXiv ID from URL
        arxiv_id: str | None = None

        if paper.url:
            match = re.search(r"arxiv\.org/abs/([\w.\-]+)", paper.url)
            if match:
                arxiv_id = match.group(1).split("v")[0]

        if arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            paper.pdf_url = pdf_url
            paper.open_access = True
            logger.info("arXiv: PDF URL set to {}", pdf_url)
            return pdf_url

        logger.warning("arXiv: could not determine arXiv ID from paper URL")
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

    def _parse_feed(self, xml_text: str) -> list[ArxivEntry]:
        """Parse the arXiv Atom XML feed.

        Args:
            xml_text: Raw XML response text.

        Returns:
            List of parsed ArxivEntry objects.
        """
        root = ElementTree.fromstring(xml_text)
        entries: list[ArxivEntry] = []

        for entry_elem in root.findall("atom:entry", self._ARXIV_NS):
            entry = ArxivEntry()

            # Extract arXiv ID from the <id> element
            id_elem = entry_elem.find("atom:id", self._ARXIV_NS)
            if id_elem is not None and id_elem.text:
                entry.arxiv_id = id_elem.text.split("/abs/")[-1]

            # Title
            title_elem = entry_elem.find("atom:title", self._ARXIV_NS)
            if title_elem is not None and title_elem.text:
                entry.title = title_elem.text.strip()

            # Summary (abstract)
            summary_elem = entry_elem.find("atom:summary", self._ARXIV_NS)
            if summary_elem is not None and summary_elem.text:
                entry.summary = summary_elem.text.strip()

            # Published date
            published_elem = entry_elem.find("atom:published", self._ARXIV_NS)
            if published_elem is not None and published_elem.text:
                entry.published = published_elem.text

            # Updated date
            updated_elem = entry_elem.find("atom:updated", self._ARXIV_NS)
            if updated_elem is not None and updated_elem.text:
                entry.updated = updated_elem.text

            # Authors
            for author_elem in entry_elem.findall("atom:author", self._ARXIV_NS):
                name_elem = author_elem.find("atom:name", self._ARXIV_NS)
                if name_elem is not None and name_elem.text:
                    entry.authors.append(name_elem.text.strip())

            # DOI
            for link_elem in entry_elem.findall("atom:link", self._ARXIV_NS):
                href = link_elem.get("href", "")
                title_attr = link_elem.get("title", "")
                if "doi" in title_attr.lower() or "dx.doi.org" in href:
                    entry.doi = href.replace("http://dx.doi.org/", "").replace(
                        "https://doi.org/", ""
                    )

            # PDF link
            for link_elem in entry_elem.findall("atom:link", self._ARXIV_NS):
                title_attr = link_elem.get("title", "")
                if title_attr == "pdf":
                    entry.pdf_url = link_elem.get("href", "")

            # Primary category
            cat_elem = entry_elem.find("arxiv:primary_category", self._ARXIV_NS)
            if cat_elem is not None:
                entry.category = cat_elem.get("term", "")

            # Journal ref
            journal_elem = entry_elem.find("arxiv:journal_ref", self._ARXIV_NS)
            if journal_elem is not None and journal_elem.text:
                entry.journal_ref = journal_elem.text.strip()

            # Comment (version info etc.)
            comment_elem = entry_elem.find("arxiv:comment", self._ARXIV_NS)
            if comment_elem is not None and comment_elem.text:
                entry.comment = comment_elem.text.strip()

            entries.append(entry)

        return entries

    def _entry_to_paper(self, entry: ArxivEntry) -> Paper:
        """Convert an ArxivEntry to a Paper model.

        Args:
            entry: Parsed arXiv entry.

        Returns:
            Paper instance.
        """
        # Extract year from published date
        year: int | None = None
        if entry.published:
            with contextlib.suppress(ValueError, IndexError):
                year = int(entry.published[:4])

        # Build authors list
        authors = [Author(name=name) for name in entry.authors]

        # Venue: prefer journal ref, fallback to category
        venue = entry.journal_ref if entry.journal_ref else entry.category

        # PDF URL - construct standard URL if not provided
        pdf_url = entry.pdf_url
        if not pdf_url and entry.arxiv_id:
            clean_id = entry.arxiv_id.split("v")[0]
            pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

        return Paper(
            title=entry.title,
            authors=authors,
            abstract=entry.summary,
            year=year,
            venue=venue,
            doi=entry.doi,
            url=f"https://arxiv.org/abs/{entry.arxiv_id}" if entry.arxiv_id else "",
            pdf_url=pdf_url if pdf_url else None,
            provider=PaperSource.ARXIV,
            citation_count=0,
            open_access=True,  # arXiv papers are always open access
            license=None,
        )
