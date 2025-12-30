"""
ShouDao search provider - discover URLs from prompts.
"""

import os
from abc import ABC, abstractmethod

import httpx

from .models import RunConfig


class SearchProvider(ABC):
    """Abstract search provider interface."""

    @abstractmethod
    def search(self, query: str, num_results: int = 10) -> list[str]:
        """Execute search and return list of URLs."""
        pass


class SerperProvider(SearchProvider):
    """Serper.dev search API provider."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("SERPER_API_KEY not set")
        self.base_url = "https://google.serper.dev/search"

    def search(self, query: str, num_results: int = 10) -> list[str]:
        """Execute Google search via Serper and return URLs."""
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": num_results,
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(self.base_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        urls = []
        for item in data.get("organic", []):
            if "link" in item:
                urls.append(item["link"])

        return urls


class MockSearchProvider(SearchProvider):
    """Mock provider for testing - returns predefined URLs."""

    def __init__(self, urls: list[str] | None = None):
        self.urls = urls or []

    def search(self, query: str, num_results: int = 10) -> list[str]:
        return self.urls[:num_results]


def get_search_provider(config: RunConfig) -> SearchProvider:
    """Factory to get the configured search provider."""
    if config.search_provider == "serper":
        return SerperProvider()
    elif config.search_provider == "mock":
        return MockSearchProvider(config.seed_sources)
    else:
        raise ValueError(f"Unknown search provider: {config.search_provider}")


def expand_prompt_to_queries(prompt: str, filters: dict) -> list[str]:
    """
    Expand a user prompt into multiple search queries.
    For MVP, we do simple template expansion.
    Later: use LLM for smarter expansion.
    """
    queries = []

    # Base query is the prompt itself
    queries.append(prompt)

    # Add region-specific variants
    region = filters.get("region")
    if region:
        queries.append(f"{prompt} {region}")

    # Add contact-focused variants
    queries.append(f"{prompt} contact email")
    queries.append(f"{prompt} management team")

    # Add directory-focused variants
    queries.append(f"{prompt} directory list")

    return queries
