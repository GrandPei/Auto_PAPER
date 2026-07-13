"""TitleMatcher 的测试。"""

from __future__ import annotations

from paper_downloader.matcher import MatchMethod, TitleMatcher


class TestExactMatch:
    """精确匹配的测试。"""

    def test_exact_match_same_title(self) -> None:
        """完全相同的标题精确匹配。"""
        matcher = TitleMatcher()
        result = matcher.match("Hello World", "Hello World")
        assert result.is_match
        assert result.score == 1.0
        assert result.method == MatchMethod.EXACT

    def test_exact_match_different_titles(self) -> None:
        """低于阈值时不同的标题不匹配。"""
        matcher = TitleMatcher()
        result = matcher.match("Hello World", "Goodbye World")
        assert not result.is_match


class TestCaseInsensitiveMatch:
    """不区分大小写匹配的测试。"""

    def test_case_insensitive_match(self) -> None:
        """仅大小写不同的标题匹配。"""
        matcher = TitleMatcher()
        result = matcher.match("HELLO WORLD", "hello world")
        assert result.is_match
        assert result.method == MatchMethod.CASE_INSENSITIVE

    def test_case_insensitive_no_match(self) -> None:
        """不同的标题即使忽略大小写也不匹配。"""
        matcher = TitleMatcher()
        result = matcher.match("Hello World", "hello universe")
        assert not result.is_match


class TestNormalizedMatch:
    """规范化（去除标点）匹配的测试。"""

    def test_normalized_punctuation(self) -> None:
        """去除标点后标题匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Hello, World! How are you?",
            "Hello World How are you",
        )
        assert result.is_match
        assert result.method == MatchMethod.NORMALIZED

    def test_normalized_whitespace(self) -> None:
        """规范化空白后标题匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Hello   World\t\tTest",
            "Hello World Test",
        )
        assert result.is_match
        assert result.method == MatchMethod.NORMALIZED

    def test_normalized_no_match(self) -> None:
        """不同内容在规范化后不匹配。"""
        matcher = TitleMatcher()
        result = matcher.match("Hello, World!", "Goodbye, World!")
        assert not result.is_match


class TestLevenshteinMatch:
    """Levenshtein 距离匹配的测试。"""

    def test_levenshtein_similar_titles(self) -> None:
        """差异较小的相似标题通过 Levenshtein 匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Attention Is All You Need for Translation",
            "Attention Is All You Need for Translating",
        )
        assert result.is_match
        assert result.score > 0.80

    def test_levenshtein_different_titles(self) -> None:
        """差异很大的标题不匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Attention Is All You Need",
            "A completely different paper about biology",
        )
        assert not result.is_match


class TestRapidFuzzMatch:
    """RapidFuzz 匹配的测试。"""

    def test_rapidfuzz_similar_titles(self) -> None:
        """词序重排的标题通过 RapidFuzz 匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Deep Learning for Natural Language Processing",
            "Natural Language Processing with Deep Learning",
        )
        # 应该通过 rapidfuzz token set ratio 匹配
        assert result.score >= 0.75

    def test_rapidfuzz_different_titles(self) -> None:
        """完全不同的标题不匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Computer Vision Applications",
            "Quantum Computing Breakthroughs",
        )
        assert not result.is_match or result.score < 0.80


class TestDOIMatch:
    """DOI 匹配的测试。"""

    def test_doi_match_exact(self) -> None:
        """相同的 DOI 无论标题如何都返回匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Different Title 1",
            "Different Title 2",
            doi1="10.1234/test",
            doi2="10.1234/test",
        )
        assert result.is_match
        assert result.score == 1.0
        assert result.method == MatchMethod.DOI

    def test_doi_match_different_prefixes(self) -> None:
        """DOI 匹配规范化 URL 前缀。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "T1",
            "T2",
            doi1="https://doi.org/10.1234/test",
            doi2="10.1234/TEST",
        )
        assert result.is_match
        assert result.method == MatchMethod.DOI

    def test_doi_no_match(self) -> None:
        """不同的 DOI 不触发 DOI 匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Same Title",
            "Same Title",
            doi1="10.1234/paper1",
            doi2="10.1234/paper2",
        )
        # 由于标题相同，回退到精确匹配
        assert result.is_match
        assert result.method == MatchMethod.EXACT  # 回退到标题匹配


class TestBestMatch:
    """best_match 方法的测试。"""

    def test_best_match_finds_correct(self) -> None:
        """最佳匹配能识别出最相似的候选。"""
        matcher = TitleMatcher()
        result = matcher.best_match(
            "Attention Is All You Need",
            [
                "BERT: Pre-training of Deep Bidirectional Transformers",
                "Attention Is All You Need",
                "GPT-3: Language Models are Few-Shot Learners",
            ],
        )
        assert result.is_match
        assert result.method == MatchMethod.EXACT

    def test_best_match_no_candidates(self) -> None:
        """空的候选列表返回无匹配。"""
        matcher = TitleMatcher()
        result = matcher.best_match("Test", [])
        assert not result.is_match

    def test_best_match_no_good_match(self) -> None:
        """如果没有候选超过阈值则返回无匹配。"""
        matcher = TitleMatcher()
        result = matcher.best_match(
            "A very specific paper title about quantum computing",
            [
                "Deep learning basics",
                "Introduction to biology",
            ],
            threshold=0.90,
        )
        assert not result.is_match


class TestCustomThreshold:
    """自定义阈值行为的测试。"""

    def test_lower_threshold_accepts(self) -> None:
        """较低的阈值允许较弱的匹配。"""
        matcher = TitleMatcher()
        result = matcher.match(
            "Deep Learning for Natural Language Processing with Transformers",
            "Deep Learning for Natural Language Processing",
            threshold=0.70,
        )
        assert result.is_match
        assert result.score >= 0.70
