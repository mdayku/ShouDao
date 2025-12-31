"""Tests for recipe system."""

from shoudao.recipe import (
    Recipe,
    RecipeContext,
    RecipeFilters,
    RecipePolicy,
    create_recipe_from_prompt,
    recipe_to_run_config,
)


class TestRecipeFilters:
    """Tests for RecipeFilters model."""

    def test_default_filters(self) -> None:
        """Default filters should be empty lists."""
        filters = RecipeFilters()
        assert filters.countries == []
        assert filters.industries == []
        assert filters.org_types == []

    def test_filters_with_values(self) -> None:
        """Should create filters with values."""
        filters = RecipeFilters(
            countries=["USA", "Canada"],
            industries=["Technology"],
            org_types=["employer"],
        )
        assert "USA" in filters.countries
        assert "Technology" in filters.industries


class TestRecipeContext:
    """Tests for RecipeContext model."""

    def test_default_context(self) -> None:
        """Default context should be empty strings."""
        context = RecipeContext()
        assert context.product == ""
        assert context.seller == ""

    def test_context_with_values(self) -> None:
        """Should create context with values."""
        context = RecipeContext(
            product="AI training program",
            seller="Gauntlet AI",
        )
        assert context.product == "AI training program"


class TestRecipePolicy:
    """Tests for RecipePolicy model."""

    def test_default_policy(self) -> None:
        """Default policy should have reasonable values."""
        policy = RecipePolicy()
        assert policy.max_results == 50
        assert policy.max_pages == 100
        assert policy.blocked_domains == []

    def test_policy_with_values(self) -> None:
        """Should create policy with values."""
        policy = RecipePolicy(
            max_results=100,
            max_pages=200,
            blocked_domains=["spam.com"],
        )
        assert policy.max_results == 100


class TestRecipe:
    """Tests for Recipe model."""

    def test_create_minimal_recipe(self) -> None:
        """Should create a recipe with minimal required fields."""
        recipe = Recipe(
            slug="test-recipe",
            prompt="Find software engineers",
        )
        assert recipe.slug == "test-recipe"
        assert recipe.prompt == "Find software engineers"
        assert recipe.use_case == "leads"  # Default

    def test_create_full_recipe(self) -> None:
        """Should create a recipe with all fields."""
        recipe = Recipe(
            slug="full-recipe",
            name="Full Recipe",
            description="A complete recipe",
            prompt="Find AI engineers in California",
            use_case="talent",
            filters=RecipeFilters(countries=["United States"]),
            context=RecipeContext(product="Gauntlet AI"),
            policy=RecipePolicy(max_results=100),
        )
        assert recipe.use_case == "talent"
        assert "United States" in recipe.filters.countries
        assert recipe.policy.max_results == 100


class TestCreateRecipeFromPrompt:
    """Tests for create_recipe_from_prompt function."""

    def test_create_from_prompt(self) -> None:
        """Should create a recipe from just a prompt."""
        recipe = create_recipe_from_prompt(
            prompt="Find AI engineers",
            slug="ai-engineers",
        )
        assert recipe.slug == "ai-engineers"
        assert recipe.prompt == "Find AI engineers"

    def test_create_with_options(self) -> None:
        """Should create a recipe with additional options."""
        recipe = create_recipe_from_prompt(
            prompt="Find AI engineers",
            slug="ai-talent",
            use_case="talent",
            max_results=25,
        )
        assert recipe.use_case == "talent"
        assert recipe.policy.max_results == 25


class TestRecipeToRunConfig:
    """Tests for recipe_to_run_config function."""

    def test_converts_recipe_to_config(self) -> None:
        """Should convert a recipe to run config dict."""
        recipe = Recipe(
            slug="test",
            prompt="Find engineers",
            use_case="leads",
            filters=RecipeFilters(countries=["USA"]),
            policy=RecipePolicy(max_results=50),
        )
        config = recipe_to_run_config(recipe)
        assert config["prompt"] == "Find engineers"
        assert config["countries"] == ["USA"]
        assert config["max_results"] == 50
