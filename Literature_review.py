"""
Literature_review.py — 交互式文献综述生成

流程:
  1. 输入主题 → LLM 生成中英双语关键词
  2. 分别搜索中英文文献
  3. LLM 根据标题+摘要判断每篇与主题的相关性，自动筛选
  4. 逐篇深度解析
  5. 综合生成综述
  6. 交互式修改
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
from typing import List, Dict, Tuple

from Auto_search import search_papers
from AI_writer import chat

# 缓存目录
_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".review_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# Phase 1: 搜索文献（无交互，全部保留）
# ══════════════════════════════════════════════════════════════════

def _search_only(topic: str, num: int, lang_label: str) -> List[Dict]:
    """搜索文献，返回全部结果并标记语言。"""
    ok, papers = search_papers(topic, max(num, 1))
    if not ok:
        print(f"  ✗ [{lang_label}] {papers[0].get('error', '搜索失败')}")
        return []
    for p in papers:
        p['_lang'] = lang_label
    return papers


def phase_search(topic_cn: str, num_cn: int, topic_en: str, num_en: int) -> List[Dict]:
    """分别搜索中英文文献，合并返回。"""
    all_papers = []

    if num_en > 0 and topic_en:
        print(f"\n{'─'*60}")
        print(f"🔍 [EN] 正在搜索: {topic_en}")
        print(f"{'─'*60}")
        en_papers = _search_only(topic_en, num_en, "EN")
        print(f"  找到 {len(en_papers)} 篇英文文献")
        all_papers.extend(en_papers)

    if num_cn > 0 and topic_cn:
        print(f"\n{'─'*60}")
        print(f"🔍 [CN] 正在搜索: {topic_cn}")
        print(f"{'─'*60}")
        cn_papers = _search_only(topic_cn, num_cn, "CN")
        print(f"  找到 {len(cn_papers)} 篇中文文献")
        all_papers.extend(cn_papers)

    return all_papers


# ══════════════════════════════════════════════════════════════════
# Phase 2: LLM 逐篇判断相关性（多线程）
# ══════════════════════════════════════════════════════════════════

FILTER_PROMPT = """你是一位严谨的学术研究者。请判断以下论文是否与综述主题相关。

综述主题：{topic}

论文标题：{title}
摘要：{abstract}

筛选标准：
- 核心相关：研究问题、方法或应用场景与主题直接相关 → 保留
- 边缘相关：仅关键词重叠但实质内容不同 → 剔除
- 无关：领域/问题完全不匹配 → 剔除
- 综述类论文（survey/review）通常保留，它们提供领域全景

只输出一个词：保留 或 剔除"""


def _filter_one(idx: int, paper: Dict, topic: str, total: int, print_lock: Lock) -> Tuple[int, bool]:
    """判断单篇论文与主题的相关性（供线程池调用）。"""
    prompt = FILTER_PROMPT.format(
        topic=topic,
        title=paper['title'],
        abstract=paper.get('abstract', 'N/A')[:300],
    )
    try:
        result = chat(prompt, max_tokens=10, temperature=0.1)
        keep = "保留" in result
        with print_lock:
            status = "✓ 保留" if keep else "✗ 剔除"
            print(f"\r  [{idx}/{total}] {status}  {paper['title'][:55]}", flush=True)
        return (idx, keep)
    except Exception as e:
        with print_lock:
            print(f"\r  [{idx}/{total}] ⚠ 判断失败，默认保留  {paper['title'][:50]}  ({e})", flush=True)
        return (idx, True)  # 失败时保留


def phase_filter(papers: List[Dict], topic: str) -> List[Dict]:
    """多线程逐篇判断每篇论文与主题的相关性，自动剔除不相关文献。"""
    total = len(papers)
    if total <= 3:
        return papers

    print(f"\n{'='*60}")
    print(f"🔎 LLM 逐篇筛选相关文献（共 {total} 篇，{total} 线程并行）...")
    print(f"{'='*60}\n")

    print_lock = Lock()
    keep_indices = set()

    with ThreadPoolExecutor(max_workers=total) as executor:
        futures = [
            executor.submit(_filter_one, i, p, topic, total, print_lock)
            for i, p in enumerate(papers, 1)
        ]
        for future in as_completed(futures):
            try:
                idx, keep = future.result()
                if keep:
                    keep_indices.add(idx)
            except Exception:
                pass  # 异常已在 _filter_one 内处理

    filtered = [p for i, p in enumerate(papers, 1) if i in keep_indices]
    removed = total - len(filtered)
    print(f"\n  保留 {len(filtered)} 篇，剔除 {removed} 篇\n")
    return filtered


# ══════════════════════════════════════════════════════════════════
# Phase 3: 逐篇深度解析
# ══════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """你是一位顶会审稿人，请用中文对以下论文做结构化笔记，每项2-4句话，直击要害，如果得到的资料里没有，则写无：

