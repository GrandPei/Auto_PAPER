# 下载模块优化记录

本文档记录本分支针对 `Auto_PAPER-main` 原始项目中“论文 PDF 下载模块”的优化内容。此次修改只关注论文下载与合法全文获取，不涉及复杂查询 Agent、查询改写、论文检索排序等策略优化。

## 修改目标

在队友的检索/推荐模块已经得到候选论文后，下载模块需要完成：

- 根据论文标题获取合法开放 PDF。
- 对接多个学术来源，避免单一来源下载失败。
- 下载后校验文件确实是可读 PDF。
- 返回结构化下载状态，便于主系统展示和后续处理。
- 避免将 HTML、登录页、错误页或错误论文当作成功下载。

## 主要改动

### 1. 新增 `academic_oa` 下载模式

修改文件：

- `paper_downloader/src/interface.py`

新增引擎模式：

```python
"academic_oa": ["arxiv", "openalex", "semantic_scholar", "crossref"]
```

该模式会依次尝试：

1. arXiv
2. OpenAlex
3. Semantic Scholar
4. CrossRef

Google Scholar 没有放入默认链路，因为它依赖可选包 `scholarly`，且访问稳定性较弱，不适合作为比赛系统的默认可重复测试来源。

### 2. 支持可选 API 配置

修改文件：

- `paper_downloader/src/interface.py`

如果存在以下配置，下载模块会自动读取：

```json
{
  "semantic_scholar": "Semantic Scholar API Key",
  "contact_email": "your_email@example.com"
}
```

推荐路径：

```text
API_key/API_key.json
```

也支持环境变量：

```text
SEMANTIC_SCHOLAR_API_KEY
OPENALEX_EMAIL
CONTACT_EMAIL
```

注意：不要把真实 API Key 提交到 GitHub。

### 3. 修复缺失 cache 模块导致的导入失败

修改文件：

- `paper_downloader/__init__.py`

原始项目会导入：

```python
paper_downloader.src.cache
```

但当前源码树中没有 `src/cache/` 目录，导致导入 `paper_downloader` 时直接报错。已改为可选导入，cache 模块缺失时不影响下载相关功能。

### 4. 主项目下载服务接入 `academic_oa`

修改文件：

- `app/services/download.py`

主项目的 `PaperDownloader` 现在默认使用：

```python
engine="academic_oa"
```

并在下载后做 PDF 校验：

- 文件是否存在。
- 文件大小是否正常。
- 是否以 PDF 文件头开头。
- 是否包含 PDF EOF 标记。
- PDF 页数是否可读取。

### 5. 扩展下载结果模型

修改文件：

- `app/models/download_result.py`

新增字段：

```python
status
file_size
page_count
doi
arxiv_id
```

常见 `status`：

```text
success_valid_pdf
success_pdf_needs_review
invalid_download_not_pdf
title_mismatch
not_found
access_limited_or_paywalled
network_timeout
rate_limited
empty_file
failed_needs_review
```

### 6. 新增下载诊断脚本

新增文件：

- `examples/download_diagnostic.py`

用途：独立测试下载模块，不调用 DeepSeek，不测试 Agent 检索流程。

测试样例来自赛题参考文献：

- PaSa
- LitSearch
- SPAR
- Demonstrate-Search-Predict
- GritLM

运行方式：

```powershell
python examples\download_diagnostic.py
```

输出目录：

```text
download_diagnostics/
```

主要输出：

```text
download_diagnostic_report.csv
download_diagnostic_report.json
pdfs/
```

### 7. 新增主项目服务层测试脚本

新增文件：

- `examples/app_download_service_test.py`

用途：验证 `app/services/download.py` 已经真正接入主项目服务层。

运行方式：

```powershell
python examples\app_download_service_test.py
```

## 队友如何调用下载模块

队友的 Agent 检索模块建议输出如下候选论文结构：

```python
[
    {
        "title": "...",
        "doi": "...",
        "arxiv_id": "...",
        "url": "...",
        "pdf_url": "..."
    }
]
```

当前主下载服务主要按 `title` 调用：

```python
import asyncio
from app.services.download import PaperDownloader


async def main():
    downloader = PaperDownloader(
        save_dir="./papers",
        engine="academic_oa",
    )

    titles = [
        "PaSa: An LLM Agent for Comprehensive Academic Paper Search",
        "SPAR: Scholar Paper Retrieval with LLM-based Agents for Enhanced Academic Search",
    ]

    result = await downloader.download_batch(titles, max_concurrent=1)

    for item in result.results:
        print(item.paper_title)
        print(item.success)
        print(item.status)
        print(item.file_path)
        print(item.source_channel)
        print(item.file_size)
        print(item.page_count)
        print(item.doi)
        print(item.arxiv_id)
        print(item.error)


asyncio.run(main())
```

返回字段说明：

```text
paper_title      下载到的论文标题
success          是否成功
status           结构化状态
file_path        本地 PDF 路径
source_channel   最终来源，如 arxiv / semantic_scholar / crossref
file_size        文件大小
page_count       PDF 页数
doi              DOI
arxiv_id         arXiv ID
error            失败原因
```

## 当前测试结果

`download_diagnostic.py` 最新结果：

```text
5/5 success_valid_pdf
```

各论文来源：

```text
PaSa       -> arxiv
LitSearch  -> crossref
SPAR       -> arxiv
DSP        -> arxiv
GritLM     -> semantic_scholar
```

这说明多 API 链路已经生效：当 arXiv 搜不到时，CrossRef 或 Semantic Scholar 能补上。

`app_download_service_test.py` 最新结果：

```text
2/2 success_valid_pdf
```

说明主项目服务层已经可正常调用下载模块。

## 提交 GitHub 前注意事项

### 1. 不要提交真实 API Key

请检查以下文件是否包含真实 Key：

```text
API_key/API_key.json
.env
赛题.txt
```

如果文件里出现真实 Key，请删除或替换为占位符，并重新生成泄露过的 Key。

### 2. 不建议提交下载产物

以下目录是运行产物，通常不应提交：

```text
download_diagnostics/
papers/
logs/
download_history.json
```

建议确认 `.gitignore` 已排除这些目录。

### 3. 安装问题

重新下载的原项目中 `pyproject.toml` 的旧式 license classifier 会导致新版 setuptools 安装失败。本分支已删除该 classifier。

如果仍遇到依赖问题，可以先安装基础依赖：

```powershell
pip install PyYAML requests rapidfuzz PyPDF2 tqdm beautifulsoup4 lxml arxiv
```

或在项目根目录执行：

```powershell
pip install -e .
```

### 4. 当前限制

- 当前主服务主要以论文标题为入口。
- 如果队友能提供 `doi`、`arxiv_id`、`pdf_url`，后续可以继续增强为“标识符优先下载”，稳定性会更高。
- OpenAlex 可能出现 429；配置 `contact_email` 有助于合规访问，但不能完全避免限流。
- CrossRef 通常提供元数据和 DOI，PDF 下载还依赖后续开放源解析。

## 后续建议

下一步建议增强：

1. 支持候选论文对象输入，而不只是标题列表。
2. 优先使用 `pdf_url`、`arxiv_id`、`doi`，最后才用标题搜索。
3. 把每个 API 源的尝试过程和失败原因写入结果，便于系统展示。
4. 增加标题匹配分数，防止“下载到有效 PDF 但论文不对”的假成功。
