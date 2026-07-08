# PaperDownloader

企业级学术论文下载器，支持多数据源自动切换。

## 特性

- **多数据源架构**：OpenAlex、Semantic Scholar、arXiv、CrossRef、Unpaywall 五大 Provider
- **全异步**：基于 `httpx` + `asyncio`，全部使用 async/await
- **智能匹配**：标题匹配支持 RapidFuzz 和 Levenshtein 编辑距离
- **稳健下载**：流式下载，支持重试、断点续传、SHA256 校验
- **元数据导出**：支持 JSON、BibTeX、RIS 三种格式
- **SQLite 缓存**：本地缓存避免重复下载
- **类型安全**：100% 类型注解，基于 Pydantic v2
- **企业级质量**：遵循 SOLID 原则，完善测试覆盖，Loguru 日志

## 安装

```bash
pip install paper-downloader
```

或从源码安装：

```bash
git clone https://github.com/username/PaperDownloader.git
cd PaperDownloader
pip install -e ".[dev]"
```

## 快速开始

```python
import asyncio
from paper_downloader import download_paper, download_paper_pdf, download_by_doi, download_many

async def main():
    # 仅获取论文元数据（不下载 PDF）
    result = await download_paper("Attention Is All You Need")
    print(result.paper.title, result.paper.year, result.paper.doi)

    # 下载论文 PDF
    result = await download_paper_pdf("Attention Is All You Need")
    print(result.pdf_path)

    # 通过 DOI 下载
    result = await download_by_doi("10.1038/nature14539")

    # 批量并发下载
    results = await download_many([
        "Attention Is All You Need",
        "BERT: Pre-training of Deep Bidirectional Transformers",
    ])

asyncio.run(main())
```

---

## 项目结构

```
PaperDownloader/
│
├── paper_downloader/                  # 核心包
│   ├── __init__.py                    # 公开 API 导出
│   ├── api.py                         # 对外 API（用户唯一入口）
│   │
│   ├── config/                        # 配置管理
│   │   ├── __init__.py
│   │   └── settings.py               # Pydantic Settings v2，支持 .env
│   │
│   ├── models/                        # 数据模型（Pydantic v2）
│   │   ├── __init__.py
│   │   └── paper.py                  # Paper、Author、Metadata、DownloadResult、
│   │                                  #   DownloadStatus、PaperSource
│   │
│   ├── providers/                     # Provider 层（策略模式）
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseProvider 抽象基类、ProviderRegistry、
│   │   │                              #   ProviderError、ProviderNotFoundError
│   │   ├── openalex.py              # OpenAlex REST API
│   │   ├── semantic_scholar.py      # Semantic Scholar Graph API
│   │   ├── arxiv.py                 # arXiv Atom XML API
│   │   ├── crossref.py              # CrossRef REST API
│   │   └── unpaywall.py             # Unpaywall OA 发现 API
│   │
│   ├── matcher/                       # 标题/DOI 匹配
│   │   ├── __init__.py
│   │   └── title_matcher.py         # TitleMatcher、MatchResult、MatchMethod
│   │
│   ├── downloader/                    # 下载编排
│   │   ├── __init__.py
│   │   ├── manager.py               # DownloadManager（Provider 级联编排）
│   │   └── pdf_downloader.py        # PDFDownloader（流式下载、重试、SHA256）
│   │
│   ├── storage/                       # 持久化层
│   │   ├── __init__.py
│   │   ├── file_store.py            # FileStore（文件名、SHA256、JSON/BibTeX/RIS）
│   │   └── cache.py                 # CacheManager（SQLite，增删改查，去重）
│   │
│   ├── metadata/                      # 元数据导出
│   │   └── __init__.py
│   │
│   └── utils/                         # 工具
│       ├── __init__.py
│       ├── hashing.py               # SHA256 计算
│       └── logging.py               # Loguru 配置
│
├── tests/                             # 测试套件（99 个测试）
│   ├── __init__.py
│   ├── test_models.py               # Paper、Author、Metadata、DownloadResult
│   ├── test_openalex.py             # OpenAlex Provider
│   ├── test_semantic_scholar.py     # Semantic Scholar Provider
│   ├── test_arxiv.py                # arXiv Provider
│   ├── test_crossref.py             # CrossRef Provider
│   ├── test_unpaywall.py            # Unpaywall Provider
│   ├── test_matcher.py              # TitleMatcher
│   └── test_storage.py              # FileStore + CacheManager
│
├── examples/
│   └── basic_usage.py               # 使用示例
│
├── pyproject.toml                    # 项目元数据、依赖、工具配置
├── .env.example                      # 环境变量模板
├── .gitignore
├── CHANGELOG.md
└── README.md
```