论文标题：{title}
作者：{authors}  ({year})
摘要：{abstract}

请按以下格式输出（务必严格遵守格式，便于后续汇总）：

【核心问题】
（本文要解决什么痛点？为什么现有方案不够？）

【技术路线】
（提出的方法/模型/框架是什么？关键创新点在哪？）

【实验与结论】
（怎么做验证的？跟谁比？核心数据是什么？）

【局限与启发】
（作者承认的不足 + 你自己判断一篇论文难以覆盖的盲区）"""


def _analyze_one(idx: int, paper: Dict, total: int, print_lock: Lock) -> Dict:
    """解析单篇论文（供线程池调用）。"""
    lang = paper.get('_lang', '')
    prompt = ANALYSIS_PROMPT.format(
        title=paper['title'],
        authors=paper.get('authors', 'N/A'),
        year=paper.get('year', 'N/A'),
        abstract=paper.get('abstract', 'N/A'),
    )
    try:
        analysis = chat(prompt, max_tokens=2048, temperature=0.5)
        paper['_analysis'] = analysis
        with print_lock:
            print(f"\r  [{idx}/{total}] [{lang}] ✓ {paper['title'][:60]}", flush=True)
    except Exception as e:
        paper['_analysis'] = f"[解析失败: {e}]"
        with print_lock:
            print(f"\r  [{idx}/{total}] [{lang}] ✗ {paper['title'][:60]}  ({e})", flush=True)
    return paper


def phase_analyze(papers: List[Dict]) -> List[Dict]:
    """多线程逐篇调用 LLM 做深度解析。"""
    total = len(papers)
    print(f"\n{'='*60}")
    print(f"📖 逐篇解析中（共 {total} 篇，{total} 线程并行）...")
    print(f"{'='*60}\n")

    print_lock = Lock()
    indexed = [(i, p) for i, p in enumerate(papers, 1)]
    results = [None] * total

    with ThreadPoolExecutor(max_workers=total) as executor:
        futures = {
            executor.submit(_analyze_one, i, p, total, print_lock): i - 1
            for i, p in indexed
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                p = papers[idx]
                p['_analysis'] = f"[线程异常: {e}]"
                results[idx] = p

    return [r for r in results if r is not None]


# ══════════════════════════════════════════════════════════════════
# Phase 4: 综述合成
# ══════════════════════════════════════════════════════════════════

SYNTHESIS_PROMPT = """你是一位领域综述的资深作者。请基于以下 {n} 篇论文的深度解析笔记，撰写一篇高质量的文献综述。

要求：
1. 标题自拟，需准确概括综述主题
2. 正文结构：总述技术背景->分时间或范式分类->每类方法代表性工作展开->总结问题，提出未来发展方向
3. 引言要点明该领域的研究价值和演进脉络，不要说"随着AI的发展"这类套话
4. 技术分类要形成清晰的 taxonomy（如按范式/架构/训练策略分），不是一个简单列表
5. 每类方法选择 1-2 篇代表性工作展开，说清 Why-How-What
6. 使用大段描述性文本，禁止使用突兀引号，如：标志着奖励函数设计从“人工编码”向“LLM自动生成”的范式转变，可直接写成标志着奖励函数设计从人工编码向LLM自动生成的范式转变。
7. 开放问题的每个点要对应前文某篇或多篇的具体局限，避免空泛
8. 引用处标注 [1] [2]... 对应文献编号
9. 文末附参考文献列表（GB/T 7714 格式）

以下是 {n} 篇论文的解析笔记：

{analyses}

