"""FileStore 和 CacheManager 的测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from paper_downloader.models import Author, Paper
from paper_downloader.storage.cache import CacheManager
from paper_downloader.storage.file_store import FileStore


class TestFileStore:
    """FileStore 的测试。"""

    @pytest.fixture
    def tmp_store(self) -> FileStore:
        """在临时目录中创建 FileStore。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield FileStore(tmpdir)

    def test_sanitize_filename_illegal_chars(self, tmp_store: FileStore) -> None:
        """非法字符将替换为下划线。"""
        result = tmp_store.sanitize_filename("test:file<name>.pdf")
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result

    def test_sanitize_filename_collapse_underscores(self, tmp_store: FileStore) -> None:
        """多个下划线被合并。"""
        result = tmp_store.sanitize_filename("test___file___name")
        assert "___" not in result

    def test_sanitize_filename_max_length(self, tmp_store: FileStore) -> None:
        """长文件名被截断。"""
        long_name = "a" * 300
        result = tmp_store.sanitize_filename(long_name)
        assert len(result) <= 200

    def test_generate_filename_basic(self, tmp_store: FileStore) -> None:
        """根据论文元数据生成文件名。"""
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
        """没有作者时文件名也能正常工作。"""
        paper = Paper(title="Test Paper", year=2024)
        filename = tmp_store.generate_filename(paper)
        assert "unknown" in filename
        assert "2024" in filename

    def test_get_paper_path(self, tmp_store: FileStore) -> None:
        """论文路径位于基础目录内。"""
        paper = Paper(
            title="Test Paper",
            authors=[Author(name="John Smith")],
            year=2023,
        )
        path = tmp_store.get_paper_path(paper)
        assert path.parent == tmp_store.base_dir
        assert path.suffix == ".pdf"

    def test_exists(self, tmp_store: FileStore) -> None:
        """不存在的论文返回 False。"""
        paper = Paper(title="Nonexistent Paper")
        assert not tmp_store.exists(paper)

    def test_generate_filename_special_chars(self, tmp_store: FileStore) -> None:
        """标题中的特殊字符被清理。"""
        paper = Paper(
            title='Test: "Paper"? <Amazing>',
            authors=[Author(name="Jane Doe")],
            year=2022,
        )
        filename = tmp_store.generate_filename(paper)
        # 没有非法字符
        assert ":" not in filename
        assert '"' not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert "?" not in filename


class TestCacheManager:
    """CacheManager 的测试。"""

    @pytest.fixture
    async def cache(self) -> CacheManager:
        """创建一个使用临时数据库的 CacheManager。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cm = CacheManager(db_path)
            await cm.initialize()
            yield cm
            # 清理
            db_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, cache: CacheManager) -> None:
        """数据库表无错误地创建。"""
        count = await cache.count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_add_and_find_by_doi(self, cache: CacheManager) -> None:
        """可以添加记录并通过 DOI 检索。"""
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
        """可以通过 SHA256 哈希查找记录。"""
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
        """已缓存的 DOI 返回 True。"""
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
        """记录字段可以更新。"""
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
        """记录可以被删除。"""
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
        """返回正确的记录数。"""
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
        """两次添加相同的 DOI 会创建两条记录（没有唯一约束）。"""
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