---

## 架构设计

### 设计模式

| 模式 | 位置 | 职责 |
|------|------|------|
| **抽象工厂** | `providers/base.py` | `BaseProvider` 定义统一接口，各 Provider 实现具体逻辑 |
| **策略模式** | `providers/` | 每个 Provider 是一个策略，`DownloadManager` 按优先级选择 |
| **服务定位器** | `providers/base.py` | `ProviderRegistry` 维护和查找 Provider 实例 |
| **外观模式** | `api.py` | 对外 API 隐藏所有内部复杂度 |

### 类图

```
┌─────────────────────────────────────────────────────────────┐
│                      api.py（外观层）                         │
│  download_paper() / download_paper_pdf() / download_by_doi()│
│  download_by_url() / download_many() / init()               │
└──────────────────────────┬──────────────────────────────────┘
                           │ 调用
┌──────────────────────────▼──────────────────────────────────┐
│                    DownloadManager                           │
│  - 按优先级依次尝试 Provider                                  │
│  - 通过 TitleMatcher 匹配标题                                 │
│  - 委托 PDFDownloader 执行实际下载                             │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │ 使用             │ 使用             │ 使用
┌──────▼──────┐  ┌────────▼────────┐  ┌──────▼──────────────┐
│ProviderReg- │  │  TitleMatcher   │  │   PDFDownloader     │
│istry        │  │  - 精确匹配      │  │  - 流式下载          │
│ - 注册       │  │  - 忽略大小写    │  │  - 进度条            │
│ - 获取全部   │  │  - 标准化匹配    │  │  - 重试/断点续传     │
│ - 按优先级   │  │  - Levenshtein  │  │  - SHA256 校验      │
└──────┬──────┘  │  - RapidFuzz    │  └──────┬──────────────┘
       │         │  - DOI 匹配      │         │ 使用
       │         └─────────────────┘  ┌──────▼──────────────┐
       │ 管理                         │  FileStore           │
┌──────▼──────────────────────────┐   │  - 文件名清洗         │
│      BaseProvider（抽象基类）     │   │  - SHA256 计算       │
│  + search(title) → list[Paper]  │   │  - 保存 JSON/BibTeX  │
│  + get_metadata(id) → Paper     │   │  - 保存 RIS          │
│  + get_pdf_url(paper) → str|None│   └─────────────────────┘
│  + download(paper, dest) → Paper│
└──────┬──────────────────────────┘   ┌──────────────────────┐
       │ 继承                          │  CacheManager (SQLite)│
  ┌────┴────┬────────┬─────────┐     │  - 新增/查询/更新/删除 │
  │         │        │         │     │  - 计数               │
OpenAlex  arXiv  CrossRef  Unpaywall │  - 存在检查（去重）     │
  S2                                 └──────────────────────┘
```

---

## 下载流程