开始撰写（Markdown 格式）："""


def phase_synthesize(papers: List[Dict], topic: str) -> str:
    """综合所有解析笔记生成综述。"""
    print(f"\n{'='*60}")
    print(f"✍️  综合 {len(papers)} 篇解析生成综述...")
    print(f"{'='*60}")

    analyses_text = ""
    for i, p in enumerate(papers, 1):
        lang = p.get('_lang', '')
        analyses_text += (
            f"\n### [{i}] [{lang}] {p['title']}\n"
            f"作者: {p.get('authors', 'N/A')}  |  {p.get('year', 'N/A')}\n\n"
            f"{p.get('_analysis', '[无解析]')}\n"
            f"---\n"
        )

    prompt = SYNTHESIS_PROMPT.format(
        n=len(papers),
        analyses=analyses_text,
    )

    review = chat(
        prompt,
        system_prompt=f"你是计算机科学领域的综述专家，主题: {topic}。请用学术风格的中文写作。",
        max_tokens=16384,
        temperature=0.6,
    )
    return review


# ══════════════════════════════════════════════════════════════════
# Phase 5: 交互式修改
# ══════════════════════════════════════════════════════════════════

REFINE_PROMPT = """以下是当前文献综述：

---
{review}
---

用户反馈：{feedback}

请仅根据反馈修改综述，保持未涉及部分不变。直接输出修改后的完整综述（Markdown）。"""


def phase_refine(review: str) -> str:
    """交互式循环修改。"""
    current = review
    while True:
        cmd = input("\n  📝 输入修改意见 / 'save' 保存 / 'done' 完成: ").strip()
        if cmd.lower() == 'done':
            return current
        if cmd.lower() == 'save':
            _save_review(current)
            continue
        if not cmd:
            continue

        print("  ⏳ 正在修改...", end=" ", flush=True)
        prompt = REFINE_PROMPT.format(review=current, feedback=cmd)
        try:
            current = chat(prompt, max_tokens=16384, temperature=0.5)
            print("✓\n")
            print(current[:400] + "..." if len(current) > 400 else current)
        except Exception as e:
            print(f"✗ {e}")


# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def _extract_ref_numbers(text: str) -> set:
    """从综述正文中提取被引用的文献编号（仅正文，排除文末参考文献列表）。"""
    import re

    # 截断：只取参考文献列表之前的部分作为正文
    body = re.split(r'\n\s*#+\s*参考', text, maxsplit=1)[0]
    body = re.split(r'\n\s*\[1\]\s', body, maxsplit=1)[0]  # 防止无标题的参考文献列表

    cited = set()
    # 匹配正文中的引用: [1], [1,2], [1-3], [1,3,5]
    for m in re.finditer(r'\[([^\]]+)\]', body):
        content = m.group(1)
        # 跳过非数字引用（如 [EN], [CN]）
        for part in re.findall(r'\d+(?:-\d+)?', content):
            if '-' in part:
                a, b = part.split('-')
                cited.update(range(int(a), int(b) + 1))
            else:
                cited.add(int(part))
    return cited


CITATION_FIX_PROMPT = """以下是文献综述正文和参考文献列表。

检查发现：参考文献中的 [{uncited}] 在正文中未被引用。

请修正此问题，二选一：
A. 若这些文献确实相关，在正文合适位置补充引用标注
B. 若这些文献与主题关联较弱，从参考文献列表中删除

直接输出修正后的完整综述（Markdown），不要解释修改。

