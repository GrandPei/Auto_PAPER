"""Title matching algorithms for paper deduplication and verification.

Provides multiple matching strategies for comparing paper titles,
from simple exact match to fuzzy string matching using Levenshtein
distance and RapidFuzz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from Levenshtein import distance as levenshtein_distance
from loguru import logger
from rapidfuzz import fuzz


class MatchMethod(str, Enum):
    """Matching algorithm used for title comparison."""

    EXACT = "exact"
    """Exact character-by-character match."""

    CASE_INSENSITIVE = "case_insensitive"
    """Match ignoring letter case."""

    NORMALIZED = "normalized"
    """Match after removing punctuation and normalizing whitespace."""

    LEVENSHTEIN = "levenshtein"
    """Match using Levenshtein edit distance ratio."""

    RAPIDFUZZ = "rapidfuzz"
    """Match using RapidFuzz token set ratio."""

    DOI = "doi"
    """Match by DOI (exact DOI comparison)."""

    NONE = "none"
    """No matching method attempted."""


@dataclass
class MatchResult:
    """Result of a title matching operation.

    Attributes:
        is_match: Whether the two strings are considered a match.
        score: Match confidence score from 0.0 (no match) to 1.0 (identical).
        method: The matching algorithm that produced this result.
        details: Additional information about the match.
    """

    is_match: bool
    score: float
    method: MatchMethod
    details: str = ""


class TitleMatcher:
    """Multi-strategy title matcher for paper deduplication.

    Provides progressive matching from strict to fuzzy:
        1. DOI matching (if both have DOIs)
        2. Exact match
        3. Case-insensitive match
        4. Normalized match (no punctuation, collapsed whitespace)
        5. Levenshtein distance ratio
        6. RapidFuzz token set ratio

    The matcher returns the first successful match with the highest
    confidence level.
    """

    # Thresholds for fuzzy matching
    LEVENSHTEIN_THRESHOLD: float = 0.85
    """Minimum Levenshtein ratio to consider a match."""

    RAPIDFUZZ_THRESHOLD: float = 0.80
    """Minimum RapidFuzz token set ratio to consider a match."""

    def match(
        self,
        title1: str,
        title2: str,
        *,
        doi1: str | None = None,
        doi2: str | None = None,
        threshold: float = 0.80,
    ) -> MatchResult:
        """Compare two paper titles using progressive matching strategies.

        Args:
            title1: First paper title.
            title2: Second paper title.
            doi1: DOI of the first paper, if available.
            doi2: DOI of the second paper, if available.
            threshold: Minimum score to consider a match (default 0.80).

        Returns:
            MatchResult with the best match score and method used.
        """
        # Strategy 1: DOI match (most reliable)
        if doi1 and doi2:
            result = self._doi_match(doi1, doi2)
            if result.is_match:
                logger.debug("DOI match confirmed: {} = {}", doi1, doi2)
                return result

        # Strategy 2: Exact match
        result = self._exact_match(title1, title2)
        if result.is_match:
            logger.debug("Exact match confirmed")
            return result

        # Strategy 3: Case-insensitive match
        result = self._case_insensitive_match(title1, title2)
        if result.is_match:
            logger.debug("Case-insensitive match confirmed")
            return result

        # Strategy 4: Normalized match
        result = self._normalized_match(title1, title2)
        if result.is_match:
            logger.debug("Normalized match confirmed")
            return result

        # Strategy 5: Levenshtein distance
        result = self._levenshtein_match(title1, title2)
        if result.score >= threshold:
            result.is_match = True
            logger.debug("Levenshtein match: score={:.3f}", result.score)
            return result

        # Strategy 6: RapidFuzz
        result = self._rapidfuzz_match(title1, title2)
        if result.score >= threshold:
            result.is_match = True
            logger.debug("RapidFuzz match: score={:.3f}", result.score)
            return result

        return MatchResult(
            is_match=False,
            score=result.score,
            method=result.method,
            details="No matching strategy produced a score above threshold",
        )

    def _doi_match(self, doi1: str, doi2: str) -> MatchResult:
        """Match by DOI - exact comparison after normalization.

        Args:
            doi1: First DOI string.
            doi2: Second DOI string.

        Returns:
            MatchResult with score 1.0 if DOIs match.
        """

        # Normalize DOIs: lowercase, strip URL prefixes
        def normalize_doi(doi: str) -> str:
            doi = doi.lower().strip()
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
            return doi

        n1 = normalize_doi(doi1)
        n2 = normalize_doi(doi2)

        if n1 == n2:
            return MatchResult(
                is_match=True,
                score=1.0,
                method=MatchMethod.DOI,
                details=f"DOIs match: {n1}",
            )
        return MatchResult(
            is_match=False,
            score=0.0,
            method=MatchMethod.DOI,
            details=f"DOIs differ: {n1} != {n2}",
        )

    def _exact_match(self, title1: str, title2: str) -> MatchResult:
        """Exact character-by-character comparison.

        Args:
            title1: First title.
            title2: Second title.

        Returns:
            MatchResult with score 1.0 if identical.
        """
        if title1 == title2:
            return MatchResult(
                is_match=True,
                score=1.0,
                method=MatchMethod.EXACT,
                details="Exact character match",
            )
        return MatchResult(
            is_match=False,
            score=0.0,
            method=MatchMethod.EXACT,
            details="Titles differ",
        )

    def _case_insensitive_match(self, title1: str, title2: str) -> MatchResult:
        """Match ignoring letter case.

        Args:
            title1: First title.
            title2: Second title.

        Returns:
            MatchResult with score 1.0 if titles match case-insensitively.
        """
        if title1.lower() == title2.lower():
            return MatchResult(
                is_match=True,
                score=1.0,
                method=MatchMethod.CASE_INSENSITIVE,
                details="Case-insensitive match",
            )
        return MatchResult(
            is_match=False,
            score=0.0,
            method=MatchMethod.CASE_INSENSITIVE,
            details="Titles differ even ignoring case",
        )

    def _normalized_match(self, title1: str, title2: str) -> MatchResult:
        """Match after removing punctuation and normalizing whitespace.

        Args:
            title1: First title.
            title2: Second title.

        Returns:
            MatchResult with score 1.0 if normalized titles match.
        """

        def normalize(text: str) -> str:
            # Lowercase
            text = text.lower()
            # Remove all punctuation except letters, digits and spaces
            text = re.sub(r"[^\w\s]", "", text)
            # Collapse multiple whitespace
            text = re.sub(r"\s+", " ", text).strip()
            return text

        n1 = normalize(title1)
        n2 = normalize(title2)

        if n1 == n2:
            return MatchResult(
                is_match=True,
                score=1.0,
                method=MatchMethod.NORMALIZED,
                details="Normalized titles match",
            )
        return MatchResult(
            is_match=False,
            score=0.0,
            method=MatchMethod.NORMALIZED,
            details="Normalized titles differ",
        )

    def _levenshtein_match(self, title1: str, title2: str) -> MatchResult:
        """Match using Levenshtein edit distance ratio.

        The score is computed as 1 - (edit_distance / max_length).

        Args:
            title1: First title.
            title2: Second title.

        Returns:
            MatchResult with Levenshtein ratio score.
        """
        # Normalize for comparison
        t1 = title1.lower().strip()
        t2 = title2.lower().strip()

        max_len = max(len(t1), len(t2))
        if max_len == 0:
            return MatchResult(
                is_match=True,
                score=1.0,
                method=MatchMethod.LEVENSHTEIN,
                details="Both titles empty",
            )

        distance = levenshtein_distance(t1, t2)
        score = 1.0 - (distance / max_len)

        return MatchResult(
            is_match=score >= self.LEVENSHTEIN_THRESHOLD,
            score=score,
            method=MatchMethod.LEVENSHTEIN,
            details=f"Levenshtein distance={distance}, ratio={score:.4f}",
        )

    def _rapidfuzz_match(self, title1: str, title2: str) -> MatchResult:
        """Match using RapidFuzz token set ratio.

        Token set ratio compares the intersection of words, making it
        robust to word order changes and partial matches.

        Args:
            title1: First title.
            title2: Second title.

        Returns:
            MatchResult with RapidFuzz token set ratio score.
        """
        score = fuzz.token_set_ratio(title1.lower(), title2.lower()) / 100.0

        return MatchResult(
            is_match=score >= self.RAPIDFUZZ_THRESHOLD,
            score=score,
            method=MatchMethod.RAPIDFUZZ,
            details=f"RapidFuzz token_set_ratio={score:.4f}",
        )

    def best_match(
        self,
        query: str,
        candidates: list[str],
        *,
        threshold: float = 0.80,
    ) -> MatchResult:
        """Find the best matching title from a list of candidates.

        Args:
            query: The title to match against.
            candidates: List of candidate titles.
            threshold: Minimum score to consider a match.

        Returns:
            MatchResult for the best matching candidate (highest score).
            Returns no-match result if no candidate exceeds threshold.
        """
        best_result = MatchResult(
            is_match=False,
            score=0.0,
            method=MatchMethod.NONE,
            details="No candidates matched",
        )

        for candidate in candidates:
            result = self.match(query, candidate, threshold=threshold)
            if result.score > best_result.score:
                best_result = result

        return best_result
