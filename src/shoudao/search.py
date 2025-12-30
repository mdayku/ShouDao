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
