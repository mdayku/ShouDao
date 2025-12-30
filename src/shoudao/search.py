"""
ShouDao search provider - discover URLs from prompts.
"""

import os
import time
from abc import ABC, abstractmethod

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .models import RunConfig


class RateLimitError(Exception):
    """Raised when API returns 429 Too Many Requests."""

    pass


class SearchProvider(ABC):
    """Abstract search provider interface."""

    @abstractmethod
    def search(self, query: str, num_results: int = 10) -> list[str]:
        """Execute search and return list of URLs."""
        pass


class SerperProvider(SearchProvider):
    """Serper.dev search API provider with retry logic."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("SERPER_API_KEY not set")
        self.base_url = "https://google.serper.dev/search"
        self._last_request_time: float = 0
        self._min_request_interval: float = 0.5  # 500ms between requests

    def _wait_for_rate_limit(self) -> None:
        """Ensure minimum interval between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        reraise=True,
    )
    def _search_with_retry(self, query: str, num_results: int) -> list[str]:
        """Execute search with retry on rate limit."""
        self._wait_for_rate_limit()

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

            # Handle rate limiting
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                print(f"  [Rate limit] Serper 429, waiting {retry_after}s...")
                time.sleep(retry_after)
                raise RateLimitError(f"Rate limited, retry after {retry_after}s")

            resp.raise_for_status()
            data = resp.json()

        urls = []
        for item in data.get("organic", []):
            if "link" in item:
                urls.append(item["link"])

        return urls

    def search(self, query: str, num_results: int = 10) -> list[str]:
        """Execute Google search via Serper and return URLs."""
        return self._search_with_retry(query, num_results)


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


# =============================================================================
# COUNTRY → LANGUAGE MAPPING (for multilingual query expansion)
# =============================================================================

CARIBBEAN_COUNTRY_LANGUAGES: dict[str, list[str]] = {
    # Spanish-first
    "Puerto Rico": ["es", "en"],
    "Dominican Republic": ["es"],
    "Cuba": ["es"],
    # French-first
    "Haiti": ["fr"],
    "Guadeloupe": ["fr"],
    "Martinique": ["fr"],
    "Saint Barthelemy": ["fr"],
    "Saint Martin": ["fr"],
    # Dutch-first
    "Aruba": ["nl", "en"],
    "Curacao": ["nl", "en"],
    "Sint Maarten": ["nl", "en"],
    # English-first (Commonwealth Caribbean)
    "Jamaica": ["en"],
    "Trinidad and Tobago": ["en"],
    "Bahamas": ["en"],
    "Barbados": ["en"],
    "Cayman Islands": ["en"],
    "Turks and Caicos": ["en"],
    "St. Lucia": ["en"],
    "Grenada": ["en"],
    "Antigua and Barbuda": ["en"],
    "St. Vincent": ["en"],
    "Dominica": ["en"],
    "British Virgin Islands": ["en"],
    "US Virgin Islands": ["en"],
}

# Keyword packs per language (window/door industry)
KEYWORD_PACKS: dict[str, dict[str, list[str]]] = {
    "en": {
        "products": ["windows", "doors", "windows and doors", "glazing", "aluminum windows"],
        "types": ["supplier", "distributor", "installer", "manufacturer"],
        "modifiers": ["hurricane", "impact", "uPVC", "aluminum"],
    },
    "es": {
        "products": [
            "ventanas",
            "puertas",
            "ventanas y puertas",
            "vidriería",
            "carpintería aluminio",
        ],
        "types": ["proveedor", "distribuidor", "instalador", "fabricante"],
        "modifiers": ["huracán", "impacto", "PVC", "aluminio"],
    },
    "fr": {
        "products": [
            "fenêtres",
            "portes",
            "portes et fenêtres",
            "vitrerie",
            "menuiserie aluminium",
        ],
        "types": ["fournisseur", "distributeur", "installateur", "fabricant"],
        "modifiers": ["ouragan", "cyclone", "PVC", "aluminium"],
    },
    "nl": {
        "products": ["ramen", "deuren", "ramen en deuren", "glas", "kozijnen"],
        "types": ["leverancier", "distributeur", "installateur", "fabrikant"],
        "modifiers": ["orkaan", "aluminium", "PVC"],
    },
}