```
用户调用 download_paper_pdf("Attention Is All You Need")
│
├─► 1. 检查 SQLite 缓存
│   ├── 命中（DOI/标题匹配）→ 返回已缓存的 DownloadResult
│   └── 未命中 → 继续
│
├─► 2. Provider 级联（按优先级依次尝试）
│   │
│   ├── OpenAlex（优先级 10）
│   │   ├── search("Attention Is All You Need") → 返回 3 条结果
│   │   ├── TitleMatcher.best_match() → 匹配分数 0.95
│   │   ├── get_metadata(doi) → 获取完整 Paper 对象
│   │   └── get_pdf_url(paper) → 找到 PDF 链接 ✓
│   │
│   ├── Semantic Scholar（优先级 20）← 跳过（已找到）
│   ├── arXiv（优先级 30）            ← 跳过
│   ├── CrossRef（优先级 40）         ← 跳过
│   └── Unpaywall（优先级 50）        ← 跳过
│
├─► 3. 标题匹配（每个 Provider 内部）
│   ├── 第 1 步：DOI 匹配（双方都有 DOI 时优先）
│   ├── 第 2 步：精确字符匹配
│   ├── 第 3 步：忽略大小写匹配
│   ├── 第 4 步：标准化匹配（去标点、合并空白）
│   ├── 第 5 步：Levenshtein 编辑距离比（阈值：0.85）
│   └── 第 6 步：RapidFuzz 词集比（阈值：0.80）
│
├─► 4. PDF 下载
│   ├── 再次检查缓存（SQLite 按 DOI/sha256 查询）
│   ├── httpx.stream("GET", pdf_url) 流式下载
│   ├── tqdm 进度条实时显示
│   ├── 断点续传（Range 请求头）
│   ├── Tenacity 自动重试（3 次，指数退避）
│   ├── SHA256 完整性校验
│   └── 失败时自动删除残留文件，重试下一轮
│
├─► 5. 保存元数据
│   ├── JSON  → {title}.json
│   ├── BibTeX → {title}.bib
│   └── RIS    → {title}.ris
│
├─► 6. 写入 SQLite 缓存
│   └── INSERT INTO papers (title, doi, provider, pdf_path, sha256, ...)
│
└─► 7. 返回 DownloadResult
    ├── paper: Paper（完整元数据）
    ├── status: SUCCESS | CACHED | FAILED | NOT_FOUND | TIMEOUT
    ├── pdf_path: 本地 PDF 文件路径
    ├── error_message: 错误描述（失败时有值）
    ├── retry_count: 重试次数
    ├── download_time_seconds: 下载耗时（秒）
    └── metadata: Metadata（下载过程元数据）
```

---

## API 参考

以下所有函数均为 **async**，需使用 `await` 调用。

### `download_paper(title: str) → DownloadResult`

在所有 Provider 中搜索论文元数据，**不下载** PDF。

```python
result = await download_paper("Attention Is All You Need")
# result.paper.title       → "Attention Is All You Need"
# result.paper.authors     → [Author(name="Ashish Vaswani"), ...]
# result.paper.year        → 2017
# result.paper.doi         → "10.48550/arXiv.1706.03762"
# result.paper.abstract    → "The dominant sequence transduction..."
# result.paper.pdf_url     → "https://arxiv.org/pdf/1706.03762.pdf"
# result.status            → DownloadStatus.SUCCESS
```

### `download_paper_pdf(title: str) → DownloadResult`

搜索论文 → 获取 PDF 链接 → **下载 PDF** → SHA256 校验 → 保存元数据。

```python
result = await download_paper_pdf("Attention Is All You Need")
# result.pdf_path          → Path("papers/Vaswani_2017_Attention_Is_All_You_Need.pdf")
# result.paper.sha256      → "a1b2c3d4..."
# result.status            → DownloadStatus.SUCCESS
```

### `download_by_doi(doi: str) → DownloadResult`

通过 DOI 下载论文。使用 CrossRef 获取元数据，结合 Unpaywall 查找 OA PDF。

```python
result = await download_by_doi("10.1038/nature14539")
```

### `download_by_url(url: str) → DownloadResult`

从直接 URL 下载论文。自动识别 arXiv 链接。

```python
result = await download_by_url("https://arxiv.org/pdf/1706.03762.pdf")
```

### `download_many(titles: Sequence[str], *, max_concurrent: int | None = None) → list[DownloadResult]`

并发批量下载，通过 `Semaphore` 控制并发数。

```python
results = await download_many(
    ["Paper A", "Paper B", "Paper C"],
    max_concurrent=3,
)
for r in results:
    print(f"{r.paper.title}: {r.status.value}")
```

### `init(*, log_level: str = "INFO", register_provider: BaseProvider | None = None) → None`

初始化 PaperDownloader，配置日志级别，可选注册自定义 Provider。

```python
from paper_downloader import init
init(log_level="DEBUG")
```

---

## 数据模型

