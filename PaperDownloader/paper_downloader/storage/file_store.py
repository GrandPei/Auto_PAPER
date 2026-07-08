"""File system operations for paper storage.

Handles directory creation, filename sanitization, SHA256 computation,
duplicate detection, and metadata persistence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import aiofiles.os
from loguru import logger

from paper_downloader.utils.hashing import compute_sha256

if TYPE_CHECKING:
    from paper_downloader.models import Paper


class FileStore:
    """Manages file system operations for paper storage.

    Handles:
        - Automatic directory creation
        - Filename sanitization (illegal character replacement)
        - SHA256 computation
        - Duplicate file detection
        - Metadata saving in JSON, BibTeX, and RIS formats
    """

    # Characters illegal in Windows filenames
    _ILLEGAL_CHARS: str = r'[<>:"/\\|?*\x00-\x1f]'

    # Template for constructing filenames
    _FILENAME_TEMPLATE: str = "{first_author}_{year}_{title}"

    def __init__(self, base_dir: str | Path) -> None:
        """Initialize the file store.

        Args:
            base_dir: Root directory for storing papers.
        """
        self._base_dir: Path = Path(base_dir)
        self._ensure_dir(self._base_dir)

    @property
    def base_dir(self) -> Path:
        """Get the base storage directory."""
        return self._base_dir

    def _ensure_dir(self, directory: Path) -> None:
        """Create a directory if it doesn't exist.

        Args:
            directory: Directory path to create.
        """
        directory.mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, filename: str) -> str:
        """Replace illegal characters in a filename.

        Args:
            filename: Raw filename string.

        Returns:
            Sanitized filename safe for all major OSes.
        """
        # Replace illegal characters with underscore
        sanitized = re.sub(self._ILLEGAL_CHARS, "_", filename)
        # Collapse multiple underscores
        sanitized = re.sub(r"_+", "_", sanitized)
        # Remove leading/trailing underscores and dots
        sanitized = sanitized.strip("_ .")
        # Limit filename length (leave room for extension)
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        return sanitized

    def generate_filename(self, paper: Paper) -> str:
        """Generate a canonical filename for a paper.

        Format: {first_author}_{year}_{title}.pdf

        Args:
            paper: Paper to generate filename for.

        Returns:
            Sanitized filename string (without extension).
        """
        # Get first author's last name
        first_author: str = "unknown"
        if paper.authors:
            name = paper.authors[0].name
            # Last name is the last word
            parts = name.split()
            first_author = parts[-1] if parts else name

        year: str = str(paper.year) if paper.year else "nodate"

        # Truncate title to reasonable length
        title: str = paper.title[:80] if paper.title else "untitled"

        raw_filename = self._FILENAME_TEMPLATE.format(
            first_author=first_author,
            year=year,
            title=title,
        )
        return self.sanitize_filename(raw_filename)

    def get_paper_path(self, paper: Paper) -> Path:
        """Get the full path where a paper PDF should be stored.

        Args:
            paper: Paper object.

        Returns:
            Full Path for the PDF file.
        """
        filename = self.generate_filename(paper)
        return self._base_dir / f"{filename}.pdf"

    def get_metadata_path(self, paper: Paper) -> Path:
        """Get the path for a paper's metadata JSON file.

        Args:
            paper: Paper object.

        Returns:
            Full Path for the metadata file.
        """
        filename = self.generate_filename(paper)
        return self._base_dir / f"{filename}.json"

    def compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to the file.

        Returns:
            Hexadecimal SHA256 digest.
        """
        return compute_sha256(file_path)

    def exists(self, paper: Paper) -> bool:
        """Check if a paper PDF already exists on disk.

        Args:
            paper: Paper to check.

        Returns:
            True if the PDF file exists.
        """
        pdf_path = self.get_paper_path(paper)
        return pdf_path.exists()

    def find_by_sha256(self, sha256: str) -> Path | None:
        """Find a file by its SHA256 hash in the base directory.

        Note: This is a simple implementation. For production use,
        consider using a database index.

        Args:
            sha256: SHA256 hash to search for.

        Returns:
            Path to the matching file, or None if not found.
        """
        for pdf_file in self._base_dir.glob("*.pdf"):
            try:
                if self.compute_sha256(pdf_file) == sha256:
                    return pdf_file
            except OSError:
                continue
        return None

    async def save_metadata_json(self, paper: Paper) -> Path:
        """Save paper metadata as a JSON file.

        Args:
            paper: Paper whose metadata to save.

        Returns:
            Path to the saved metadata file.
        """
        metadata_path = self.get_metadata_path(paper)

        data = {
            "title": paper.title,
            "authors": [
                {
                    "name": a.name,
                    "orcid": a.orcid,
                    "affiliation": a.affiliation,
                }
                for a in paper.authors
            ],
            "abstract": paper.abstract,
            "year": paper.year,
            "venue": paper.venue,
            "doi": paper.doi,
            "url": paper.url,
            "pdf_url": paper.pdf_url,
            "pdf_path": str(paper.pdf_path) if paper.pdf_path else None,
            "provider": paper.provider.value,
            "citation_count": paper.citation_count,
            "open_access": paper.open_access,
            "license": paper.license,
            "sha256": paper.sha256,
            "downloaded_at": datetime.now().isoformat(),
        }

        async with aiofiles.open(metadata_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

        logger.info("Saved metadata to {}", metadata_path)
        return metadata_path

    async def save_metadata_bibtex(self, paper: Paper) -> Path:
        """Save paper metadata as a BibTeX file.

        Args:
            paper: Paper whose metadata to save.

        Returns:
            Path to the saved BibTeX file.
        """
        filename = self.generate_filename(paper)
        bib_path = self._base_dir / f"{filename}.bib"

        # Generate a citation key
        first_author = paper.authors[0].name.split()[-1] if paper.authors else "unknown"
        year = str(paper.year) if paper.year else "nodate"
        title_word = paper.title.split()[0].lower() if paper.title else "untitled"
        cite_key = f"{first_author}{year}{title_word}"

        bibtex = f"""@article{{{cite_key},
    title = {{{paper.title}}},
    author = {{{" and ".join(a.name for a in paper.authors)}}},
    year = {{{paper.year or ""}}},
    journal = {{{paper.venue}}},
    doi = {{{paper.doi or ""}}},
    url = {{{paper.url}}},
}}"""

        async with aiofiles.open(bib_path, "w", encoding="utf-8") as f:
            await f.write(bibtex)

        logger.info("Saved BibTeX to {}", bib_path)
        return bib_path

    async def save_metadata_ris(self, paper: Paper) -> Path:
        """Save paper metadata as a RIS file.

        Args:
            paper: Paper whose metadata to save.

        Returns:
            Path to the saved RIS file.
        """
        filename = self.generate_filename(paper)
        ris_path = self._base_dir / f"{filename}.ris"

        ris_lines: list[str] = [
            "TY  - JOUR",
            f"TI  - {paper.title}",
        ]

        for author in paper.authors:
            ris_lines.append(f"AU  - {author.name}")

        if paper.year:
            ris_lines.append(f"PY  - {paper.year}")
        if paper.venue:
            ris_lines.append(f"JO  - {paper.venue}")
        if paper.doi:
            ris_lines.append(f"DO  - {paper.doi}")
        if paper.url:
            ris_lines.append(f"UR  - {paper.url}")
        if paper.abstract:
            # Truncate abstract for RIS
            abstract = paper.abstract[:500]
            ris_lines.append(f"AB  - {abstract}")

        ris_lines.append("ER  - ")

        async with aiofiles.open(ris_path, "w", encoding="utf-8") as f:
            await f.write("\n".join(ris_lines))

        logger.info("Saved RIS to {}", ris_path)
        return ris_path
