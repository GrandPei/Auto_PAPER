"""Core data models for PaperDownloader using Pydantic v2."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path  # noqa: TC001 — needed at runtime for Pydantic model_rebuild()

from pydantic import BaseModel, ConfigDict, Field


class PaperSource(str, Enum):
    """Enumeration of supported paper metadata sources (providers)."""

    OPENALEX = "openalex"
    """OpenAlex - Open access bibliometric database."""

    SEMANTIC_SCHOLAR = "semantic_scholar"
    """Semantic Scholar - AI-powered academic search engine."""

    ARXIV = "arxiv"
    """arXiv - Open-access preprint repository."""

    CROSSREF = "crossref"
    """CrossRef - DOI registration agency and metadata hub."""

    UNPAYWALL = "unpaywall"
    """Unpaywall - Open Access PDF discovery service."""

    MANUAL = "manual"
    """User-provided metadata."""

    UNKNOWN = "unknown"
    """Unknown or unspecified source."""


class DownloadStatus(str, Enum):
    """Enumeration of possible download outcomes."""

    SUCCESS = "success"
    """Download completed successfully with SHA256 verification."""

    CACHED = "cached"
    """Paper already exists in local cache, no download needed."""

    FAILED = "failed"
    """Download failed after all retry attempts."""

    NOT_FOUND = "not_found"
    """Paper metadata found but PDF is not available."""

    TIMEOUT = "timeout"
    """Download exceeded the configured timeout."""

    PARTIAL = "partial"
    """Download started but did not complete (resume possible)."""

    PENDING = "pending"
    """Download has not started yet."""


class Author(BaseModel):
    """Represents a single paper author.

    Attributes:
        name: Full name of the author (e.g., "John Smith").
        orcid: ORCID identifier if available.
        affiliation: Institutional affiliation at time of publication.
        email: Contact email if publicly available.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="Full name of the author")
    orcid: str | None = Field(
        default=None, description="ORCID identifier (e.g., 0000-0002-1825-0097)"
    )
    affiliation: str | None = Field(
        default=None, description="Institutional affiliation at time of publication"
    )
    email: str | None = Field(default=None, description="Contact email if publicly available")


class Paper(BaseModel):
    """Represents an academic paper with all its metadata.

    This is the central data model of the system. All providers MUST
    return Paper instances from their search and metadata methods.

    Attributes:
        title: The paper title.
        authors: List of Author objects.
        abstract: Abstract text.
        year: Publication year.
        venue: Journal, conference, or repository name.
        doi: Digital Object Identifier (e.g., "10.1038/nature14539").
        url: URL to the paper's landing page.
        pdf_url: Direct URL to the PDF file, if available.
        pdf_path: Local filesystem path to the downloaded PDF.
        provider: Source provider that supplied this metadata.
        citation_count: Number of citations, if known.
        open_access: Whether the paper is open access.
        license: License information (e.g., "CC-BY", "CC BY-NC-SA 4.0").
        sha256: SHA-256 hash of the downloaded PDF file.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    title: str = Field(..., min_length=1, description="The paper title")
    authors: list[Author] = Field(default_factory=list, description="List of paper authors")
    abstract: str = Field(default="", description="Abstract text of the paper")
    year: int | None = Field(default=None, ge=1500, le=2100, description="Publication year")
    venue: str = Field(default="", description="Journal, conference, or repository name")
    doi: str | None = Field(default=None, description="Digital Object Identifier (DOI)")
    url: str = Field(default="", description="URL to the paper's landing page")
    pdf_url: str | None = Field(default=None, description="Direct URL to the PDF file")
    pdf_path: Path | None = Field(
        default=None, description="Local filesystem path to the downloaded PDF"
    )
    provider: PaperSource = Field(
        default=PaperSource.UNKNOWN, description="Source provider of this metadata"
    )
    citation_count: int = Field(default=0, ge=0, description="Number of citations received")
    open_access: bool = Field(default=False, description="Whether the paper is open access")
    license: str | None = Field(
        default=None, description="License information (e.g., CC-BY, CC BY-NC-SA 4.0)"
    )
    sha256: str | None = Field(default=None, description="SHA-256 hash of the downloaded PDF file")


class Metadata(BaseModel):
    """Supplementary metadata about the download process and paper source.

    Attributes:
        source: The provider that supplied the metadata.
        retrieved_at: Timestamp when metadata was fetched.
        raw_response: Raw API response data for debugging.
        match_score: Confidence score from the title matcher (0.0 to 1.0).
        match_method: Which matching algorithm was used.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: PaperSource = Field(..., description="The provider that supplied the metadata")
    retrieved_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when metadata was retrieved",
    )
    raw_response: dict[str, object] = Field(
        default_factory=dict, description="Raw API response data for debugging"
    )
    match_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score from the title matcher (0.0 to 1.0)",
    )
    match_method: str | None = Field(default=None, description="Which matching algorithm was used")


class DownloadResult(BaseModel):
    """Result of a paper download operation.

    Encapsulates the outcome of a download attempt including the paper
    metadata, status, and any error information.

    Attributes:
        paper: The Paper object with metadata (may be partial on failure).
        status: Outcome status of the download.
        pdf_path: Local path to the downloaded PDF (None if download failed).
        error_message: Human-readable error description if status is not SUCCESS/CACHED.
        retry_count: Number of retry attempts made.
        download_time_seconds: Total time spent on the download in seconds.
        metadata: Supplementary metadata about the download process.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    paper: Paper = Field(..., description="The Paper object with metadata")
    status: DownloadStatus = Field(..., description="Outcome status of the download")
    pdf_path: Path | None = Field(default=None, description="Local path to the downloaded PDF")
    error_message: str | None = Field(
        default=None, description="Error description if status is not SUCCESS/CACHED"
    )
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts made")
    download_time_seconds: float = Field(
        default=0.0, ge=0.0, description="Total download time in seconds"
    )
    metadata: Metadata | None = Field(
        default=None, description="Supplementary download process metadata"
    )


# Rebuild models to resolve forward references (required when using
# `from __future__ import annotations` with Pydantic v2).
Paper.model_rebuild()
Metadata.model_rebuild()
DownloadResult.model_rebuild()
