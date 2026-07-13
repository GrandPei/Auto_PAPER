# paper_downloader — 学术论文自动下载器

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

一键搜索并下载学术论文 PDF，支持 arXiv、CrossRef、Google Scholar 多源检索。可作为命令行工具独立使用，也可作为 **AI Agent / LLM 项目的论文获取组件**。

---

## 快速开始

```bash
pip install -e .

# 命令行
paper-downloader --title "Attention Is All You Need"
```

```python
from paper_downloader import download_paper, search_papers

# 下载单篇论文
paper = download_paper("Attention Is All You Need")
print(paper.pdf_path)  # → papers/Vaswani_2017_Attention_Is_All_You_Need.pdf

# 批量下载
papers = download_papers(["GPT-4 Technical Report", "BERT: Pre-training"])

# 搜索
results = search_papers("diffusion models", max_results=5)
```

---

## 安装

```bash
# 基础安装
pip install -e .

# 完整安装（含 Google Scholar 等可选依赖）
pip install -e ".[full]"

# 开发安装
pip install -e ".[dev]"
```

## 环境变量

复制 `.env.example` → `.env` 并按需配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PAPER_DOWNLOAD_DIR` | `papers` | PDF 保存目录 |
| `PAPER_CONCURRENT` | `3` | 并发下载数 |
| `PAPER_TIMEOUT` | `120` | 下载超时（秒） |
| `PAPER_CACHE_ENABLED` | `true` | 启用搜索缓存 |
| `PAPER_CACHE_TTL` | `86400` | 缓存过期时间（秒） |
| `PAPER_ENGINES` | `arxiv,crossref` | 默认搜索引擎 |
| `PAPER_LOG_LEVEL` | `INFO` | 日志级别 |

---

## API 文档

### 便捷函数

```python
from paper_downloader import download_paper, download_papers, search_papers, get_paper_info
```

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `download_paper(title, output_dir, engines, rename)` | 标题 + 可选输出目录 | `Paper` | 搜索并下载单篇 PDF |
| `download_papers(titles, output_dir, engines, rename)` | 标题列表 | `List[Paper]` | 批量下载多篇 |
| `search_papers(query, max_results, engines)` | 搜索关键词 | `List[Paper]` | 仅搜索不下载 |
| `get_paper_info(identifier)` | DOI / arXiv ID | `Paper\|None` | 获取论文元数据 |

### Paper 数据模型

```python
paper = download_paper("Attention Is All You Need")

# 核心字段
paper.title          # str
paper.authors        # List[str]
paper.year           # str | None
paper.abstract       # str | None
paper.doi            # str | None
paper.arxiv_id       # str | None

# 属性
paper.has_pdf        # bool — 是否已有本地 PDF
paper.identifier     # str — 最佳标识符 (DOI > arXiv ID > URL)
paper.citation       # str — "Vaswani et al. (2017)"
paper.first_author_surname  # "Vaswani"

# 序列化
paper.to_dict()      # 完整字典
paper.to_json()      # JSON 字符串
paper.to_bibtex()    # BibTeX 条目
```

### 核心类

```python
from paper_downloader import PaperDownloader

# 自定义配置
dl = PaperDownloader(
    output_dir="./my_papers",
    max_downloads=5,
    engines=["arxiv", "crossref"],
)

# 设置进度回调
def on_progress(paper):
    print(f"完成: {paper.title} → {paper.pdf_path}")

dl.set_progress_callback(on_progress)

# 使用
paper = dl.download_by_title("Attention Is All You Need")
papers = dl.batch_download(["GPT-4", "BERT", "ResNet"])
```

### 异步使用

```python
import asyncio
from paper_downloader import AsyncPaperDownloader

async def main():
    async with AsyncPaperDownloader() as dl:
        papers = await dl.batch_download_async([
            "GPT-4 Technical Report",
            "LLaMA: Open and Efficient Foundation Language Models",
        ])

asyncio.run(main())
```

### 缓存

```python
from paper_downloader import CacheManager, cached

