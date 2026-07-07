"""
main.py — Auto Paper 交互式主菜单

集成三大模块:
  1. 文献综述生成 → Literature_review.run()
  2. 文献搜索     → Auto_search.search_papers()
  3. 引用生成     → Auto_quote.get_citation()
"""

from Literature_review import run as run_review
from Auto_search import search_papers
from Auto_quote import get_citation


def _menu():
    print("\n" + "=" * 50)
    print("  📚 Auto Paper — 学术论文辅助工具")
    print("=" * 50)
    print("  1. 文献综述生成（搜索 + 解析 + 综述）")
    print("  2. 文献搜索（按关键词搜索论文列表）")
    print("  3. 引用生成（按文献名获取引用文本）")
    print("  0. 退出")
    print("=" * 50)

    while True:
        choice = input("\n  请选择功能 [0-3]: ").strip()
        if choice in ('0', '1', '2', '3'):
            return choice
        print("  输入无效，请重新输入")


def _interactive_review():
    """交互式输入综述参数。"""
    print("\n" + "─" * 50)
    print("  文献综述生成")
    print("─" * 50)

    topic = input("  输入文献综述主题: ").strip()
    if not topic:
        print("  主题不能为空，已取消。")
        return

    try:
        num_cn = int(input("  中文文献篇数 (默认5，0=跳过): ").strip() or "5")
        num_en = int(input("  英文文献篇数 (默认10，0=跳过): ").strip() or "10")
    except ValueError:
        num_cn, num_en = 5, 10

    if num_cn == 0 and num_en == 0:
        print("  至少需要一种语言的文献，已取消。")
        return

    run_review(topic, num_cn, num_en)


def _interactive_search():
    """交互式输入搜索参数。"""
    print("\n" + "─" * 50)
    print("  文献搜索")
    print("─" * 50)

    keyword = input("  搜索关键词: ").strip()
    if not keyword:
        print("  关键词不能为空，已取消。")
        return

    try:
        num = int(input("  返回篇数 (默认10): ").strip() or "10")
    except ValueError:
        num = 10

    print(f"\n  正在搜索: {keyword} ...\n")
    ok, papers = search_papers(keyword, num)

    if not ok:
        print(f"  ✗ {papers[0].get('error', '搜索失败')}")
        return

    print(f"  共找到 {len(papers)} 篇:\n")
    for i, p in enumerate(papers, 1):
        authors_short = p['authors'][:60] + "..." if len(p['authors']) > 60 else p['authors']
        print(f"  [{i}] {p['title']}")
        print(f"       {authors_short}  |  {p['year']}")
        print(f"       {p['abstract'][:120]}...")
        print()


def _interactive_quote():
    """交互式输入引用参数。"""
    print("\n" + "─" * 50)
    print("  引用生成")
    print("─" * 50)
    print("  支持格式: GB/T 7714 / MLA / APA")
    print()

    title = input("  文献标题: ").strip()
    if not title:
        print("  标题不能为空，已取消。")
        return

    style = input("  引用格式 (默认 GB/T 7714): ").strip() or "GB/T 7714"

    print(f"\n  正在获取引用...\n")
    success, text = get_citation(title, style)

    if success:
        print(f"  [{style}]")
        print(f"  {text}")
    else:
        print(f"  ✗ {text}")


def main():
    while True:
        choice = _menu()
        if choice == '0':
            print("  再见！")
            break
        elif choice == '1':
            _interactive_review()
        elif choice == '2':
            _interactive_search()
        elif choice == '3':
            _interactive_quote()


if __name__ == "__main__":
    main()