### `Paper`（论文）

| 字段 | 类型 | 说明 |
|-------|------|------|
| `title` | `str` | 论文标题（必填） |
| `authors` | `list[Author]` | 作者列表 |
| `abstract` | `str` | 摘要 |
| `year` | `int \| None` | 发表年份（1500–2100） |
| `venue` | `str` | 期刊/会议/仓库名称 |
| `doi` | `str \| None` | 数字对象标识符 |
| `url` | `str` | 论文页面 URL |
| `pdf_url` | `str \| None` | PDF 直链 |
| `pdf_path` | `Path \| None` | 本地 PDF 文件路径 |
| `provider` | `PaperSource` | 数据来源 |
| `citation_count` | `int` | 引用次数（≥ 0） |
| `open_access` | `bool` | 是否开放获取 |
| `license` | `str \| None` | 许可信息 |
| `sha256` | `str \| None` | PDF 文件 SHA-256 哈希 |

### `Author`（作者）

| 字段 | 类型 | 说明 |
|-------|------|------|
| `name` | `str` | 全名（必填） |
| `orcid` | `str \| None` | ORCID 标识符 |
| `affiliation` | `str \| None` | 所属机构 |
| `email` | `str \| None` | 公开邮箱 |

### `DownloadResult`（下载结果）

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `paper` | `Paper` | 论文元数据 |
| `status` | `DownloadStatus` | 下载状态 |
| `pdf_path` | `Path \| None` | 本地 PDF 路径 |
| `error_message` | `str \| None` | 错误描述 |
| `retry_count` | `int` | 重试次数 |
| `download_time_seconds` | `float` | 下载耗时（秒） |
| `metadata` | `Metadata \| None` | 下载过程元数据 |

### `DownloadStatus`（下载状态枚举）

| 值 | 含义 |
|-------|---------|
| `success` | 下载成功，SHA256 校验通过 |
| `cached` | 命中本地缓存 |
| `failed` | 重试耗尽，下载失败 |
| `not_found` | 找到元数据但无可用 PDF |
| `timeout` | 下载超时 |
| `partial` | 部分下载（可续传） |
| `pending` | 尚未开始 |

### `PaperSource`（数据来源枚举）

| 值 | 对应 Provider |
|-------|----------|
| `openalex` | OpenAlex |
| `semantic_scholar` | Semantic Scholar |
| `arxiv` | arXiv |
| `crossref` | CrossRef |
| `unpaywall` | Unpaywall |
| `manual` | 用户手动提供 |
| `unknown` | 未知来源 |

---

## 独立模块用法

以下内部模块均可单独导入使用，不依赖上层 API。

### 配置模块

```python
from paper_downloader.config import get_settings

settings = get_settings()
print(settings.download_dir)   # Path("./papers")
print(settings.log_level)      # "INFO"
```

环境变量（统一使用 `PAPER_` 前缀）：

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `PAPER_DOWNLOAD_DIR` | `./papers` | PDF 存储目录 |
| `PAPER_CACHE_DB` | `./cache/papers.db` | SQLite 缓存路径 |
| `PAPER_OPENALEX_EMAIL` | — | OpenAlex polite pool 邮箱 |
| `PAPER_SEMANTIC_SCHOLAR_API_KEY` | — | Semantic Scholar API 密钥 |
| `PAPER_UNPAYWALL_EMAIL` | — | Unpaywall 邮箱 |
| `PAPER_DOWNLOAD_TIMEOUT` | `300` | 下载超时（秒） |
| `PAPER_DOWNLOAD_MAX_RETRIES` | `3` | 最大重试次数 |
| `PAPER_DOWNLOAD_CONCURRENT_LIMIT` | `5` | 最大并发下载数 |
| `PAPER_LOG_LEVEL` | `INFO` | 日志级别 |
| `PAPER_LOG_FILE` | `paper_downloader.log` | 日志文件路径 |

### TitleMatcher（标题匹配器）

