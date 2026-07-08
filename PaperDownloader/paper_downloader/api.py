"""Public API for PaperDownloader.

This module exposes the only functions end users should call.
All complex provider logic, caching, and download orchestration
is hidden behind these simple async functions.

Quick Start:
    >>> from paper_downloader import download_paper, download_by_doi
    >>>
    >>> # Download by title
    >>> result = await download_paper("Attention Is All You Need")
    >>> print(result.pdf_path)
    >>>
    >>> # Download by DOI
    >>> result = await download_by_doi("10.1038/nature14539")
    >>>
    >>> # Download many
    >>> results = await download_many([
    ...     "Attention Is All You Need",
    ...     "BERT: Pre-training of Deep Bidirectional Transformers",
    ... ])
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from paper_downloader.config import get_settings
from paper_downloader.downloader.manager import DownloadManager
from paper_downloader.downloader.pdf_downloader import PDFDownloader
from paper_downloader.matcher import TitleMatcher
from paper_downloader.models import DownloadResult, Paper
from paper_downloader.providers.arxiv import ArxivProvider
from paper_downloader.providers.base import BaseProvider, ProviderRegistry
from paper_downloader.providers.crossref import CrossRefProvider
from paper_downloader.providers.openalex import OpenAlexProvider
from paper_downloader.providers.semantic_scholar import SemanticScholarProvider
from paper_downloader.providers.unpaywall import UnpaywallProvider
from paper_downloader.storage.cache import CacheManager
from paper_downloader.storage.file_store import FileStore
from paper_downloader.utils.logging import setup_logging

if TYPE_CHECKING:
    from collections.abc import Sequence

# Global state (lazily initialized)
_settings = get_settings()
_registry: ProviderRegistry | None = None
_matcher: TitleMatcher | None = None
_manager: DownloadManager | None = None
_pdf_downloader: PDFDownloader | None = None
_file_store: FileStore | None = None
_cache_manager: CacheManager | None = None


def _get_registry() -> ProviderRegistry:
    """Get or create the provider registry with all built-in providers.

    Returns:
        Configured ProviderRegistry with all providers registered.
    """
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _registry.register(OpenAlexProvider(email=_settings.openalex_email, priority=10))
        _registry.register(
            SemanticScholarProvider(api_key=_settings.semantic_scholar_api_key, priority=20)
        )
        _registry.register(ArxivProvider(priority=30))
        _registry.register(CrossRefProvider(priority=40))
        _registry.register(UnpaywallProvider(email=_settings.unpaywall_email, priority=50))
        logger.info("Provider registry initialized with {} providers", _registry.count)
    return _registry


def _get_manager() -> DownloadManager:
    """Get or create the download manager.

    Returns:
        Configured DownloadManager.
    """
    global _manager, _matcher
    if _manager is None:
        _matcher = TitleMatcher()
        _manager = DownloadManager(registry=_get_registry(), matcher=_matcher)
        logger.info("Download manager initialized")
    return _manager


def _get_file_store() -> FileStore:
    """Get or create the file store.

    Returns:
        Configured FileStore.
    """
    global _file_store
    if _file_store is None:
        _file_store = FileStore(base_dir=_settings.download_dir)
    return _file_store


def _get_cache_manager() -> CacheManager:
    """Get or create the cache manager.

    Returns:
        Configured CacheManager.
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(db_path=_settings.cache_db)
    return _cache_manager


def _get_pdf_downloader() -> PDFDownloader:
    """Get or create the PDF downloader.

    Returns:
        Configured PDFDownloader.
    """
    global _pdf_downloader
    if _pdf_downloader is None:
        _pdf_downloader = PDFDownloader(
            file_store=_get_file_store(),
            cache_manager=_get_cache_manager(),
        )
    return _pdf_downloader


async def download_paper_pdf(title: str) -> DownloadResult:
    """Download a paper's PDF by title.

    This is the primary function for downloading papers. It searches
    across all configured providers, finds the best match, obtains
    the PDF URL, downloads the file, verifies SHA256, and saves metadata.

    Args:
        title: The paper title to search for and download.

    Returns:
        DownloadResult with:
            - paper: Paper object with full metadata
            - pdf_path: Path to the downloaded PDF (if successful)
            - status: SUCCESS, CACHED, FAILED, or NOT_FOUND
            - error_message: Description if download failed

    Example:
        >>> result = await download_paper_pdf("Attention Is All You Need")
        >>> if result.status == DownloadStatus.SUCCESS:
        ...     print(f"Downloaded to: {result.pdf_path}")
    """
    await _get_cache_manager().initialize()

    manager = _get_manager()
    result = await manager.download(title)

    # If metadata found and we have a PDF URL, actually download the PDF
    if result.paper.pdf_url and result.status.value in ("success",):
        try:
            pdf_downloader = _get_pdf_downloader()
            paper = await pdf_downloader.download(result.paper)
            result.paper = paper
            result.pdf_path = paper.pdf_path
            result.status = result.status.__class__.SUCCESS
        except Exception as e:
            logger.error("PDF download failed: {}", e)
            result.error_message = f"Metadata found but PDF download failed: {e}"
            result.status = result.status.__class__.FAILED

    return result


