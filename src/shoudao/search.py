"""
ShouDao search provider - discover URLs from prompts.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .models import RunConfig

# Lazy-load WorldContext to avoid circular imports
_world_context_cache: Any = None


def _get_world_context() -> Any:
    """Lazy-load and cache WorldContext."""
    global _world_context_cache
    if _world_context_cache is None:
        try:
            from .world_context import WorldContext

            _world_context_cache = WorldContext.load()
        except Exception:
            _world_context_cache = False  # Mark as failed, don't retry
    return _world_context_cache if _world_context_cache else None


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


def _detect_product_category(prompt_lower: str) -> str:
    """Detect product category from prompt text."""
    building_keywords = ["window", "door", "glazing", "aluminum", "glass", "roofing", "flooring"]
    food_keywords = [
        "takeout",
        "food container",
        "sushi",
        "restaurant",
        "cafe",
        "supermarket",
        "grocery",
        "fast food",
        "packaging",
        "disposable",
    ]

    if any(kw in prompt_lower for kw in building_keywords):
        return "building_materials"
    elif any(kw in prompt_lower for kw in food_keywords):
        return "food_service"
    return "unknown"


def _get_keywords_for_category(lang: str, category: str) -> dict[str, list[str]]:
    """Get keywords from WorldContext or fall back to hardcoded."""
    ctx = _get_world_context()

    if ctx:
        # Try to get from WorldContext
        lang_data = ctx._data.get("languages", {}).get(lang, {}).get("keywords", {})

        if category == "food_service" and "food_service" in lang_data:
            fs = lang_data["food_service"]
            return {
                "products": fs.get("products", []),
                "types": fs.get("types", []),
                "buyers": fs.get("buyers", []),
            }
        elif category == "building_materials":
            return {
                "products": lang_data.get("products", []),
                "types": lang_data.get("types", []),
                "modifiers": lang_data.get("modifiers", []),
            }

    # Fall back to hardcoded KEYWORD_PACKS
    if lang in KEYWORD_PACKS:
        return KEYWORD_PACKS[lang]
    return {}


def expand_prompt_to_queries(prompt: str, filters: dict) -> list[str]:
    """
    Expand a user prompt into multiple search queries.
    Includes multilingual expansion for Caribbean markets.
    Uses WorldContext for keywords when available.
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
        "maarten",  # Sint Maarten
        "st martin",  # Saint Martin
        "saint martin",  # Saint Martin (full)
    ]
    is_caribbean_prompt = any(trigger in prompt_lower for trigger in caribbean_triggers)

    if is_caribbean_prompt:
        # Detect product category from prompt
        product_category = _detect_product_category(prompt_lower)
        is_window_door = product_category == "building_materials"
        is_food_service = product_category == "food_service"

        # Add island-specific queries with language variants
        for country, languages in CARIBBEAN_COUNTRY_LANGUAGES.items():
            for lang in languages[:1]:  # Primary language only for now
                # Get keywords from WorldContext or fallback
                keywords = _get_keywords_for_category(lang, product_category)

                if lang == "en":
                    # English query - use WorldContext keywords if available
                    if is_window_door:
                        queries.append(f"windows doors supplier installer {country}")
                    elif is_food_service and keywords.get("products"):
                        # Use food service keywords from WorldContext
                        product = keywords["products"][0]
                        buyer = keywords.get("buyers", ["restaurant"])[0]
                        queries.append(f"{product} {buyer} {country}")
                    else:
                        queries.append(f"{prompt} {country}")
                elif keywords.get("products"):
                    # Non-English query using WorldContext or fallback keywords
                    product = keywords["products"][0]  # Primary product term
                    org_type = keywords.get("types", [""])[0]  # Primary type
                    if product and org_type:
                        queries.append(f"{product} {org_type} {country}")
                    elif product:
                        queries.append(f"{product} {country}")

        # Add contractor/builder expansion queries ONLY for building materials prompts
        # These catch companies that USE windows/doors, not just sell them
        if is_window_door:
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

        # Add food service buyer expansion queries ONLY for food service prompts
        # These catch chain restaurants, supermarkets, hotels with F&B operations
        if is_food_service:
            # Focus on the specific markets mentioned in prompt, or top Caribbean markets
            food_markets = [
                "Sint Maarten",
                "Saint Martin",
                "Puerto Rico",
                "Jamaica",
                "Bahamas",
                "Dominican Republic",
            ]
            for market in food_markets:
                # Chain/franchise queries - these are the high-volume buyers
                queries.append(f"restaurant chain {market}")
                queries.append(f"franchise restaurant {market}")
                queries.append(f"supermarket chain {market}")
                queries.append(f"grocery store chain {market}")
                # Hotel F&B - large volume buyers
                queries.append(f"hotel restaurant {market}")
                queries.append(f"resort dining {market}")
                # Quick service / fast food
                queries.append(f"fast food {market}")
                queries.append(f"quick service restaurant {market}")

            # Food industry directories
            for market in food_markets[:3]:  # Top 3 only to limit query count
                queries.append(f"restaurant association {market}")
                queries.append(f"hospitality association {market}")
                queries.append(f"food service directory {market}")

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


def _get_talent_templates_from_world_context() -> dict[str, list[str]] | None:
    """Load talent query templates from WorldContext if available."""
    ctx = _get_world_context()
    if not ctx:
        return None

    # Try to get Gauntlet-specific templates
    talent_programs = ctx._data.get("talent_programs", {})
    gauntlet = talent_programs.get("gauntlet", {})
    templates = gauntlet.get("query_templates", {})

    if templates:
        return templates
    return None


def expand_talent_queries(prompt: str, filters: dict | None = None) -> list[str]:
    """
    Expand a talent discovery prompt into search queries.
    Uses WorldContext for templates when available, falls back to hardcoded.

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

    # Try WorldContext templates first, fall back to hardcoded
    wc_templates = _get_talent_templates_from_world_context()
    templates = wc_templates if wc_templates else TALENT_QUERY_TEMPLATES

    # Add all template queries by default
    for category, category_queries in templates.items():
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

    # Add top schools from WorldContext (if not filtering by specific university)
    if not university:
        ctx = _get_world_context()
        if ctx:
            talent_programs = ctx._data.get("talent_programs", {})
            gauntlet = talent_programs.get("gauntlet", {})
            target_schools = gauntlet.get("target_schools", {})
            # Only add tier 1 schools to avoid query explosion
            tier_1 = target_schools.get("tier_1", [])[:5]  # Top 5 only
            for school in tier_1:
                queries.append(f'site:github.com "{school}" ai project')

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
