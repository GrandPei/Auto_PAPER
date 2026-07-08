"""PaperDownloader - Enterprise-grade academic paper downloader."""

from paper_downloader.api import (
    download_by_doi,
    download_by_url,
    download_many,
    download_paper,
    download_paper_pdf,
    init,
)
from paper_downloader.models import (
    DownloadResult,
    DownloadStatus,
    Paper,
    PaperSource,
)

__version__ = "0.1.0"
__all__ = [
    "download_paper",
    "download_paper_pdf",
    "download_by_doi",
    "download_by_url",
    "download_many",
    "init",
    "Paper",
    "DownloadResult",
    "DownloadStatus",
    "PaperSource",
]
