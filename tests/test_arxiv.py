"""arXiv 提供者的测试。"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from paper_downloader.models import Paper, PaperSource
from paper_downloader.providers.arxiv import ArxivProvider
from paper_downloader.providers.base import ProviderNotFoundError


def _mock_arxiv_xml(
    entries: list[dict] | None = None,
) -> str:
    """生成一个模拟的 arXiv Atom XML 响应。"""
    if entries is None:
        entries = [
            {
                "id": "http://arxiv.org/abs/1706.03762v7",
                "title": "Attention Is All You Need",
                "summary": "The dominant sequence transduction models...",
                "published": "2017-06-12",
                "updated": "2023-08-02",
                "authors": ["Ashish Vaswani", "Noam Shazeer"],
                "doi": "10.48550/arXiv.1706.03762",
                "category": "cs.CL",
                "journal_ref": "NeurIPS 2017",
                "comment": "15 pages, 5 figures",
            }
        ]

    entries_xml = []
    for e in entries:
        author_xml = "".join(f"<author><name>{a}</name></author>" for a in e.get("authors", []))
        doi_link = ""
        if e.get("doi"):
            doi_link = f'<link href="http://dx.doi.org/{e["doi"]}" rel="related" title="doi"/>'

        entries_xml.append(f"""<entry>
    <id>{e.get("id", "http://arxiv.org/abs/test")}</id>
    <title>{e.get("title", "Test Paper")}</title>
    <summary>{e.get("summary", "Test abstract.")}</summary>
    <published>{e.get("published", "2023-01-01")}</published>
    <updated>{e.get("updated", "2023-01-02")}</updated>
    {author_xml}
    {doi_link}
    <link href="{e.get("id", "").replace("/abs/", "/pdf/")}.pdf" title="pdf" rel="related"/>
    <arxiv:primary_category term="{e.get("category", "cs.AI")}"/>
    <arxiv:journal_ref>{e.get("journal_ref", "")}</arxiv:journal_ref>
    <arxiv:comment>{e.get("comment", "")}</arxiv:comment>
</entry>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
    <title>ArXiv Query Results</title>
    <totalResults>{len(entries)}</totalResults>
    {"".join(entries_xml)}
</feed>"""


XML_HEADERS = {"Content-Type": "application/atom+xml"}
ARXIV_API = "http://export.arxiv.org/api/query"


@pytest.fixture
def provider() -> ArxivProvider:
    """创建一个用于测试的 arXiv 提供者。"""
    return ArxivProvider()


@pytest.mark.asyncio
async def test_search_by_title(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """按标题搜索返回 Paper 对象。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?search_query=ti%3AAttention+Is+All+You+Need&start=0&max_results=5&sortBy=relevance",
        text=_mock_arxiv_xml(),
        headers=XML_HEADERS,
    )

    results = await provider.search("Attention Is All You Need")
    assert len(results) == 1
    assert results[0].title == "Attention Is All You Need"
    assert results[0].provider == PaperSource.ARXIV


@pytest.mark.asyncio
async def test_search_parses_authors_and_abstract(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """正确解析作者和摘要。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?search_query=ti%3ATest&start=0&max_results=5&sortBy=relevance",
        text=_mock_arxiv_xml(),
        headers=XML_HEADERS,
    )

    paper = (await provider.search("Test"))[0]
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Ashish Vaswani"
    assert "transduction" in paper.abstract


@pytest.mark.asyncio
async def test_search_parses_doi_and_year(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """提取 DOI 和年份。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?search_query=ti%3ATest&start=0&max_results=5&sortBy=relevance",
        text=_mock_arxiv_xml(),
        headers=XML_HEADERS,
    )

    paper = (await provider.search("Test"))[0]
    assert paper.year == 2017
    assert paper.doi is not None
    assert "1706.03762" in paper.doi


@pytest.mark.asyncio
async def test_pdf_url_constructed(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """arXiv 论文提供 PDF URL。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?search_query=ti%3ATest&start=0&max_results=5&sortBy=relevance",
        text=_mock_arxiv_xml(),
        headers=XML_HEADERS,
    )

    paper = (await provider.search("Test"))[0]
    assert paper.pdf_url is not None
    assert paper.open_access is True


@pytest.mark.asyncio
async def test_search_by_author(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """按作者搜索有效。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?search_query=au%3AVaswani&start=0&max_results=5&sortBy=relevance",
        text=_mock_arxiv_xml(),
        headers=XML_HEADERS,
    )

    results = await provider.search_by_author("Vaswani")
    assert len(results) == 1
    assert "Vaswani" in results[0].authors[0].name


@pytest.mark.asyncio
async def test_get_metadata(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """可以通过 arXiv ID 获取元数据。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?id_list=1706.03762&max_results=1",
        text=_mock_arxiv_xml(),
        headers=XML_HEADERS,
    )

    paper = await provider.get_metadata("1706.03762v7")
    assert paper.title == "Attention Is All You Need"


@pytest.mark.asyncio
async def test_get_metadata_not_found(
    provider: ArxivProvider,
    httpx_mock: HTTPXMock,
) -> None:
    """不存在的 ID 抛出 ProviderNotFoundError。"""
    httpx_mock.add_response(
        url=f"{ARXIV_API}?id_list=nonexistent&max_results=1",
        text=_mock_arxiv_xml([]),
        headers=XML_HEADERS,
    )

    with pytest.raises(ProviderNotFoundError):
        await provider.get_metadata("nonexistent")


@pytest.mark.asyncio
async def test_get_pdf_url_from_paper(
    provider: ArxivProvider,
) -> None:
    """PDF URL 从 arXiv 论文 URL 推导得出。"""
    paper = Paper(title="Test", url="https://arxiv.org/abs/1706.03762")
    pdf_url = await provider.get_pdf_url(paper)
    assert pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"


@pytest.mark.asyncio
async def test_parse_empty_feed(
    provider: ArxivProvider,
) -> None:
    """空 Feed 返回空列表。"""
    entries = provider._parse_feed(
        """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <totalResults>0</totalResults>
        </feed>"""
    )
    assert len(entries) == 0
