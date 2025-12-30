"""
ShouDao recipe system - save and rerun queries reproducibly.

Recipes are YAML files stored in `recipes/` that define:
- prompt: The search prompt
- filters: Country, industry, org type filters
- use_case: "leads" or "talent"
- context: Product/seller context for advice generation
- policy: Rate limits, max pages, blocked domains
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RecipeFilters(BaseModel):
    """Filters for a recipe."""

    model_config = ConfigDict(extra="forbid")

    countries: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    org_types: list[str] = Field(default_factory=list)


class RecipeContext(BaseModel):
    """Context for advice generation."""

    model_config = ConfigDict(extra="forbid")

    product: str = Field(default="", description="What product/service you're selling")
    seller: str = Field(default="", description="Who you are (for personalization)")


class RecipePolicy(BaseModel):
    """Policy controls for a recipe run."""

    model_config = ConfigDict(extra="forbid")

    max_results: int | None = Field(default=50, description="Max leads/candidates to return")
    max_pages: int = Field(default=100, description="Max pages to fetch")
    blocked_domains: list[str] = Field(default_factory=list)
    seed_sources: list[str] = Field(default_factory=list, description="Known-good URLs to include")


class Recipe(BaseModel):
    """A saved query configuration for reproducible runs."""

    model_config = ConfigDict(extra="forbid")

    # Metadata
    slug: str = Field(..., min_length=1, description="Unique identifier (filename stem)")
    name: str = Field(default="", description="Human-readable name")
    description: str = Field(default="", description="What this recipe does")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Core
    prompt: str = Field(..., min_length=1, description="The search prompt")
    use_case: Literal["leads", "talent"] = Field(default="leads")

    # Filters
    filters: RecipeFilters = Field(default_factory=RecipeFilters)

    # Context (for advice generation)
    context: RecipeContext = Field(default_factory=RecipeContext)

    # Policy
    policy: RecipePolicy = Field(default_factory=RecipePolicy)


def get_recipes_dir() -> Path:
    """Get the recipes directory path."""
    # Look for recipes/ in project root
    cwd = Path.cwd()
    recipes_dir = cwd / "recipes"
    return recipes_dir


def list_recipes() -> list[Recipe]:
    """List all saved recipes."""
    recipes_dir = get_recipes_dir()
    if not recipes_dir.exists():
        return []

    recipes = []
    for path in recipes_dir.glob("*.yml"):
        try:
            recipe = load_recipe(path.stem)
            recipes.append(recipe)
        except Exception:
            continue  # Skip invalid recipes

    return sorted(recipes, key=lambda r: r.slug)


def load_recipe(slug: str) -> Recipe:
    """Load a recipe by slug.

    Args:
        slug: The recipe slug (filename without .yml).

    Returns:
        The loaded Recipe object.

    Raises:
        FileNotFoundError: If recipe doesn't exist.
        ValueError: If recipe is invalid.
    """
    recipes_dir = get_recipes_dir()
    path = recipes_dir / f"{slug}.yml"

    if not path.exists():
        raise FileNotFoundError(f"Recipe not found: {slug}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Ensure slug matches filename
    data["slug"] = slug

    return Recipe(**data)


def save_recipe(recipe: Recipe) -> Path:
    """Save a recipe to disk.

    Args:
        recipe: The recipe to save.

    Returns:
        Path to the saved file.
    """
    recipes_dir = get_recipes_dir()
    recipes_dir.mkdir(parents=True, exist_ok=True)

    path = recipes_dir / f"{recipe.slug}.yml"

    # Convert to dict, excluding None values
    data = recipe.model_dump(mode="json", exclude_none=True)

    # Update timestamp
    data["updated_at"] = datetime.now().isoformat()

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return path


def delete_recipe(slug: str) -> bool:
    """Delete a recipe by slug.

    Args:
        slug: The recipe slug.

    Returns:
        True if deleted, False if not found.
    """
    recipes_dir = get_recipes_dir()
    path = recipes_dir / f"{slug}.yml"

    if path.exists():
        path.unlink()
        return True
    return False


def create_recipe_from_prompt(
    slug: str,
    prompt: str,
    use_case: Literal["leads", "talent"] = "leads",
    name: str = "",
    countries: list[str] | None = None,
    industries: list[str] | None = None,
    product_context: str = "",
    seller_context: str = "",
    max_results: int | None = 50,
) -> Recipe:
    """Create a recipe from a prompt and options.

    Args:
        slug: Unique identifier for the recipe.
        prompt: The search prompt.
        use_case: "leads" or "talent".
        name: Human-readable name.
        countries: Country filters.
        industries: Industry filters.
        product_context: Product context for advice.
        seller_context: Seller context for advice.
        max_results: Maximum results to return.

    Returns:
        The created Recipe object (not yet saved).
    """
    return Recipe(
        slug=slug,
        name=name or slug.replace("-", " ").replace("_", " ").title(),
        prompt=prompt,
        use_case=use_case,
        filters=RecipeFilters(
            countries=countries or [],
            industries=industries or [],
        ),
        context=RecipeContext(
            product=product_context,
            seller=seller_context,
        ),
        policy=RecipePolicy(
            max_results=max_results,
        ),
    )


def recipe_to_run_config(recipe: Recipe) -> dict[str, Any]:
    """Convert a recipe to run pipeline kwargs.

    Args:
        recipe: The recipe to convert.

    Returns:
        Dict of kwargs for run_pipeline or run_talent_pipeline.
    """
    return {
        "prompt": recipe.prompt,
        "countries": recipe.filters.countries,
        "industries": recipe.filters.industries,
        "max_results": recipe.policy.max_results,
        "product_context": recipe.context.product,
        "seller_context": recipe.context.seller,
        "seed_sources": recipe.policy.seed_sources,
    }


