"""Abstract base class and factory for paper metadata providers.

Architecture: Abstract Factory + Strategy Pattern

    ┌──────────────────────────┐
    │     BaseProvider (ABC)   │
    │  ─────────────────────   │
    │  + search(title) → Paper │
    │  + get_metadata(id)      │
    │  + get_pdf_url(paper)    │
    │  + download(paper)       │
    └────────┬─────────────────┘
             │  implements
     ┌───────┼───────┬──────────┬──────────┬──────────┐
     │       │       │          │          │          │
  OpenAlex  S2    arXiv    CrossRef  Unpaywall  (custom)
  Provider  Prov. Provider  Provider  Provider

Each concrete provider encapsulates API-specific logic while
exposing the same interface. The factory selects the appropriate
provider based on availability and capability.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loguru import logger

from paper_downloader.models import Paper, PaperSource


class BaseProvider(ABC):
    """Abstract base class for all paper metadata providers.

    Defines the Strategy interface that every provider must implement.
    New providers MUST inherit from this class and implement all
    abstract methods to ensure consistent behavior across the system.

    Attributes:
        name: Human-readable provider name.
        source: The PaperSource enum value identifying this provider.
        priority: Priority in the provider cascade (lower = tried first).
    """

    def __init__(self, name: str, source: PaperSource, priority: int = 100) -> None:
        """Initialize the provider.

        Args:
            name: Human-readable provider name.
            source: PaperSource enum value for this provider.
            priority: Cascade priority (lower = tried first). Default 100.
        """
        self.name: str = name
        self.source: PaperSource = source
        self.priority: int = priority

    @abstractmethod
    async def search(
        self,
        title: str,
        *,
        max_results: int = 5,
    ) -> list[Paper]:
        """Search for papers matching the given title.

        Args:
            title: Paper title to search for.
            max_results: Maximum number of results to return.

        Returns:
            A list of Paper objects ordered by relevance (best match first).
            Returns an empty list if no results are found.

        Raises:
            ProviderError: If the API request fails after retries.
        """
        ...

    @abstractmethod
    async def get_metadata(self, identifier: str) -> Paper:
        """Retrieve detailed metadata for a specific paper.

        Args:
            identifier: Provider-specific paper identifier
                (DOI, arXiv ID, OpenAlex ID, etc.).

        Returns:
            A fully populated Paper object.

        Raises:
            ProviderError: If the API request fails or the paper is not found.
        """
        ...

    @abstractmethod
    async def get_pdf_url(self, paper: Paper) -> str | None:
        """Determine the direct PDF URL for a paper.

        This method may modify the paper in-place or return a URL that
        can be set on the Paper object.

        Args:
            paper: The Paper object to find a PDF for.

        Returns:
            A direct PDF URL string, or None if no PDF is available.
        """
        ...

    @abstractmethod
    async def download(self, paper: Paper, destination: str) -> Paper:
        """Download the paper PDF to the specified destination.

        Args:
            paper: The Paper object with pdf_url set.
            destination: Local file path to save the PDF.

        Returns:
            The Paper object with pdf_path and sha256 populated.

        Raises:
            ProviderError: If the download fails.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, priority={self.priority})"

    def __str__(self) -> str:
        return f"{self.name} (priority={self.priority})"


class ProviderError(Exception):
    """Base exception for provider-related errors.

    Attributes:
        provider: Name of the provider that raised the error.
        message: Human-readable error description.
        original_error: The original exception, if any.
    """

    def __init__(
        self,
        provider: str,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize the provider error.

        Args:
            provider: Name of the provider that raised the error.
            message: Human-readable error description.
            original_error: The original exception for chaining.
        """
        self.provider: str = provider
        self.message: str = message
        self.original_error: Exception | None = original_error
        super().__init__(f"[{provider}] {message}")


class ProviderNotFoundError(ProviderError):
    """Raised when a specific paper cannot be found by the provider."""

    def __init__(self, provider: str, identifier: str) -> None:
        """Initialize the not-found error.

        Args:
            provider: Name of the provider.
            identifier: The paper identifier that was searched for.
        """
        super().__init__(provider, f"Paper not found: {identifier}")


class ProviderRegistry:
    """Registry of available providers with priority-based selection.

    Implements a simple service locator pattern that allows the
    download manager to select the best provider for a given task.
    """

    def __init__(self) -> None:
        """Initialize an empty provider registry."""
        self._providers: dict[PaperSource, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        """Register a provider in the registry.

        Args:
            provider: The provider instance to register.

        Raises:
            ValueError: If a provider with the same source is already registered.
        """
        if provider.source in self._providers:
            raise ValueError(
                f"Provider for source '{provider.source.value}' is already registered."
            )
        self._providers[provider.source] = provider
        logger.debug("Registered provider: {}", provider)

    def get(self, source: PaperSource) -> BaseProvider | None:
        """Get a provider by its source type.

        Args:
            source: The PaperSource to look up.

        Returns:
            The provider instance, or None if not registered.
        """
        return self._providers.get(source)

    def get_all(self) -> list[BaseProvider]:
        """Get all registered providers sorted by priority.

        Returns:
            List of providers sorted by priority (lowest first).
        """
        return sorted(self._providers.values(), key=lambda p: p.priority)

    def get_pdf_capable(self) -> list[BaseProvider]:
        """Get providers that can supply PDF URLs or downloads.

        Returns:
            List of PDF-capable providers sorted by priority.
        """
        return [
            p
            for p in self.get_all()
            if p.source
            in {
                PaperSource.OPENALEX,
                PaperSource.SEMANTIC_SCHOLAR,
                PaperSource.ARXIV,
                PaperSource.UNPAYWALL,
            }
        ]

    @property
    def count(self) -> int:
        """Number of registered providers."""
        return len(self._providers)
