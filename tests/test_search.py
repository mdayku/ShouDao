"""Tests for search module - query expansion and search providers."""


from shoudao.search import (
    CARIBBEAN_COUNTRY_LANGUAGES,
    KEYWORD_PACKS,
    MockSearchProvider,
    expand_prompt_to_queries,
)


class TestExpandPromptToQueries:
    """Tests for query expansion."""

    def test_basic_expansion(self) -> None:
        """Test that a basic prompt expands to multiple queries."""
        queries = expand_prompt_to_queries("contractors", {})
        assert len(queries) >= 4  # Base + contact + directory variants

    def test_includes_contact_variants(self) -> None:
        """Test that expansion includes contact-focused queries."""
        queries = expand_prompt_to_queries("construction companies", {})
        assert any("contact email" in q for q in queries)
        assert any("sales team" in q for q in queries)

    def test_includes_directory_variants(self) -> None:
        """Test that expansion includes directory-focused queries."""
        queries = expand_prompt_to_queries("window suppliers", {})
        assert any("directory list" in q for q in queries)
        assert any("suppliers list" in q for q in queries)

    def test_caribbean_trigger_expansion(self) -> None:
        """Test that Caribbean prompts trigger island-specific queries."""
        queries = expand_prompt_to_queries("window and door suppliers Caribbean", {})
        # Should include country-specific queries
        assert any("Jamaica" in q for q in queries)
        assert any("Puerto Rico" in q for q in queries)
        assert any("Bahamas" in q for q in queries)

    def test_contractor_builder_expansion(self) -> None:
        """Test that Caribbean prompts include contractor/builder queries."""
        queries = expand_prompt_to_queries("windows doors Caribbean islands", {})
        # Should include construction company queries
        assert any("construction company hotel resort" in q for q in queries)
        assert any("general contractor commercial" in q for q in queries)
        assert any("building contractor" in q for q in queries)

    def test_design_build_queries(self) -> None:
        """Test that expansion includes design-build and renovation queries."""
        queries = expand_prompt_to_queries("glazing Caribbean", {})
        # Should include design-build queries (Task 14.2.4)
        assert any("design build firm" in q for q in queries)
        assert any("hotel renovation contractor" in q for q in queries)
        assert any("commercial renovation" in q for q in queries)

    def test_directory_harvesting_queries(self) -> None:
        """Test that expansion includes directory harvesting queries (Tasks 14.3.1-3)."""
        queries = expand_prompt_to_queries("windows doors Caribbean islands", {})
        # Chamber of commerce (Task 14.3.1)
        assert any("chamber of commerce" in q for q in queries)
        # Trade associations (Task 14.3.2)
        assert any("contractors association" in q or "builders association" in q for q in queries)
        # Top contractors lists (Task 14.3.3)
        assert any("top contractors" in q or "top construction companies" in q for q in queries)

    def test_multilingual_queries_spanish(self) -> None:
        """Test that Spanish-speaking markets get Spanish queries."""
        queries = expand_prompt_to_queries("window doors Caribbean Puerto Rico", {})
        # Should include Spanish keywords
        spanish_products = KEYWORD_PACKS["es"]["products"]
        assert any(any(sp in q for sp in spanish_products) for q in queries)

    def test_multilingual_queries_french(self) -> None:
        """Test that French-speaking markets get French queries."""
        queries = expand_prompt_to_queries("windows Caribbean Haiti Martinique", {})
        # Should include French keywords for Haiti/Martinique
        french_products = KEYWORD_PACKS["fr"]["products"]
        assert any(any(fp in q for fp in french_products) for q in queries)


class TestCaribbeanCountryLanguages:
    """Tests for country-language mapping."""

    def test_spanish_countries(self) -> None:
        """Test Spanish-speaking countries are mapped correctly."""
        assert "es" in CARIBBEAN_COUNTRY_LANGUAGES["Puerto Rico"]
        assert "es" in CARIBBEAN_COUNTRY_LANGUAGES["Dominican Republic"]

    def test_french_countries(self) -> None:
        """Test French-speaking countries are mapped correctly."""
        assert "fr" in CARIBBEAN_COUNTRY_LANGUAGES["Haiti"]
        assert "fr" in CARIBBEAN_COUNTRY_LANGUAGES["Martinique"]
        assert "fr" in CARIBBEAN_COUNTRY_LANGUAGES["Guadeloupe"]

    def test_dutch_countries(self) -> None:
        """Test Dutch-speaking countries are mapped correctly."""
        assert "nl" in CARIBBEAN_COUNTRY_LANGUAGES["Aruba"]
        assert "nl" in CARIBBEAN_COUNTRY_LANGUAGES["Curacao"]

    def test_english_countries(self) -> None:
        """Test English-speaking countries are mapped correctly."""
        assert "en" in CARIBBEAN_COUNTRY_LANGUAGES["Jamaica"]
        assert "en" in CARIBBEAN_COUNTRY_LANGUAGES["Barbados"]
        assert "en" in CARIBBEAN_COUNTRY_LANGUAGES["Trinidad and Tobago"]


class TestKeywordPacks:
    """Tests for keyword packs."""

    def test_english_pack_complete(self) -> None:
        """Test English keyword pack has all required keys."""
        assert "products" in KEYWORD_PACKS["en"]
        assert "types" in KEYWORD_PACKS["en"]
        assert "modifiers" in KEYWORD_PACKS["en"]
        assert len(KEYWORD_PACKS["en"]["products"]) >= 3

    def test_spanish_pack_complete(self) -> None:
        """Test Spanish keyword pack has all required keys."""
        assert "products" in KEYWORD_PACKS["es"]
        assert "ventanas" in KEYWORD_PACKS["es"]["products"]
        assert "proveedor" in KEYWORD_PACKS["es"]["types"]

    def test_french_pack_complete(self) -> None:
        """Test French keyword pack has all required keys."""
        assert "products" in KEYWORD_PACKS["fr"]
        assert "fenêtres" in KEYWORD_PACKS["fr"]["products"]


class TestMockSearchProvider:
    """Tests for MockSearchProvider."""

    def test_returns_configured_urls(self) -> None:
        """Test that mock provider returns configured URLs."""
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        provider = MockSearchProvider(urls=urls)
        result = provider.search("test query")
        assert result == urls

    def test_respects_num_results(self) -> None:
        """Test that mock provider respects num_results limit."""
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        provider = MockSearchProvider(urls=urls)
        result = provider.search("test query", num_results=2)
        assert len(result) == 2

    def test_empty_urls(self) -> None:
        """Test mock provider with no URLs configured."""
        provider = MockSearchProvider()
        result = provider.search("test query")
        assert result == []
