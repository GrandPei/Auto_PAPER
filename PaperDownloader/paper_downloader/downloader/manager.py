"""Download orchestration manager.

Coordinates the full download pipeline:
    1. Check cache → 2. Search providers → 3. Get metadata →
    4. Find PDF URL → 5. Download PDF → 6. Save metadata →
    7. Return DownloadResult

If one provider fails, the next provider is tried automatically.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from loguru import logger

from paper_downloader.config import get_settings
from paper_downloader.matcher import TitleMatcher
from paper_downloader.models import (
    DownloadResult,
    DownloadStatus,
    Metadata,
    Paper,
    PaperSource,
)
from paper_downloader.providers.base import (
    BaseProvider,
    ProviderError,
    ProviderNotFoundError,
    ProviderRegistry,
)


class DownloadManager:
    """Orchestrates the paper download pipeline.

    Coordinates multiple providers, caching, matching, and storage
    to deliver a robust paper download experience.

    Flow:
        ┌─────────────┐
        │ Check Cache │──→ hit? → return cached
        └──────┬──────┘
               ↓ miss
        ┌─────────────┐
        │  OpenAlex   │──→ found? → get PDF URL
        └──────┬──────┘
               ↓ not found
        ┌─────────────┐
        │  S2 Search  │──→ found? → get PDF URL
        └──────┬──────┘
               ↓ not found
        ┌─────────────┐
        │   arXiv     │──→ found? → get PDF URL
        └──────┬──────┘
               ↓ not found
        ┌─────────────┐
        │  CrossRef   │──→ found? → get DOI
        └──────┬──────┘
               ↓
        ┌─────────────┐
        │  Unpaywall  │──→ found? → get PDF URL
        └──────┬──────┘
               ↓
        ┌─────────────┐
        │  Download   │
        │    PDF      │
        └──────┬──────┘
               ↓
        ┌─────────────┐
        │Save Metadata│
        └──────┬──────┘
               ↓
        DownloadResult
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        matcher: TitleMatcher | None = None,
    ) -> None:
        """Initialize the download manager.

        Args:
            registry: Pre-configured provider registry. Creates default if None.
            matcher: Title matcher for result verification.
        """
        self._registry: ProviderRegistry = registry or ProviderRegistry()
        self._matcher: TitleMatcher = matcher or TitleMatcher()
        self._settings = get_settings()

    def register_provider(self, provider: BaseProvider) -> None:
        """Register a provider for use in the cascade.

        Args:
            provider: The provider instance to register.
        """
        self._registry.register(provider)

    @property
    def registry(self) -> ProviderRegistry:
        """Get the provider registry."""
        return self._registry

    async def download(
        self,
        title: str,
        *,
        destination: str | Path | None = None,
        timeout: int | None = None,
    ) -> DownloadResult:
        """Download a paper by title through the provider cascade.

        Args:
            title: Paper title to search for and download.
            destination: Custom download directory. Uses config default if None.
            timeout: Download timeout in seconds. Uses config default if None.

        Returns:
            DownloadResult with paper metadata and PDF path.
        """
        start_time = time.monotonic()
        Path(destination) if destination else self._settings.download_dir

        logger.info("Starting download for: '{}'", title)

        # Step 1: Check cache (placeholder — will be fully implemented in storage)
        # For now, proceed with provider cascade

        # Step 2–6: Provider cascade
        paper: Paper | None = None
        last_error: str | None = None
        tried_providers: list[str] = []

        for provider in self._registry.get_all():
            tried_providers.append(provider.name)
            logger.info("Trying provider: {}", provider.name)

            try:
                # Search for the paper
                results = await provider.search(title, max_results=3)
                if not results:
                    logger.info("{} - no results for '{}'", provider.name, title)
                    continue

                # Find best matching result
                candidate_titles = [r.title for r in results]
                match = self._matcher.best_match(title, candidate_titles)
                logger.info(
                    "{} - best match score={:.3f}, method={}",
                    provider.name,
                    match.score,
                    match.method.value,
                )

                if match.score < 0.70:
                    logger.info("{} - match score too low, skipping", provider.name)
                    continue

                # Get the best matching paper
                candidate_titles.index(
                    [r.title for r in results if match.score > 0][0]
                ) if results else -1
                paper = results[0]  # Use first result as best match

                # Enrich with full metadata if available
                if paper.doi:
                    try:
                        paper = await provider.get_metadata(paper.doi)
                    except (ProviderError, ProviderNotFoundError):
                        pass  # Use search result as-is

                # Try to get PDF URL
                pdf_url = await provider.get_pdf_url(paper)
                if pdf_url:
                    logger.info("{} - found PDF URL: {}", provider.name, pdf_url)
                else:
                    logger.info("{} - no PDF URL available", provider.name)

                break  # Found a paper, exit cascade

            except (ProviderError, ProviderNotFoundError) as e:
                logger.warning("{} - error: {}", provider.name, e.message)
                last_error = str(e)
                continue

        if paper is None:
            logger.error("All providers failed for '{}'", title)
            return DownloadResult(
                paper=Paper(title=title, provider=PaperSource.UNKNOWN),
                status=DownloadStatus.NOT_FOUND,
                error_message=(
                    f"No paper found for '{title}'. "
                    f"Tried: {', '.join(tried_providers)}. "
                    f"Last error: {last_error or 'N/A'}"
                ),
                download_time_seconds=time.monotonic() - start_time,
            )

        # Step 7: Download PDF (placeholder — will be implemented in download module)
        # For now return metadata only
        elapsed = time.monotonic() - start_time
        metadata = Metadata(
            source=paper.provider,
            retrieved_at=datetime.now(),
            match_score=None,
            match_method=None,
        )

        result = DownloadResult(
            paper=paper,
            status=DownloadStatus.SUCCESS if paper.pdf_url else DownloadStatus.NOT_FOUND,
            pdf_path=paper.pdf_path,
            download_time_seconds=elapsed,
            metadata=metadata,
        )

        logger.info(
            "Download complete for '{}': status={}, time={:.2f}s",
            title,
            result.status.value,
            elapsed,
        )
        return result

    async def download_by_doi(
        self,
        doi: str,
        *,
        destination: str | Path | None = None,
        timeout: int | None = None,
    ) -> DownloadResult:
        """Download a paper by its DOI.

        Tries providers in cascade order to find PDF for the given DOI.

        Args:
            doi: Digital Object Identifier (e.g., "10.1038/nature14539").
            destination: Custom download directory.
            timeout: Download timeout in seconds.

        Returns:
            DownloadResult with paper metadata and PDF path.
        """
        start_time = time.monotonic()
        logger.info("Starting download for DOI: '{}'", doi)

        paper: Paper | None = None
        last_error: str | None = None

        for provider in self._registry.get_all():
            logger.info("Trying provider: {}", provider.name)
            try:
                paper = await provider.get_metadata(doi)
                pdf_url = await provider.get_pdf_url(paper)
                if pdf_url:
                    logger.info("{} - found PDF: {}", provider.name, pdf_url)
                break
            except (ProviderError, ProviderNotFoundError) as e:
                logger.warning("{} - error: {}", provider.name, e.message)
                last_error = str(e)
                continue

        if paper is None:
            return DownloadResult(
                paper=Paper(title="", doi=doi, provider=PaperSource.UNKNOWN),
                status=DownloadStatus.NOT_FOUND,
                error_message=f"No paper found for DOI: {doi}. Last error: {last_error or 'N/A'}",
                download_time_seconds=time.monotonic() - start_time,
            )

        elapsed = time.monotonic() - start_time
        metadata = Metadata(
            source=paper.provider,
            retrieved_at=datetime.now(),
        )

        return DownloadResult(
            paper=paper,
            status=DownloadStatus.SUCCESS if paper.pdf_url else DownloadStatus.NOT_FOUND,
            pdf_path=paper.pdf_path,
            download_time_seconds=elapsed,
            metadata=metadata,
        )

    async def download_by_url(
        self,
        url: str,
        *,
        destination: str | Path | None = None,
        timeout: int | None = None,
    ) -> DownloadResult:
        """Download a paper from a direct URL.

        Args:
            url: Direct URL to the paper PDF or landing page.
            destination: Custom download directory.
            timeout: Download timeout in seconds.

        Returns:
            DownloadResult with PDF path.
        """
        start_time = time.monotonic()
        logger.info("Starting download from URL: {}", url)

        # Try to extract metadata from the URL
        paper = Paper(
            title="",
            url=url,
            pdf_url=url if url.lower().endswith(".pdf") else None,
            provider=PaperSource.UNKNOWN,
        )

        # Try to find metadata from URL using available providers
        for provider in self._registry.get_all():
            try:
                if "arxiv.org" in url:
                    pdf_url = await provider.get_pdf_url(paper)
                    if pdf_url:
                        paper.pdf_url = pdf_url
                        paper.provider = PaperSource.ARXIV
                        break
                elif "doi.org" in url or paper.doi:
                    doi = paper.doi or url.split("doi.org/")[-1]
                    paper = await provider.get_metadata(doi)
                    break
            except (ProviderError, ProviderNotFoundError):
                continue

        return DownloadResult(
            paper=paper,
            status=DownloadStatus.SUCCESS if paper.pdf_url else DownloadStatus.NOT_FOUND,
            download_time_seconds=time.monotonic() - start_time,
        )