# 装饰器 — 透明缓存函数结果
@cached(ttl=3600)
def expensive_search(query: str):
    return call_api(query)

# 直接使用
cache = CacheManager(db_path="cache/data.db")
cache.set("key", value, ttl=86400)
value = cache.get("key")
```

### 报告生成

```python
from paper_downloader import ReportGenerator

gen = ReportGenerator(output_dir="./reports")
gen.export_json(papers)     # download_report_20240101_120000.json
gen.export_csv(papers)      # download_report_20240101_120000.csv
gen.export_markdown(papers) # download_report_20240101_120000.md
gen.export_bibtex(papers)   # references_20240101_120000.bib
```

---

## CLI 使用

```bash
# 下载单篇
paper-downloader --title "Attention Is All You Need"

# 指定输出目录
paper-downloader --title "GPT-4" --output ./my_papers

# 批量下载（从文件，每行一个标题）
paper-downloader --file titles.txt

# 搜索（不下载）
paper-downloader --search "graph neural networks" --max 10

# 搜索并下载
paper-downloader --search "BERT" --download --max 3

# 查询论文信息
paper-downloader --info "10.1038/nature14539"

# 指定搜索引擎
paper-downloader --title "Deep Learning" --engines arxiv crossref

# 使用自定义配置
paper-downloader --title "Attention" --config my_config.yaml
```

---

## AI 项目集成示例

### 作为 LLM Tool

```python
from paper_downloader import PaperDownloader

def llm_tool_download_paper(title: str) -> str:
    """供 LLM Agent 调用的论文下载函数."""
    paper = PaperDownloader().download_by_title(title)
    return json.dumps({
        "status": "success",
        "pdf_path": paper.pdf_path,
        "metadata": paper.to_dict(),
    })
```

### 文献综述

```python
from paper_downloader import search_papers, download_papers, ReportGenerator

papers = search_papers("graph neural networks", max_results=10)
titles = [p.title for p in papers]
downloaded = download_papers(titles, output_dir="./review")
ReportGenerator("./review").export_bibtex(downloaded)
```

### RAG 文档流水线

```python
from paper_downloader import PaperDownloader
from paper_downloader.src.downloaders.pdf_processor import PDFProcessor

paper = PaperDownloader().download_by_title("Attention Is All You Need")
text = PDFProcessor.extract_text(paper.pdf_path, max_pages=5)
# → 送入向量数据库 / LLM 上下文
```

更多示例见 [examples/](examples/)。

---

## 支持的搜索引擎

| 引擎 | 需要 | 说明 |
|------|------|------|
| arXiv | `pip install arxiv` | 数学/物理/CS 领域 |
| CrossRef | 内置（REST API） | 全学科 DOI 检索 |
| Google Scholar | `pip install scholarly` | 需代理/低频率 |

---

## 项目结构

```
paper_downloader/
├── src/
│   ├── core/           # 核心下载器、异步、批量处理
│   ├── search_engines/ # arXiv / CrossRef / Google Scholar
│   ├── downloaders/    # HTTP / arXiv PDF 下载
│   ├── config/         # 配置管理器（单例）
│   ├── cache/          # 双层缓存（内存+SQLite）
│   ├── monitoring/     # 指标收集、健康检查
│   ├── exceptions/     # 异常 + 自动重试装饰器
│   ├── utils/          # 日志、验证器、报告生成
│   ├── models/         # Paper 数据模型
│   ├── api.py          # 模块级便捷 API
│   └── main.py         # CLI 入口
├── config/             # YAML 配置模板
├── tests/              # 366 个测试用例
├── examples/           # 使用示例
└── pyproject.toml
```

---

## 测试

```bash
# 运行所有测试
pytest paper_downloader/tests/ -v

# 包含真实网络测试
PAPER_RUN_REAL_TESTS=1 pytest paper_downloader/tests/ -v

# 仅快速单元测试
pytest paper_downloader/tests/ -v -m "not slow"
```

---

## License

MIT
