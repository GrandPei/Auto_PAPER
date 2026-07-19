"""
Smoke test for the main app download service.

This is the integration point your teammate can call after their retrieval
module has produced final paper titles.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.download import PaperDownloader


async def main() -> None:
    downloader = PaperDownloader(
        save_dir=str(PROJECT_ROOT / "download_diagnostics" / "app_service_pdfs"),
        engine="academic_oa",
    )

    titles = [
        "PaSa: An LLM Agent for Comprehensive Academic Paper Search",
        "SPAR: Scholar Paper Retrieval with LLM-based Agents for Enhanced Academic Search",
    ]
    result = await downloader.download_batch(titles, max_concurrent=1)

    print(f"total={result.total}, success={result.success_count}, failure={result.failure_count}")
    for item in result.results:
        print()
        print(f"title:  {item.paper_title}")
        print(f"ok:     {item.success}")
        print(f"status: {item.status}")
        print(f"source: {item.source_channel}")
        print(f"pages:  {item.page_count}")
        print(f"size:   {item.file_size}")
        print(f"path:   {item.file_path}")
        if item.error:
            print(f"error:  {item.error}")


if __name__ == "__main__":
    asyncio.run(main())