async def download_paper(title: str) -> DownloadResult:
    """Download paper metadata only (no PDF download).

    Searches across providers for paper metadata without downloading
    the actual PDF file.

    Args:
        title: The paper title to search for.

    Returns:
        DownloadResult with paper metadata but no PDF file.

    Example:
        >>> result = await download_paper("BERT: Pre-training of Deep Bidirectional")
        >>> print(result.paper.abstract)
    """
    await _get_cache_manager().initialize()

    manager = _get_manager()
    return await manager.download(title)


async def download_by_doi(doi: str) -> DownloadResult:
    """Download a paper's PDF by its DOI.

    Uses the provider cascade to find metadata and PDF for the given DOI.
    Unpaywall is particularly effective for finding OA PDFs by DOI.

    Args:
        doi: Digital Object Identifier (e.g., "10.1038/nature14539").

    Returns:
        DownloadResult with paper metadata and PDF path.

    Example:
        >>> result = await download_by_doi("10.1038/nature14539")
        >>> print(result.pdf_path)
    """
    await _get_cache_manager().initialize()

    manager = _get_manager()
    result = await manager.download_by_doi(doi)

    # Try to download PDF if we have a URL
    if result.paper.pdf_url and result.status.value in ("success",):
        try:
            pdf_downloader = _get_pdf_downloader()
            paper = await pdf_downloader.download(result.paper)
            result.paper = paper
            result.pdf_path = paper.pdf_path
        except Exception as e:
            logger.error("PDF download failed: {}", e)
            result.error_message = f"PDF download failed: {e}"
            result.status = result.status.__class__.FAILED

    return result


async def download_by_url(url: str) -> DownloadResult:
    """Download a paper from a direct URL.

    Attempts to detect the source and download the PDF.

    Args:
        url: URL to the paper PDF or landing page.

    Returns:
        DownloadResult with PDF path if download was successful.

    Example:
        >>> result = await download_by_url("https://arxiv.org/pdf/1706.03762.pdf")
    """
    await _get_cache_manager().initialize()

    manager = _get_manager()
    result = await manager.download_by_url(url)

    if result.paper.pdf_url:
        try:
            pdf_downloader = _get_pdf_downloader()
            paper = await pdf_downloader.download(result.paper)
            result.paper = paper
            result.pdf_path = paper.pdf_path
        except Exception as e:
            logger.error("PDF download failed: {}", e)
            result.error_message = f"PDF download failed: {e}"
            result.status = result.status.__class__.FAILED

    return result


async def download_many(
    titles: Sequence[str],
    *,
    max_concurrent: int | None = None,
) -> list[DownloadResult]:
    """Download multiple papers concurrently.

    Uses asyncio.gather with a concurrency limit to download
    multiple papers at once without overwhelming APIs.

    Args:
        titles: List of paper titles to download.
        max_concurrent: Maximum concurrent downloads. Uses config default if None.

    Returns:
        List of DownloadResult objects in the same order as input titles.

    Example:
        >>> results = await download_many([
        ...     "Attention Is All You Need",
        ...     "BERT: Pre-training of Deep Bidirectional Transformers",
        ...     "GPT-3: Language Models are Few-Shot Learners",
        ... ])
        >>> for r in results:
        ...     print(f"{r.paper.title}: {r.status.value}")
    """
    settings = get_settings()
    max_workers = max_concurrent or settings.download_concurrent_limit

    # Initialize cache once
    await _get_cache_manager().initialize()

    semaphore = asyncio.Semaphore(max_workers)

    async def _download_with_limit(title: str) -> DownloadResult:
        async with semaphore:
            return await download_paper_pdf(title)

    logger.info(
        "Downloading {} papers with concurrency limit {}",
        len(titles),
        max_workers,
    )

    tasks = [_download_with_limit(title) for title in titles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions in results
    final_results: list[DownloadResult] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error("Download failed for '{}': {}", titles[i], result)
            final_results.append(
                DownloadResult(
                    paper=Paper(title=titles[i]),
                    status=DownloadResult.__annotations__["status"].__args__[0]("failed"),
                    error_message=str(result),
                )
            )
        else:
            final_results.append(result)

    logger.info(
        "Download complete: {}/{} succeeded",
        sum(1 for r in final_results if r.status.value in ("success", "cached")),
        len(final_results),
    )
    return final_results


def init(
    *,
    log_level: str = "INFO",
    register_provider: BaseProvider | None = None,
) -> None:
    """Initialize PaperDownloader with custom configuration.

    Call this once at application startup to configure logging
    and register custom providers.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        register_provider: Optional custom provider to register.

    Example:
        >>> from paper_downloader import init
        >>> init(log_level="DEBUG")
    """
    setup_logging(level=log_level)

    if register_provider:
        registry = _get_registry()
        registry.register(register_provider)
        logger.info("Registered custom provider: {}", register_provider.name)

    logger.info("PaperDownloader v0.1.0 initialized")
