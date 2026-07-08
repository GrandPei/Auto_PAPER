# Changelog

All notable changes to PaperDownloader will be documented in this file.

## [0.1.0] - 2026-07-08

### Added
- **Project Foundation**: Python 3.12+ project with uv/pip management, SOLID architecture
- **Data Models**: Pydantic v2 models — Paper, Author, Metadata, DownloadResult, DownloadStatus, PaperSource
- **Provider Architecture**: Abstract BaseProvider with abstract factory + strategy pattern, ProviderRegistry
- **OpenAlex Provider**: REST API integration with retry, error handling, async httpx
- **Semantic Scholar Provider**: Graph API integration for paper search and metadata
- **arXiv Provider**: Official arXiv API with Atom XML parsing, title and author search
- **CrossRef Provider**: DOI lookup and title-to-DOI search via CrossRef REST API
- **Unpaywall Provider**: Open Access PDF discovery by DOI
- **Title Matcher**: Multi-strategy matching — exact, case-insensitive, normalized, Levenshtein, RapidFuzz, DOI
- **Download Manager**: Provider cascade orchestration with automatic failover
- **PDF Downloader**: Streaming download with progress bar, retry, SHA256 verification, resume support
- **File Store**: Filename sanitization, SHA256 computation, duplicate detection, metadata export (JSON, BibTeX, RIS)
- **SQLite Cache**: Persistent download history with CRUD operations, avoiding duplicate downloads
- **Public API**: `download_paper()`, `download_paper_pdf()`, `download_by_doi()`, `download_by_url()`, `download_many()`
- **Configuration**: Pydantic Settings v2 with .env support, environment variable overrides
- **Logging**: Loguru-based structured logging with file rotation
- **Testing**: 99 pytest tests across all modules with pytest-httpx, pytest-asyncio
- **Code Quality**: Ruff linting, Black formatting, mypy strict type checking
- **Examples**: `basic_usage.py` demonstrating all API functions