```python
from paper_downloader.matcher import TitleMatcher

matcher = TitleMatcher()

# 比较两个标题
result = matcher.match(
    "Attention Is All You Need",
    "attention is all you need",
    doi1="10.48550/arXiv.1706.03762",
    doi2="10.48550/arXiv.1706.03762",
)
# result.is_match  → True
# result.score     → 1.0
# result.method    → MatchMethod.DOI

# 从候选列表中找最佳匹配
result = matcher.best_match(
    "Attention Is All You Need",
    ["BERT 论文", "Attention Is All You Need", "GPT 论文"],
)
# result.is_match  → True
# result.method    → MatchMethod.EXACT

# 六种匹配策略（按优先级从高到低）：
#   MatchMethod.DOI              — DOI 精确比较
#   MatchMethod.EXACT            — 字符完全一致
#   MatchMethod.CASE_INSENSITIVE — 忽略大小写
#   MatchMethod.NORMALIZED       — 去除标点、合并空白
#   MatchMethod.LEVENSHTEIN      — 编辑距离比
#   MatchMethod.RAPIDFUZZ        — Token Set Ratio

# 自定义匹配阈值
result = matcher.match("标题 A", "标题 B", threshold=0.70)
```

### FileStore（文件存储）

```python
from paper_downloader.storage import FileStore
from paper_downloader.models import Paper, Author

store = FileStore(base_dir="./papers")

# 生成规范文件名（格式：第一作者_年份_标题前80字符）
filename = store.generate_filename(Paper(
    title="Attention Is All You Need",
    authors=[Author(name="Ashish Vaswani")],
    year=2017,
))
# → "Vaswani_2017_Attention_Is_All_You_Need"

# 获取完整 PDF 存储路径
pdf_path = store.get_paper_path(paper)
# → Path("papers/Vaswani_2017_Attention_Is_All_You_Need.pdf")

# 清洗文件名（替换非法字符为下划线）
safe = store.sanitize_filename('test:file<name>.pdf')
# → "test_file_name_.pdf"

# 计算文件 SHA256
sha256 = store.compute_sha256(Path("paper.pdf"))

# 检查文件是否已存在
exists = store.exists(paper)

# 按 SHA256 查找文件（重复文件检测）
path = store.find_by_sha256("a1b2c3d4...")

# 保存元数据（三种格式）
json_path = await store.save_metadata_json(paper)    # → .json
bib_path  = await store.save_metadata_bibtex(paper)   # → .bib
ris_path  = await store.save_metadata_ris(paper)      # → .ris
```

### CacheManager（SQLite 缓存）

```python
from paper_downloader.storage import CacheManager

cache = CacheManager(db_path="./cache/papers.db")
await cache.initialize()

# 新增下载记录
record_id = await cache.add_record(
    title="Attention Is All You Need",
    doi="10.48550/arXiv.1706.03762",
    provider="arxiv",
    pdf_path=Path("papers/paper.pdf"),
    sha256="a1b2c3d4...",
    status="success",
)

# 按 DOI 查询
record = await cache.find_by_doi("10.48550/arXiv.1706.03762")

# 按 SHA256 查询（精确去重）
record = await cache.find_by_sha256("a1b2c3d4...")

# 按标题精确查询
record = await cache.find_by_title("Attention Is All You Need")

# 检查论文是否存在（SHA256 > DOI > 标题 优先级）
exists = await cache.exists(doi="10.48550/arXiv.1706.03762")

# 更新记录
await cache.update_record(record_id, status="success", sha256="newhash")

# 删除记录
await cache.delete_record(record_id)

# 分页列出全部记录
records = await cache.get_all(limit=50, offset=0)

# 记录总数
count = await cache.count()
```

### PDFDownloader（PDF 下载器）

```python
from paper_downloader.downloader import PDFDownloader
from paper_downloader.storage import FileStore, CacheManager

store = FileStore("./papers")
cache = CacheManager("./cache/papers.db")
await cache.initialize()

downloader = PDFDownloader(file_store=store, cache_manager=cache)

# 下载 PDF（自动重试、进度条、SHA256 校验）
paper = await downloader.download(paper)  # paper 必须有 pdf_url
# paper.pdf_path  → Path("papers/Vaswani_2017_Attention.pdf")
# paper.sha256    → "a1b2c3d4e5f6..."

# 带外层重试包装的下载
paper = await downloader.download_with_retry(paper)
```

