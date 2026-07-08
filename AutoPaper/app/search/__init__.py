"""学术搜索引擎（Semantic Scholar / OpenAlex / Arxiv）."""

from app.search.base import BaseSearcher, SearchError
from app.search.manager import SearchManager
from app.search.semantic_scholar import SemanticScholarSearcher
from app.search.openalex import OpenAlexSearcher
from app.search.arxiv import ArxivSearcher

__all__ = [
    "BaseSearcher",
    "SearchError",
    "SearchManager",
    "SemanticScholarSearcher",
    "OpenAlexSearcher",
    "ArxivSearcher",
]