def expand_prompt_to_queries(prompt: str, filters: dict) -> list[str]:
    """
    Expand a user prompt into multiple search queries.
    Includes multilingual expansion for Caribbean markets.
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
    queries.append(f"{prompt} sales team")

    # Add directory-focused variants
    queries.append(f"{prompt} directory list")
    queries.append(f"{prompt} suppliers list")

    # Caribbean-specific expansions (if prompt mentions Caribbean or Caribbean countries)
    prompt_lower = prompt.lower()
    caribbean_triggers = [
        "caribbean",
        "island",
        "jamaica",
        "trinidad",
        "barbados",
        "bahamas",
        "puerto rico",
        "dominican republic",
        "haiti",
        "guadeloupe",
        "martinique",
        "aruba",
        "curacao",
        "cayman",
    ]
    is_caribbean_prompt = any(trigger in prompt_lower for trigger in caribbean_triggers)

    if is_caribbean_prompt:
        # Detect product category from prompt
        is_window_door = any(
            term in prompt_lower for term in ["window", "door", "glazing", "aluminum", "glass"]
        )

        # Add island-specific queries with language variants
        for country, languages in CARIBBEAN_COUNTRY_LANGUAGES.items():
            for lang in languages[:1]:  # Primary language only for now
                if lang == "en":
                    # English query
                    if is_window_door:
                        queries.append(f"windows doors supplier installer {country}")
                    else:
                        queries.append(f"{prompt} {country}")
                elif lang in KEYWORD_PACKS and is_window_door:
                    # Non-English query using keyword packs
                    pack = KEYWORD_PACKS[lang]
                    product = pack["products"][0]  # Primary product term
                    org_type = pack["types"][0]  # Primary type
                    queries.append(f"{product} {org_type} {country}")

        # Add contractor/builder expansion queries (these are BUYERS, not sellers)
        # These catch companies that USE windows/doors, not just sell them
        top_markets = [
            "Jamaica",
            "Puerto Rico",
            "Dominican Republic",
            "Trinidad and Tobago",
            "Bahamas",
            "Barbados",
        ]
        for market in top_markets:
            # Core contractor queries
            queries.append(f"construction company hotel resort {market}")
            queries.append(f"general contractor commercial {market}")
            queries.append(f"building contractor {market}")
            # Design-build and renovation (Task 14.2.4)
            queries.append(f"design build firm {market}")
            queries.append(f"hotel renovation contractor {market}")
            queries.append(f"commercial renovation {market}")

        # Directory harvesting queries (Tasks 14.3.1-14.3.3)
        for market in top_markets:
            # Chamber of commerce directories
            queries.append(f"chamber of commerce {market} directory")
            queries.append(f"chamber of commerce {market} members construction")
            # Trade association member lists
            queries.append(f"contractors association {market} members")
            queries.append(f"builders association {market} directory")
            queries.append(f"construction association {market}")
            # Top contractors lists
            queries.append(f"top contractors {market}")
            queries.append(f"top construction companies {market}")
            queries.append(f"largest builders {market}")

    return queries


# =============================================================================
# TALENT DISCOVERY QUERIES (Gauntlet Cohort 4)
# =============================================================================

# Core talent discovery queries - high signal surfaces
TALENT_QUERY_TEMPLATES = {
    # GitHub - primary signal source
    "github_ai_agents": [
        'site:github.com "agent" "openai"',
        'site:github.com "llm" "agent"',
        'site:github.com "langchain" project',
        'site:github.com "gpt" "api" project',
        'site:github.com "anthropic" "claude"',
    ],
    "github_demos": [
        'site:github.com "streamlit" "llm"',
        'site:github.com "gradio" "demo"',
        'site:github.com "huggingface" project',
        'site:github.com "openai" "demo"',
    ],
    "github_tooling": [
        'site:github.com "cursor" "ai"',
        'site:github.com "copilot" workflow',
        'site:github.com "ai" "coding" "assistant"',
    ],
    # Blogs and writing - build in public signal
    "blogs": [
        '"learning in public" ai',
        '"built with gpt" project',
        '"building with ai" blog',
        'site:substack.com "ai" "building"',
        'site:substack.com "llm" "project"',
        'site:medium.com "llm" "tutorial"',
        'site:dev.to "openai" "project"',
    ],
    # Demos and apps
    "demos": [
        '"huggingface spaces" personal project',
        '"streamlit" "ai" demo',
        '"vercel" "ai" project',
        '"replicate" demo project',
    ],
    # Adjacent communities
    "communities": [
        '"gauntlet ai" cohort',
        '"buildspace" ai project',
        '"replit" ai agent',
        '"ai engineer" portfolio',
    ],
    # University CS programs (high CCAT correlation)
    "universities": [
        'site:github.com "stanford" "cs" project',
        'site:github.com "mit" "eecs" project',
        'site:github.com "cmu" "cs" project',
        'site:github.com "berkeley" "eecs" project',
        'site:github.com "cornell" "cs" project',
        'site:github.com "university" "computer science" ai',
    ],
}


def expand_talent_queries(prompt: str, filters: dict | None = None) -> list[str]:
    """
    Expand a talent discovery prompt into search queries.

    Args:
        prompt: The user's search prompt (e.g., "AI engineers building agents")
        filters: Optional filters (e.g., {"university": "stanford"})

    Returns:
        List of search queries optimized for finding talent.
    """
    queries = []
    filters = filters or {}

    # Base prompt as-is
    if prompt:
        queries.append(prompt)
        # Add some prompt variants
        queries.append(f"{prompt} github")
        queries.append(f"{prompt} portfolio")
        queries.append(f"{prompt} project")

    # Add all template queries by default
    for category, category_queries in TALENT_QUERY_TEMPLATES.items():
        # Check if we should filter by category
        categories_filter = filters.get("categories")
        if categories_filter and category not in categories_filter:
            continue
        queries.extend(category_queries)

    # Add university-specific queries if filtered
    university = filters.get("university")
    if university:
        queries.append(f'site:github.com "{university}" cs project')
        queries.append(f'site:github.com "{university}" ai project')
        queries.append(f'"{university}" computer science github')

    # Add role-specific queries
    role = filters.get("role")
    if role:
        queries.append(f'"{role}" ai project github')
        queries.append(f'"{role}" llm portfolio')

    # Dedupe while preserving order
    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return unique_queries
