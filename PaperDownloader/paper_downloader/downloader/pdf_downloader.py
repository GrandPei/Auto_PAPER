"""Real PDF download implementation with streaming, retry, and SHA256 verification."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from paper_downloader.config import get_settings
from paper_downloader.utils.hashing import compute_sha256

if TYPE_CHECKING:
    from paper_downloader.models import Paper
    from paper_downloader.storage.cache import CacheManager
    from paper_downloader.storage.file_store import FileStore


class PDFDownloader:
    """Handles actual PDF file downloading.

    Features:
        - httpx streaming download
        - Progress bar via tqdm
        - Retry with exponential backoff
        - Timeout handling
        - Resume support
        - SHA256 verification
        - Automatic cleanup of partial files on failure
        - SQLite cache integration
        - Metadata persistence

    Input: Paper object with pdf_url
    Output: Locally saved PDF file
    """

    def __init__(
        self,
        file_store: FileStore,
        cache_manager: CacheManager,
    ) -> None:
        """Initialize the PDF downloader.

        Args:
            file_store: FileStore for path generation and SHA256.
            cache_manager: CacheManager for download records.
        """
        self._file_store: FileStore = file_store
        self._cache: CacheManager = cache_manager
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an httpx client for downloads.

        Returns:
            Configured httpx.AsyncClient with long timeout.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.download_timeout),
                follow_redirects=True,
                headers={
                    "User-Agent": "PaperDownloader/0.1",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _should_retry(exception: BaseException) -> bool:
        """Retry on network errors and server errors, not 4xx."""
        if isinstance(exception, httpx.HTTPStatusError):
            return 500 <= exception.response.status_code < 600
        return isinstance(exception, httpx.RequestError | httpx.TimeoutException)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=_should_retry,
        reraise=True,
    )
    async def _stream_download(
        self,
        url: str,
        dest_path: Path,
        resume: bool = False,
    ) -> str:
        """Download a file with streaming and optional resume support.

        Args:
            url: URL to download from.
            dest_path: Destination file path.
            resume: If True, attempt to resume partial download.

        Returns:
            SHA256 hash of the downloaded file.

        Raises:
            httpx.HTTPStatusError: On HTTP errors.
            httpx.RequestError: On network errors.
        """
        client = await self._get_client()

        # Partial file for resume
        downloaded_bytes: int = 0
        if resume and dest_path.exists():
            downloaded_bytes = dest_path.stat().st_size
            logger.info("Resuming download from byte {}", downloaded_bytes)

        headers: dict[str, str] = {}
        if downloaded_bytes > 0:
            headers["Range"] = f"bytes={downloaded_bytes}-"

        mode = "ab" if downloaded_bytes > 0 else "wb"

        # Determine file size for progress bar
        try:
            head_response = await client.head(url)
            total_size: int | None = (
                int(head_response.headers.get("content-length", 0))
                if head_response.headers.get("content-length")
                else None
            )
        except Exception:
            total_size = None

        with tqdm(
            total=total_size,
            initial=downloaded_bytes,
            unit="B",
            unit_scale=True,
            desc=dest_path.name,
            disable=not dest_path.name,
        ) as progress:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()

                with open(dest_path, mode) as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        progress.update(len(chunk))

        # Compute SHA256
        sha256 = compute_sha256(dest_path)
        logger.info("Download complete: {} (SHA256: {})", dest_path.name, sha256[:16])
        return sha256

    async def download(
        self,
        paper: Paper,
        *,
        destination: Path | None = None,
        show_progress: bool = True,
    ) -> Paper:
        """Download a paper's PDF and update the Paper object.

        Args:
            paper: Paper object with pdf_url set.
            destination: Custom destination path. Auto-generated if None.
            show_progress: Whether to show tqdm progress bar.

        Returns:
            Updated Paper with pdf_path and sha256 populated.

        Raises:
            ValueError: If paper has no pdf_url.
            httpx.HTTPStatusError: If download fails after retries.
        """
        if not paper.pdf_url:
            raise ValueError(f"Paper '{paper.title}' has no pdf_url set")

        # Determine destination path
        dest_path = destination or self._file_store.get_paper_path(paper)

        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Downloading PDF: '{}' -> {}",
            paper.title,
            dest_path,
        )

        # Check cache by DOI or title
        if paper.doi:
            cached = await self._cache.find_by_doi(paper.doi)
            if cached and cached.get("pdf_path"):
                cached_path = Path(cached["pdf_path"])
                if cached_path.exists():
                    logger.info("Found in cache by DOI: {}", cached_path)
                    paper.pdf_path = cached_path
                    paper.sha256 = cached.get("sha256")
                    return paper

        if paper.title:
            cached = await self._cache.find_by_title(paper.title)
            if cached and cached.get("pdf_path"):
                cached_path = Path(cached["pdf_path"])
                if cached_path.exists():
                    logger.info("Found in cache by title: {}", cached_path)
                    paper.pdf_path = cached_path
                    paper.sha256 = cached.get("sha256")
                    return paper

        try:
            # Download the PDF
            sha256 = await self._stream_download(
                paper.pdf_url,
                dest_path,
                resume=False,
            )

            # Verify integrity
            if paper.sha256 and paper.sha256 != sha256:
                logger.warning(
                    "SHA256 mismatch! Expected={}, Actual={}",
                    paper.sha256,
                    sha256,
                )

            paper.pdf_path = dest_path
            paper.sha256 = sha256

            # Write to SQLite cache
            await self._cache.add_record(
                title=paper.title,
                doi=paper.doi,
                provider=paper.provider.value,
                pdf_path=dest_path,
                sha256=sha256,
                status="success",
            )

            # Save metadata
            await self._file_store.save_metadata_json(paper)
            await self._file_store.save_metadata_bibtex(paper)

            logger.info("PDF saved: {}", dest_path)
            return paper

        except Exception:
            # Clean up residual file on failure
            if dest_path.exists():
                try:
                    dest_path.unlink()
                    logger.info("Cleaned up residual file: {}", dest_path)
                except OSError:
                    pass
            raise

    async def download_with_retry(
        self,
        paper: Paper,
        *,
        destination: Path | None = None,
    ) -> Paper:
        """Download with additional retry logic wrapping the retry decorator.

        Args:
            paper: Paper to download.
            destination: Custom destination path.

        Returns:
            Updated Paper on success.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._settings.download_max_retries + 2):
            try:
                return await self.download(paper, destination=destination)
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
                last_error = e
                logger.warning(
                    "Download attempt {}/{} failed: {}",
                    attempt,
                    self._settings.download_max_retries,
                    e,
                )
                if attempt <= self._settings.download_max_retries:
                    wait_time = 2 ** (attempt - 1)
                    time.sleep(wait_time)

        raise RuntimeError(
            f"Download failed after {self._settings.download_max_retries + 1} attempts: {last_error}"
        )
