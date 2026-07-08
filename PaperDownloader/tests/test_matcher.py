"""Tests for TitleMatcher."""

from __future__ import annotations

from paper_downloader.matcher import MatchMethod, TitleMatcher


class TestExactMatch:
    """Tests for exact matching."""

    def test_exact_match_same_title(self) -> None:
        """Identical titles match exactly."""
        matcher = TitleMatcher()
        result = matcher.match("Hello World", "Hello World")
        assert result.is_match
        assert result.score == 1.0
        assert result.method == MatchMethod.EXACT

    def test_exact_match_different_titles(self) -> None:
        """Different titles do not match when below threshold."""
        matcher = TitleMatcher()
        result = matcher.match("Hello World", "Goodbye World")
        assert not result.is_match


class TestCaseInsensitiveMatch:
    """Tests for case-insensitive matching."""

    def test_case_insensitive_match(self) -> None:
        """Titles match when only case differs."""
        matcher = TitleMatcher()
        result = matcher.match("HELLO WORLD", "hello world")
        assert result.is_match
        assert result.method == MatchMethod.CASE_INSENSITIVE

    def test_case_insensitive_no_match(self) -> None:
        """Different titles don't match even case-insensitively."""
        matcher = TitleMatcher()
        result = matcher.match("Hello World", "hello universe")
        assert not result.is_match


class TestNormalizedMatch:
    """Tests for normalized (punctuation-stripped) matching."""

    def test_normalized_punctuation(self) -> None:
        """Titles match after removing punctuation."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Hello, World! How are you?",
            "Hello World How are you",
        )
        assert result.is_match
        assert result.method == MatchMethod.NORMALIZED

    def test_normalized_whitespace(self) -> None:
        """Titles match after normalizing whitespace."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Hello   World\t\tTest",
            "Hello World Test",
        )
        assert result.is_match
        assert result.method == MatchMethod.NORMALIZED

    def test_normalized_no_match(self) -> None:
        """Different content doesn't match after normalization."""
        matcher = TitleMatcher()
        result = matcher.match("Hello, World!", "Goodbye, World!")
        assert not result.is_match


class TestLevenshteinMatch:
    """Tests for Levenshtein distance matching."""

    def test_levenshtein_similar_titles(self) -> None:
        """Similar titles with small differences match via Levenshtein."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Attention Is All You Need for Translation",
            "Attention Is All You Need for Translating",
        )
        assert result.is_match
        assert result.score > 0.80

    def test_levenshtein_different_titles(self) -> None:
        """Very different titles do not match."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Attention Is All You Need",
            "A completely different paper about biology",
        )
        assert not result.is_match


class TestRapidFuzzMatch:
    """Tests for RapidFuzz matching."""

    def test_rapidfuzz_similar_titles(self) -> None:
        """Titles with word reordering match via RapidFuzz."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Deep Learning for Natural Language Processing",
            "Natural Language Processing with Deep Learning",
        )
        # Should match via rapidfuzz token set ratio
        assert result.score >= 0.75

    def test_rapidfuzz_different_titles(self) -> None:
        """Completely different titles do not match."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Computer Vision Applications",
            "Quantum Computing Breakthroughs",
        )
        assert not result.is_match or result.score < 0.80


class TestDOIMatch:
    """Tests for DOI matching."""

    def test_doi_match_exact(self) -> None:
        """Same DOI returns a match regardless of titles."""
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
        """DOI matching normalizes URL prefixes."""
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
        """Different DOIs do not trigger DOI match."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Same Title",
            "Same Title",
            doi1="10.1234/paper1",
            doi2="10.1234/paper2",
        )
        # Falls through to exact match since titles are same
        assert result.is_match
        assert result.method == MatchMethod.EXACT  # Falls through to title match


class TestBestMatch:
    """Tests for best_match method."""

    def test_best_match_finds_correct(self) -> None:
        """Best match identifies the most similar candidate."""
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
        """Empty candidate list returns no match."""
        matcher = TitleMatcher()
        result = matcher.best_match("Test", [])
        assert not result.is_match

    def test_best_match_no_good_match(self) -> None:
        """Returns no match if no candidate exceeds threshold."""
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
    """Tests for custom threshold behavior."""

    def test_lower_threshold_accepts(self) -> None:
        """Lower threshold allows weaker matches."""
        matcher = TitleMatcher()
        result = matcher.match(
            "Deep Learning for Natural Language Processing with Transformers",
            "Deep Learning for Natural Language Processing",
            threshold=0.70,
        )
        assert result.is_match
        assert result.score >= 0.70
