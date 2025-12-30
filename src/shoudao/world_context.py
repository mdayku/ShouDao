"""
ShouDao World Context Provider

Authoritative facts for query planning - NOT inside the LLM.
This replaces implicit model knowledge with explicit, auditable data.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class CountryContext(BaseModel):
    """Structured context for a country/territory."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    languages: list[str]
    population: int
    gdp_bucket: str  # tiny, small, medium, large
    import_reliance: str  # low, medium, high, very_high
    china_trade: str  # low, moderate, active
    construction_activity: str  # low, medium, medium-high, high, very_high
    notes: str = ""


class LanguageKeywords(BaseModel):
    """Keywords for a language."""

    model_config = ConfigDict(extra="forbid")

    products: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)


class WorldContext:
    """
    World Context Provider - loads and queries world almanac data.

    Usage:
        ctx = WorldContext.load()
        countries = ctx.get_region_countries("caribbean")
        derived_prompt = ctx.generate_derived_prompt("caribbean", "windows doors")
    """

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self._countries: dict[str, CountryContext] = {}
        self._languages: dict[str, LanguageKeywords] = {}
        self._load_countries()
        self._load_languages()

    def _load_countries(self) -> None:
        """Parse countries from raw data."""
        for _region_key, region_data in self._data.get("regions", {}).items():
            for country_raw in region_data.get("countries", []):
                country = CountryContext(**country_raw)
                self._countries[country.code] = country

    def _load_languages(self) -> None:
        """Parse language keywords from raw data."""
        for lang_code, lang_data in self._data.get("languages", {}).items():
            keywords = lang_data.get("keywords", {})
            self._languages[lang_code] = LanguageKeywords(**keywords)

    @classmethod
    def load(cls, path: Path | None = None) -> "WorldContext":
        """Load world context from YAML file."""
        if path is None:
            # Default path relative to this module
            path = Path(__file__).parent.parent.parent / "data" / "world_context.yaml"

        if not path.exists():
            raise FileNotFoundError(f"World context file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(data)

    def get_region_countries(self, region: str) -> list[CountryContext]:
        """Get all countries in a region."""
        region_data = self._data.get("regions", {}).get(region, {})
        codes = [c["code"] for c in region_data.get("countries", [])]
        return [self._countries[code] for code in codes if code in self._countries]

    def get_country(self, code: str) -> CountryContext | None:
        """Get a specific country by ISO code."""
        return self._countries.get(code)

    def get_language_keywords(self, lang_code: str) -> LanguageKeywords | None:
        """Get keywords for a language."""
        return self._languages.get(lang_code)

    def filter_countries(
        self,
        region: str | None = None,
        min_gdp: str | None = None,
        china_trade: str | None = None,
        languages: list[str] | None = None,
    ) -> list[CountryContext]:
        """Filter countries by criteria."""
        countries = list(self._countries.values())

        if region:
            region_codes = {
                c["code"]
                for c in self._data.get("regions", {}).get(region, {}).get("countries", [])
            }
            countries = [c for c in countries if c.code in region_codes]

        if min_gdp:
            gdp_order = ["tiny", "small", "medium", "large"]
            min_idx = gdp_order.index(min_gdp) if min_gdp in gdp_order else 0
            countries = [c for c in countries if gdp_order.index(c.gdp_bucket) >= min_idx]

        if china_trade:
            countries = [c for c in countries if c.china_trade == china_trade]

        if languages:
            countries = [c for c in countries if any(lang in c.languages for lang in languages)]

        return countries

    def generate_derived_prompt(
        self,
        region: str,
        product_category: str,
        buyer_types: list[str] | None = None,
        exclude_exporters: bool = True,
    ) -> str:
        """
        Generate a derived prompt from structured world context.

        This replaces implicit LLM world knowledge with explicit, auditable facts.
        """
        countries = self.get_region_countries(region)
        if not countries:
            return f"{product_category} suppliers in {region}"

        # Group by language
        lang_countries: dict[str, list[str]] = {}
        for country in countries:
            primary_lang = country.languages[0]
            if primary_lang not in lang_countries:
                lang_countries[primary_lang] = []
            lang_countries[primary_lang].append(country.name)

        # Build market list
        top_markets = sorted(countries, key=lambda c: c.population, reverse=True)[:8]
        market_names = [c.name for c in top_markets]

        # Build language note
        lang_notes = []
        for lang, names in lang_countries.items():
            lang_data = self._languages.get(lang)
            lang_name = lang_data and "keywords" or lang.upper()
            if lang == "en":
                lang_name = "English"
            elif lang == "es":
                lang_name = "Spanish"
            elif lang == "fr":
                lang_name = "French"
            elif lang == "nl":
                lang_name = "Dutch"
            lang_notes.append(
                f"{lang_name} ({', '.join(names[:3])}{'...' if len(names) > 3 else ''})"
            )

        buyer_types = buyer_types or ["suppliers", "distributors", "installers", "contractors"]

        # Generate derived prompt
        prompt_parts = [
            f"Target markets: {', '.join(market_names)}.",
            f"Primary business languages: {'; '.join(lang_notes)}.",
            "These markets import building materials and have active hotel/resort construction.",
            f"Find locally-based {product_category} {', '.join(buyer_types)}.",
        ]

        if exclude_exporters:
            prompt_parts.append(
                "Exclude China-based exporters and manufacturers. "
                "Only include companies based in the target markets."
            )

        return " ".join(prompt_parts)

    def get_query_expansion_config(self, region: str) -> dict[str, Any]:
        """
        Get configuration for query expansion based on region.

        Returns country list and language keywords for the query planner.
        """
        countries = self.get_region_countries(region)

        # Collect unique languages
        all_languages = set()
        for country in countries:
            all_languages.update(country.languages)

        # Get keywords per language
        keywords_by_lang = {}
        for lang in all_languages:
            kw = self.get_language_keywords(lang)
            if kw:
                keywords_by_lang[lang] = kw.model_dump()

        return {
            "countries": [c.model_dump() for c in countries],
            "languages": list(all_languages),
            "keywords": keywords_by_lang,
        }