### ProviderRegistry（Provider 注册中心）

```python
from paper_downloader.providers import BaseProvider, ProviderRegistry
from paper_downloader.providers.openalex import OpenAlexProvider
from paper_downloader.providers.arxiv import ArxivProvider

registry = ProviderRegistry()

# 注册 Provider（priority 越小越优先）
registry.register(OpenAlexProvider(email="me@example.com", priority=10))
registry.register(ArxivProvider(priority=30))

# 按优先级排序获取全部 Provider
providers = registry.get_all()

# 获取指定来源的 Provider
arxiv = registry.get(PaperSource.ARXIV)

# 仅获取支持 PDF 的 Provider
pdf_providers = registry.get_pdf_capable()

# 已注册数量
print(registry.count)  # → 2
```

### 自定义 Provider

```python
from paper_downloader.providers import BaseProvider
from paper_downloader.models import Paper, PaperSource

class MyCustomProvider(BaseProvider):
    def __init__(self):
        super().__init__(
            name="我的数据源",
            source=PaperSource.UNKNOWN,
            priority=60,
        )

    async def search(self, title, *, max_results=5):
        """搜索论文"""
        ...

    async def get_metadata(self, identifier):
        """获取元数据"""
        ...

    async def get_pdf_url(self, paper):
        """获取 PDF 链接"""
        ...

    async def download(self, paper, destination):
        """下载 PDF"""
        ...

# 注册到全局 API
from paper_downloader import init
init(register_provider=MyCustomProvider())
```

### 日志模块

```python
from paper_downloader.utils import setup_logging

setup_logging(
    level="DEBUG",                      # 日志级别
    log_file="paper_downloader.log",    # 日志文件路径
    rotation="10 MB",                   # 滚动切割大小
    retention="7 days",                 # 保留天数
)
```

### 哈希工具

```python
from paper_downloader.utils import compute_sha256

hash_hex = compute_sha256("/path/to/file.pdf")
# → "a1b2c3d4e5f67890..."
```

---

## Provider 能力矩阵

| Provider | API | 搜索 | 元数据 | PDF | 速率限制 |
|----------|-----|--------|----------|-----|------------|
| [OpenAlex](https://openalex.org/) | REST | 标题 | ✓ | OA PDF | 10 万/天（polite pool） |
| [Semantic Scholar](https://semanticscholar.org/) | Graph | 标题、作者 | ✓ + 摘要 | OA PDF | 100/5min（无密钥） |
| [arXiv](https://arxiv.org/) | Atom XML | 标题、作者 | ✓ + 摘要 | 始终可获取 | 1 请求/3 秒 |
| [CrossRef](https://crossref.org/) | REST | 标题→DOI | ✓（DOI 元数据） | — | 50/秒（礼貌模式） |
| [Unpaywall](https://unpaywall.org/) | REST | —（需 DOI 输入） | ✓ + OA 状态 | OA PDF | 10 万/天 |

---

## 配置

复制 `.env.example` 为 `.env`，按需修改：

```bash
cp .env.example .env
```

```ini
PAPER_DOWNLOAD_DIR=./papers
PAPER_CACHE_DB=./cache/papers.db
PAPER_OPENALEX_EMAIL=your-email@example.com
PAPER_SEMANTIC_SCHOLAR_API_KEY=
PAPER_UNPAYWALL_EMAIL=your-email@example.com
PAPER_DOWNLOAD_TIMEOUT=300
PAPER_DOWNLOAD_MAX_RETRIES=3
PAPER_DOWNLOAD_CONCURRENT_LIMIT=5
PAPER_LOG_LEVEL=INFO
```

---

## 开发指南

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
pytest -v

# 跳过慢速测试
pytest -v -m "not slow"

# 代码检查
ruff check paper_downloader/

# 代码格式化
ruff format paper_downloader/

# 类型检查
mypy paper_downloader/
```

---

## 环境要求

- Python 3.12+
- 依赖：pydantic v2, httpx, tenacity, loguru, rapidfuzz, Levenshtein, tqdm, aiosqlite, aiofiles, bibtexparser

## 许可证

MIT
