
import asyncio
from paper_downloader import download_paper, download_paper_pdf, download_by_doi, download_many

async def main():
    # 仅获取论文元数据（不下载 PDF）
    """ result = await download_paper("Attention Is All You Need")
    print(result.paper.title, result.paper.year, result.paper.doi)"""

    # 下载论文 PDF
    result = await download_paper_pdf("Graph Attention Site Prediction (GrASP): Identifying Druggable Binding Sites Using Graph Neural Networks with Attention")
    print(result.pdf_path)

    # 通过 DOI 下载
    """result = await download_by_doi("10.1038/nature14539")"""

    # 批量并发下载
    """results = await download_many([
        "Attention Is All You Need",
        "BERT: Pre-training of Deep Bidirectional Transformers",
    ])"""

asyncio.run(main())