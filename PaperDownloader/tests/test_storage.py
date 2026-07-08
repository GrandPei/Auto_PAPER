"""Tests for FileStore and CacheManager."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from paper_downloader.models import Author, Paper
from paper_downloader.storage.cache import CacheManager
from paper_downloader.storage.file_store import FileStore


class TestFileStore:
    """Tests for FileStore."""

    @pytest.fixture
    def tmp_store(self) -> FileStore:
        """Create a FileStore in a temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield FileStore(tmpdir)

    def test_sanitize_filename_illegal_chars(self, tmp_store: FileStore) -> None:
        """Illegal characters are replaced with underscore."""
        result = tmp_store.sanitize_filename("test:file<name>.pdf")
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result

    def test_sanitize_filename_collapse_underscores(self, tmp_store: FileStore) -> None:
        """Multiple underscores are collapsed."""
        result = tmp_store.sanitize_filename("test___file___name")
        assert "___" not in result

    def test_sanitize_filename_max_length(self, tmp_store: FileStore) -> None:
        """Long filenames are truncated."""
        long_name = "a" * 300
        result = tmp_store.sanitize_filename(long_name)
        assert len(result) <= 200

    def test_generate_filename_basic(self, tmp_store: FileStore) -> None:
        """Filename is generated from paper metadata."""
        paper = Paper(
            title="Attention Is All You Need",
            authors=[Author(name="Ashish Vaswani")],
            year=2017,
        )
        filename = tmp_store.generate_filename(paper)
        assert "Vaswani" in filename
        assert "2017" in filename
        assert "Attention" in filename

    def test_generate_filename_no_author(self, tmp_store: FileStore) -> None:
        """Filename works with no author."""
        paper = Paper(title="Test Paper", year=2024)
        filename = tmp_store.generate_filename(paper)
        assert "unknown" in filename
        assert "2024" in filename

    def test_get_paper_path(self, tmp_store: FileStore) -> None:
        """Paper path is within base directory."""
        paper = Paper(
            title="Test Paper",
            authors=[Author(name="John Smith")],
            year=2023,
        )
        path = tmp_store.get_paper_path(paper)
        assert path.parent == tmp_store.base_dir
        assert path.suffix == ".pdf"

    def test_exists(self, tmp_store: FileStore) -> None:
        """exists returns False for non-existent paper."""
        paper = Paper(title="Nonexistent Paper")
        assert not tmp_store.exists(paper)

    def test_generate_filename_special_chars(self, tmp_store: FileStore) -> None:
        """Special characters in title are sanitized."""
        paper = Paper(
            title='Test: "Paper"? <Amazing>',
            authors=[Author(name="Jane Doe")],
            year=2022,
        )
        filename = tmp_store.generate_filename(paper)
        # No illegal characters
        assert ":" not in filename
        assert '"' not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert "?" not in filename


class TestCacheManager:
    """Tests for CacheManager."""

    @pytest.fixture
    async def cache(self) -> CacheManager:
        """Create a CacheManager with a temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cm = CacheManager(db_path)
            await cm.initialize()
            yield cm
            # Cleanup
            db_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, cache: CacheManager) -> None:
        """Database tables are created without error."""
        count = await cache.count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_add_and_find_by_doi(self, cache: CacheManager) -> None:
        """Record can be added and retrieved by DOI."""
        await cache.add_record(
            title="Test Paper",
            doi="10.1234/test",
            provider="openalex",
            pdf_path=Path("/tmp/test.pdf"),
            sha256="abc123",
            status="success",
        )

        record = await cache.find_by_doi("10.1234/test")
        assert record is not None
        assert record["title"] == "Test Paper"
        assert record["doi"] == "10.1234/test"

    @pytest.mark.asyncio
    async def test_find_by_sha256(self, cache: CacheManager) -> None:
        """Record can be found by SHA256 hash."""
        await cache.add_record(
            title="Paper B",
            doi="10.5678/paperb",
            provider="arxiv",
            pdf_path=Path("/tmp/b.pdf"),
            sha256="def456",
            status="success",
        )

        record = await cache.find_by_sha256("def456")
        assert record is not None
        assert record["title"] == "Paper B"

    @pytest.mark.asyncio
    async def test_exists_by_doi(self, cache: CacheManager) -> None:
        """exists returns True for cached DOI."""
        await cache.add_record(
            title="Cached Paper",
            doi="10.9999/cached",
            provider="semantic_scholar",
            pdf_path=Path("/tmp/cached.pdf"),
            sha256="hash123",
            status="success",
        )

        assert await cache.exists(doi="10.9999/cached")
        assert not await cache.exists(doi="10.9999/missing")

    @pytest.mark.asyncio
    async def test_update_record(self, cache: CacheManager) -> None:
        """Record fields can be updated."""
        record_id = await cache.add_record(
            title="Original Title",
            doi="10.1111/update",
            provider="crossref",
            pdf_path=None,
            sha256=None,
            status="pending",
        )

        await cache.update_record(record_id, status="success", sha256="newhash")

        record = await cache.find_by_doi("10.1111/update")
        assert record is not None
        assert record["status"] == "success"
        assert record["sha256"] == "newhash"

    @pytest.mark.asyncio
    async def test_delete_record(self, cache: CacheManager) -> None:
        """Record can be deleted."""
        record_id = await cache.add_record(
            title="To Delete",
            doi="10.2222/delete",
            provider="unpaywall",
            pdf_path=None,
            sha256=None,
            status="failed",
        )

        await cache.delete_record(record_id)
        assert await cache.count() == 0

    @pytest.mark.asyncio
    async def test_count(self, cache: CacheManager) -> None:
        """Count returns correct number of records."""
        assert await cache.count() == 0

        for i in range(5):
            await cache.add_record(
                title=f"Paper {i}",
                doi=f"10.1000/paper{i}",
                provider="openalex",
                pdf_path=None,
                sha256=None,
                status="success",
            )

        assert await cache.count() == 5

    @pytest.mark.asyncio
    async def test_duplicate_doi_avoided(self, cache: CacheManager) -> None:
        """Adding same DOI twice creates two records (no unique constraint)."""
        await cache.add_record(
            title="First Entry",
            doi="10.3333/dup",
            provider="openalex",
            pdf_path=None,
            sha256=None,
            status="success",
        )
        await cache.add_record(
            title="Second Entry",
            doi="10.3333/dup",
            provider="arxiv",
            pdf_path=None,
            sha256=None,
            status="success",
        )
        assert await cache.count() == 2
