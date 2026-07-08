"""Basic usage examples for PaperDownloader.

Run with:
    python examples/basic_usage.py
"""

from __future__ import annotations

import asyncio

from paper_downloader import (
    DownloadResult,
    DownloadStatus,
    download_by_doi,
    download_many,
    download_paper,
    init,
)


async def example_download_by_title() -> None:
    """Download a paper by its title (metadata only, no PDF)."""
    print("\n=== Example: Download by Title ===")
    result = await download_paper("Attention Is All You Need")
    print_result(result)


async def example_download_by_doi() -> None:
    """Download a paper by its DOI."""
    print("\n=== Example: Download by DOI ===")
    result = await download_by_doi("10.1038/nature14539")
    print_result(result)


async def example_download_many() -> None:
    """Download multiple papers concurrently."""
    print("\n=== Example: Download Many ===")
    results = await download_many(
        [
            "Attention Is All You Need",
            "BERT: Pre-training of Deep Bidirectional Transformers",
        ]
    )
    for result in results:
        print_result(result)


def print_result(result: DownloadResult) -> None:
    """Print a download result."""
    print(f"  Title: {result.paper.title}")
    print(f"  Status: {result.status.value}")
    print(f"  Provider: {result.paper.provider.value}")
    if result.paper.doi:
        print(f"  DOI: {result.paper.doi}")
    if result.paper.year:
        print(f"  Year: {result.paper.year}")
    if result.paper.pdf_url:
        print(f"  PDF URL: {result.paper.pdf_url}")
    if result.pdf_path:
        print(f"  PDF Path: {result.pdf_path}")
    if result.error_message:
        print(f"  Error: {result.error_message}")
    print(f"  Time: {result.download_time_seconds:.2f}s")
    print()


async def main() -> None:
    """Run all examples."""
    init(log_level="INFO")

    await example_download_by_title()
    await example_download_by_doi()
    await example_download_many()


if __name__ == "__main__":
    asyncio.run(main())