当前综述：
---
{review}
---"""


def _fix_uncited_references(review: str, total_papers: int) -> str:
    """检测并修复参考文献未被引用的问题。"""
    # 提取正文引用编号
    cited = _extract_ref_numbers(review)

    # 所有文献编号
    all_refs = set(range(1, total_papers + 1))
    uncited = all_refs - cited

    if not uncited:
        return review

    uncited_list = sorted(uncited)
    print(f"\n  ⚠ 检测到 {len(uncited_list)} 篇参考文献未被引用: {uncited_list}")
    print(f"  🔧 正在自动修复...", end=" ", flush=True)

    prompt = CITATION_FIX_PROMPT.format(
        uncited=', '.join(str(u) for u in uncited_list),
        review=review,
    )
    try:
        fixed = chat(prompt, max_tokens=16384, temperature=0.3)
        # 验证修复结果
        new_cited = _extract_ref_numbers(fixed)
        still_uncited = all_refs - new_cited
        if len(still_uncited) < len(uncited):
            print(f"✓ (剩余 {len(still_uncited)} 篇未引用)")
        else:
            print("⚠ 修复可能不完整")
        return fixed
    except Exception as e:
        print(f"✗ {e}")
        return review


def _save_review(text: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(_CACHE_DIR, f"review_{ts}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  💾 已保存至 {path}")


def _generate_keywords(topic: str) -> Tuple[str, str]:
    """由 LLM 判断语言并生成中英双语检索关键词。"""
    prompt = (
        "你的任务是根据用户输入的研究主题，生成中英双语学术检索关键词。\n\n"
        f"用户输入：{topic}\n\n"
        "要求：\n"
        "1. 判断输入语言，若为中文则翻译为英文关键词，若为英文则翻译为中文关键词\n"
        "2. 中英文关键词都应是适合在 Google Scholar 检索的短语（3-8 词）\n"
        "3. 使用该领域的标准学术术语\n\n"
        "严格按以下格式输出（只输出两行，不要额外解释）：\n"
        "CN: 中文关键词\n"
        "EN: English keywords"
    )
    result = chat(prompt, max_tokens=120, temperature=0.3)
    topic_cn, topic_en = "", ""
    for line in result.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("CN:") or line.startswith("中文"):
            topic_cn = line.split(":", 1)[-1].strip() if ":" in line else line[3:].strip()
        elif line.upper().startswith("EN:") or line.startswith("英文"):
            topic_en = line.split(":", 1)[-1].strip() if ":" in line else line[3:].strip()
    if not topic_cn and not topic_en:
        if any('一' <= c <= '鿿' for c in topic):
            topic_cn, topic_en = topic, ""
        else:
            topic_cn, topic_en = "", topic
    return topic_cn, topic_en


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def run(
    topic: str = "",
    num_cn: int = 5,
    num_en: int = 10,
):
    """交互式文献综述主入口——输入主题，LLM 自动完成关键词翻译、文献筛选、综述撰写。

    Args:
        topic:  研究主题（中英文均可）
        num_cn: 中文文献搜索篇数，0 则跳过
        num_en: 英文文献搜索篇数，0 则跳过
    """
    print("\n" + "="*60)
    print("  📚 交互式文献综述生成系统（中英双语）")
    print("="*60)

    # ── Step 1: 主题 & 篇数 ────────────────────────────────
    if not topic:
        topic = input("\n  输入文献综述主题: ").strip()
        if not topic:
            print("  主题不能为空"); return
    if num_cn <= 0 and num_en <= 0:
        try:
            num_cn = int(input("  中文文献篇数 (默认5，0=跳过): ") or "5")
            num_en = int(input("  英文文献篇数 (默认10，0=跳过): ") or "10")
        except ValueError:
            num_cn, num_en = 5, 10

    # ── Step 2: LLM 生成双语关键词 ─────────────────────────
    print(f"\n  🌐 正在生成双语检索关键词 ...", end=" ", flush=True)
    topic_cn, topic_en = _generate_keywords(topic)
    print(f"→ CN: \"{topic_cn}\"  |  EN: \"{topic_en}\"")
    if num_cn <= 0: topic_cn = ""
    if num_en <= 0: topic_en = ""

    # ── Step 3: 双语搜索 ────────────────────────────────────
    papers = phase_search(topic_cn, num_cn, topic_en, num_en)
    if not papers:
        print("  未搜索到文献，退出。"); return

    # ── Step 4: LLM 自动筛选 ────────────────────────────────
    papers = phase_filter(papers, topic)
    if not papers:
        print("  筛选后无相关文献，退出。"); return
    cn_count = sum(1 for p in papers if p.get('_lang') == 'CN')
    en_count = sum(1 for p in papers if p.get('_lang') == 'EN')
    print(f"\n  最终文献: {len(papers)} 篇（中文 {cn_count} + 英文 {en_count}）")

    review_topic = f"{topic_cn} ({topic_en})" if topic_en else topic_cn

    # ── Step 5: 逐篇解析 ────────────────────────────────────
    papers = phase_analyze(papers)

    # ── Step 6: 合成综述 ────────────────────────────────────
    review = phase_synthesize(papers, review_topic)

    # ── Step 6.5: 检测并修复未引用文献 ──────────────────────
    review = _fix_uncited_references(review, len(papers))

    print("\n" + "="*60)
    print("  📄 综述初稿")
    print("="*60 + "\n")
    print(review)

    # ── Step 7: 交互修改 ────────────────────────────────────
    review = phase_refine(review)

    _save_review(review)
    print("\n  完成！")
