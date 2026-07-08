"""Cryptographic hashing utilities."""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_sha256(file_path: str | Path, chunk_size: int = 8192) -> str:
    """Compute the SHA-256 hash of a file.

    Reads the file in chunks to handle large files efficiently.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Size of chunks to read, in bytes.

    Returns:
        The hexadecimal SHA-256 digest string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    file_path = Path(file_path)
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)

    return sha256.hexdigest()


def compute_sha256_bytes(data: bytes) -> str:
    """Compute the SHA-256 hash of bytes data.

    Args:
        data: Bytes to hash.

    Returns:
        The hexadecimal SHA-256 digest string.
    """
    return hashlib.sha256(data).hexdigest()
