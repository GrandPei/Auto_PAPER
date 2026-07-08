"""SQLite-based cache for paper download tracking.

Prevents duplicate downloads and maintains a record of all
downloaded papers with their metadata.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import aiosqlite
from loguru import logger


class CacheManager:
    """SQLite cache manager for paper download records.

    Stores and queries paper download history to avoid
    duplicate downloads and enable cache lookups.

    Database schema:
        papers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            doi TEXT,
            provider TEXT,
            pdf_path TEXT,
            sha256 TEXT,
            download_time TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """

    _SCHEMA: str = """
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            doi TEXT,
            provider TEXT,
            pdf_path TEXT,
            sha256 TEXT,
            download_time TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
        CREATE INDEX IF NOT EXISTS idx_papers_sha256 ON papers(sha256);
        CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the cache manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path: Path = Path(db_path)
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Create database tables and indexes if they don't exist."""
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.executescript(self._SCHEMA)
            await db.commit()
        logger.info("Cache database initialized at {}", self._db_path)

    async def add_record(
        self,
        title: str,
        doi: str | None,
        provider: str,
        pdf_path: Path | None,
        sha256: str | None,
        status: str,
    ) -> int:
        """Insert a new paper download record.

        Args:
            title: Paper title.
            doi: DOI if available.
            provider: Source provider name.
            pdf_path: Local path to the downloaded PDF.
            sha256: SHA256 hash of the PDF.
            status: Download status string.

        Returns:
            The ID of the inserted record.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            cursor = await db.execute(
                """INSERT INTO papers (title, doi, provider, pdf_path, sha256, download_time, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    title,
                    doi,
                    provider,
                    str(pdf_path) if pdf_path else None,
                    sha256,
                    datetime.now().isoformat(),
                    status,
                ),
            )
            await db.commit()
            row_id = cursor.lastrowid or 0
            logger.debug("Added cache record id={} for '{}'", row_id, title)
            return row_id

    async def find_by_doi(self, doi: str) -> dict | None:
        """Find a cached paper by DOI.

        Args:
            doi: DOI to search for.

        Returns:
            Record as a dict, or None if not found.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM papers WHERE doi = ? AND status = 'success'",
                (doi,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def find_by_sha256(self, sha256: str) -> dict | None:
        """Find a cached paper by SHA256 hash.

        Args:
            sha256: SHA256 hash to search for.

        Returns:
            Record as a dict, or None if not found.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM papers WHERE sha256 = ? AND status = 'success'",
                (sha256,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def find_by_title(self, title: str) -> dict | None:
        """Find a cached paper by exact title.

        Args:
            title: Exact paper title.

        Returns:
            Record as a dict, or None if not found.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM papers WHERE title = ? AND status = 'success'",
                (title,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def exists(self, title: str = "", doi: str = "", sha256: str = "") -> bool:
        """Check if a paper is already in the cache.

        Checks by SHA256 first (most reliable), then DOI, then title.

        Args:
            title: Paper title.
            doi: DOI.
            sha256: SHA256 hash.

        Returns:
            True if the paper is found in cache with status 'success'.
        """
        if sha256:
            record = await self.find_by_sha256(sha256)
            if record:
                return True
        if doi:
            record = await self.find_by_doi(doi)
            if record:
                return True
        if title:
            record = await self.find_by_title(title)
            if record:
                return True
        return False

    async def update_record(
        self,
        record_id: int,
        **kwargs: str | None,
    ) -> None:
        """Update fields of an existing cache record.

        Args:
            record_id: ID of the record to update.
            **kwargs: Field names and new values.
        """
        if not kwargs:
            return

        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values())

        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.execute(
                f"UPDATE papers SET {set_clause} WHERE id = ?",
                (*values, record_id),
            )
            await db.commit()
            logger.debug("Updated cache record id={}: {}", record_id, kwargs)

    async def delete_record(self, record_id: int) -> None:
        """Delete a cache record by ID.

        Args:
            record_id: ID of the record to delete.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.execute("DELETE FROM papers WHERE id = ?", (record_id,))
            await db.commit()
            logger.debug("Deleted cache record id={}", record_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get all cached records with pagination.

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.

        Returns:
            List of record dicts.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM papers ORDER BY download_time DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def count(self) -> int:
        """Get the total number of cached records.

        Returns:
            Total record count.
        """
        async with aiosqlite.connect(str(self._db_path)) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM papers")
            row = await cursor.fetchone()
            return (row[0] if row else 0) if row else 0
