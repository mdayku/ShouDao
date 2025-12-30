"""
ShouDao CLI - command line interface.
"""

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@click.group()
@click.version_option(version="0.1.0", prog_name="shoudao")
def main() -> None:
    """ShouDao - Prompt to Leads CSV"""
    pass


@main.command()
@click.option("--prompt", "-p", required=True, help="Search prompt describing the leads you want")
@click.option(
    "--region",
    "-r",
    default=None,
    help="Use world context for region (e.g., 'caribbean'). Generates derived prompt.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="runs",
    help="Output directory for run artifacts (default: runs/)",
)
@click.option(
    "--max-results",
    "-n",
    type=int,
    default=50,
    help="Maximum number of leads to return; use 0 for unlimited (default: 50)",
)
@click.option("--country", multiple=True, help="Filter by country (can specify multiple)")
@click.option("--industry", multiple=True, help="Filter by industry (can specify multiple)")
@click.option(
    "--product-context", default="", help="What product/service you're selling (for better advice)"
)
@click.option("--seller-context", default="", help="Who you are (for better personalization)")
def run(
    prompt: str,
    region: str | None,
    output: str,
    max_results: int,
    country: tuple[str, ...],
    industry: tuple[str, ...],
    product_context: str,
    seller_context: str,
) -> None:
    """Run a lead generation query."""
    from .pipeline import run_pipeline
    from .world_context import WorldContext

    output_dir = Path(output)
    max_results_opt: int | None = max_results
    if max_results <= 0:
        max_results_opt = None

    # If region specified, generate derived prompt from world context
    final_prompt = prompt
    if region:
        try:
            ctx = WorldContext.load()
            derived = ctx.generate_derived_prompt(
                region=region,
                product_category=prompt,
                exclude_exporters=True,
            )
            final_prompt = derived
            click.echo(f"[ShouDao] Using world context for region: {region}")
            click.echo(f"[ShouDao] Derived prompt: {final_prompt[:100]}...")
        except FileNotFoundError:
            click.echo("Warning: World context file not found, using raw prompt", err=True)
        except Exception as e:
            click.echo(f"Warning: Could not load world context: {e}", err=True)

    try:
        result = run_pipeline(
            prompt=final_prompt,
            countries=list(country),
            industries=list(industry),
            max_results=max_results_opt,
            output_dir=output_dir,
            product_context=product_context,
            seller_context=seller_context,
        )

        click.echo(f"\nGenerated {len(result.leads)} leads")
        if result.errors:
            click.echo(f"Warnings: {len(result.errors)}")
            for err in result.errors[:3]:
                click.echo(f"  - {err}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Make sure OPENAI_API_KEY and SERPER_API_KEY are set in .env", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Pipeline error: {e}", err=True)
        sys.exit(1)


@main.command()
def check() -> None:
    """Check if required API keys are configured."""
    import os

    click.echo("Checking configuration...\n")

    openai_key = os.getenv("OPENAI_API_KEY")
    serper_key = os.getenv("SERPER_API_KEY")
    apify_key = os.getenv("APIFY_API_KEY")

    click.echo("Required:")
    if openai_key:
        click.echo(f"  OPENAI_API_KEY: {openai_key[:8]}...{openai_key[-4:]}")
    else:
        click.echo("  OPENAI_API_KEY: NOT SET (required)")

    if serper_key:
        click.echo(f"  SERPER_API_KEY: {serper_key[:8]}...{serper_key[-4:]}")
    else:
        click.echo("  SERPER_API_KEY: NOT SET (required for search)")

    github_token = os.getenv("GITHUB_TOKEN")

    click.echo("\nOptional:")
    if apify_key:
        click.echo(f"  APIFY_API_KEY:  {apify_key[:8]}...{apify_key[-4:]} (LinkedIn enabled)")
    else:
        click.echo("  APIFY_API_KEY:  NOT SET (LinkedIn disabled)")

    if github_token:
        click.echo(f"  GITHUB_TOKEN:   {github_token[:8]}...{github_token[-4:]} (5000 req/hr)")
    else:
        click.echo("  GITHUB_TOKEN:   NOT SET (60 req/hr limit)")

    if openai_key and serper_key:
        click.echo("\nAll required keys are set. Ready to run!")
    else:
        click.echo("\nMissing keys. Copy env.example to .env and fill in your values.")
        sys.exit(1)


@main.command()
@click.option("--prompt", "-p", required=True, help="What kind of candidates you're looking for")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="runs",
    help="Output directory for run artifacts (default: runs/)",
)
@click.option(
    "--max-results",
    "-n",
    type=int,
    default=50,
    help="Maximum number of candidates to return; use 0 for unlimited (default: 50)",
)
@click.option(
    "--linkedin/--no-linkedin",
    default=False,
    help="Use LinkedIn as primary source (requires APIFY_API_KEY)",
)
@click.option(
    "--linkedin-mode",
    type=click.Choice(["Short", "Full"]),
    default="Full",
    help="LinkedIn scraper mode: Short (basic) or Full (detailed)",
)
@click.option(
    "--location",
    "-l",
    multiple=True,
    default=["United States"],
    help="Filter by location (can specify multiple, default: 'United States')",
)
@click.option(
    "--enrich/--no-enrich",
    default=True,
    help="Enrich candidates with GitHub data (default: enabled)",
)
def talent(
    prompt: str,
    output: str,
    max_results: int,
    linkedin: bool,
    linkedin_mode: str,
    location: tuple[str, ...],
    enrich: bool,
) -> None:
    """Run a talent discovery query (Gauntlet Cohort 4 style).

    Finds candidates based on public signals:
    - GitHub repos and AI/LLM projects
    - Technical blogs and "building in public"
    - Education and experience signals
    - Salary band estimation

    A candidate is qualified if we can contact them (email OR social media).

    Use --linkedin to source candidates from LinkedIn instead of web search.
    """
    from .pipeline import run_talent_pipeline

    output_dir = Path(output)
    max_results_opt: int | None = max_results
    if max_results <= 0:
        max_results_opt = None

    locations_list = list(location) if location else ["United States"]

    if linkedin:
        click.echo("[ShouDao] Using LinkedIn as primary source")
        click.echo(f"[ShouDao] LinkedIn mode: {linkedin_mode}")
        click.echo(f"[ShouDao] Locations: {', '.join(locations_list)}")
        click.echo("[ShouDao] Profile language: English")

    if enrich:
        click.echo("[ShouDao] GitHub enrichment: enabled")

    try:
        result = run_talent_pipeline(
            prompt=prompt,
            output_dir=output_dir,
            max_results=max_results_opt,
            use_linkedin=linkedin,
            linkedin_mode=linkedin_mode,
            locations=locations_list,
            enrich_github=enrich,
        )

        click.echo(f"\nFound {len(result.candidates)} candidates")
        click.echo(f"  Tier A: {result.tier_a_count}")
        click.echo(f"  Tier B: {result.tier_b_count}")
        click.echo(f"  Tier C: {result.tier_c_count}")
        click.echo(f"  Contactable: {result.contactable_candidates}")

        if result.errors:
            click.echo(f"\nWarnings: {len(result.errors)}")
            for err in result.errors[:3]:
                click.echo(f"  - {err}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Make sure OPENAI_API_KEY and SERPER_API_KEY are set in .env", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Pipeline error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--region", "-r", default=None, help="Show countries in a specific region")
@click.option("--list-regions", is_flag=True, help="List available regions")
def world(region: str | None, list_regions: bool) -> None:
    """Inspect world context data."""
    from .world_context import WorldContext

    try:
        ctx = WorldContext.load()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if list_regions:
        click.echo("Available regions:")
        for region_key in ctx._data.get("regions", {}).keys():
            countries = ctx.get_region_countries(region_key)
            click.echo(f"  {region_key}: {len(countries)} countries")
        return

    if region:
        countries = ctx.get_region_countries(region)
        if not countries:
            click.echo(f"No countries found for region: {region}", err=True)
            sys.exit(1)

        click.echo(f"\n{region.upper()} ({len(countries)} countries)\n")
        click.echo(f"{'Country':<25} {'Lang':<8} {'GDP':<8} {'China':<10} {'Construction'}")
        click.echo("-" * 70)
        for c in countries:
            click.echo(
                f"{c.name:<25} {','.join(c.languages):<8} {c.gdp_bucket:<8} "
                f"{c.china_trade:<10} {c.construction_activity}"
            )

        # Show derived prompt example
        click.echo("\nExample derived prompt for 'windows doors':")
        click.echo("-" * 70)
        derived = ctx.generate_derived_prompt(region, "windows doors")
        click.echo(derived)
    else:
        click.echo("Use --list-regions to see available regions")
        click.echo("Use --region <name> to see countries in that region")


@main.command()
@click.option("--search", "-s", default=None, help="Search for profiles by keywords")
@click.option("--profile", "-p", default=None, help="Scrape a specific LinkedIn profile URL")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["Short", "Full"]),
    default="Short",
    help="Scraper mode: Short (basic) or Full (detailed)",
)
@click.option("--max", "-n", "max_results", type=int, default=5, help="Max profiles to return")
def linkedin(search: str | None, profile: str | None, mode: str, max_results: int) -> None:
    """Test LinkedIn integration via Apify (for debugging).

    For full candidate sourcing with exports, use: shoudao talent --linkedin
    """
    from .linkedin import get_linkedin_provider

    provider = get_linkedin_provider()
    if not provider:
        click.echo("LinkedIn not configured. Set APIFY_API_KEY in .env", err=True)
        sys.exit(1)

    if search:
        click.echo(f"Searching LinkedIn for: {search}\n")
        profiles = provider.search_profiles(search, max_results=max_results, scraper_mode=mode)

        if not profiles:
            click.echo("No profiles found.")
            return

        click.echo(f"Found {len(profiles)} profiles:\n")
        for p in profiles[:10]:  # Show first 10
            # Sanitize for Windows console encoding
            name = (p.name or "Unknown").encode("ascii", "replace").decode("ascii")
            headline = (p.headline or "No headline").encode("ascii", "replace").decode("ascii")
            click.echo(f"  {name}")
            click.echo(f"    {headline}")
            click.echo(f"    {p.url}")
            click.echo()

        if len(profiles) > 10:
            click.echo(f"  ... and {len(profiles) - 10} more\n")

        click.echo("Tip: Use 'shoudao talent --linkedin' for full pipeline with exports.")

    elif profile:
        click.echo(f"Scraping profile: {profile}\n")
        p = provider.scrape_profile(profile)

        if not p:
            click.echo("Could not scrape profile.", err=True)
            sys.exit(1)

        click.echo(f"Name:       {p.name}")
        click.echo(f"Headline:   {p.headline}")
        click.echo(f"Location:   {p.location}")
        click.echo(f"Company:    {p.current_company}")
        click.echo(f"Title:      {p.current_title}")
        click.echo(f"School:     {p.school}")
        click.echo(f"Degree:     {p.degree}")
        click.echo(f"Years exp:  {p.years_experience}")
        click.echo(f"Email:      {p.email}")

    else:
        click.echo("Usage:")
        click.echo("  shoudao linkedin --search 'software engineer AI'")
        click.echo("  shoudao linkedin --profile 'https://linkedin.com/in/someone'")


# =============================================================================
# RECIPE COMMANDS
# =============================================================================


@main.group()
def recipe() -> None:
    """Manage saved recipes (query configurations)."""
    pass


@recipe.command("list")
def recipe_list() -> None:
    """List all saved recipes."""
    from .recipe import list_recipes

    recipes = list_recipes()

    if not recipes:
        click.echo("No recipes found. Create one with: shoudao recipe create")
        return

    click.echo(f"\nSaved Recipes ({len(recipes)})\n")
    click.echo(f"{'Slug':<25} {'Use Case':<10} {'Prompt'}")
    click.echo("-" * 70)

    for r in recipes:
        prompt_preview = r.prompt[:40] + "..." if len(r.prompt) > 40 else r.prompt
        click.echo(f"{r.slug:<25} {r.use_case:<10} {prompt_preview}")


@recipe.command("show")
@click.argument("slug")
def recipe_show(slug: str) -> None:
    """Show details of a recipe."""
    from .recipe import load_recipe

    try:
        r = load_recipe(slug)
    except FileNotFoundError:
        click.echo(f"Recipe not found: {slug}", err=True)
        sys.exit(1)

    click.echo(f"\nRecipe: {r.name or r.slug}")
    click.echo("-" * 40)
    click.echo(f"Slug:       {r.slug}")
    click.echo(f"Use case:   {r.use_case}")
    click.echo(f"Prompt:     {r.prompt}")

    if r.filters.countries:
        click.echo(f"Countries:  {', '.join(r.filters.countries)}")
    if r.filters.industries:
        click.echo(f"Industries: {', '.join(r.filters.industries)}")

    if r.context.product:
        click.echo(f"Product:    {r.context.product}")
    if r.context.seller:
        click.echo(f"Seller:     {r.context.seller}")

    click.echo(f"Max results: {r.policy.max_results or 'unlimited'}")

    if r.description:
        click.echo(f"\nDescription: {r.description}")


@recipe.command("create")
@click.option("--slug", "-s", required=True, help="Unique identifier for the recipe")
@click.option("--prompt", "-p", required=True, help="Search prompt")
@click.option(
    "--use-case",
    "-u",
    type=click.Choice(["leads", "talent"]),
    default="leads",
    help="Use case type",
)
@click.option("--name", "-n", default="", help="Human-readable name")
@click.option("--country", multiple=True, help="Country filter (can specify multiple)")
@click.option("--industry", multiple=True, help="Industry filter (can specify multiple)")
@click.option("--product-context", default="", help="Product context for advice")
@click.option("--seller-context", default="", help="Seller context for advice")
@click.option("--max-results", type=int, default=50, help="Max results (0 for unlimited)")
def recipe_create(
    slug: str,
    prompt: str,
    use_case: str,
    name: str,
    country: tuple[str, ...],
    industry: tuple[str, ...],
    product_context: str,
    seller_context: str,
    max_results: int,
) -> None:
    """Create a new recipe."""
    from .recipe import create_recipe_from_prompt, load_recipe, save_recipe

    # Check if already exists
    try:
        load_recipe(slug)
        click.echo(f"Recipe already exists: {slug}", err=True)
        click.echo("Use a different slug or delete the existing recipe first.", err=True)
        sys.exit(1)
    except FileNotFoundError:
        pass  # Good, doesn't exist yet

    max_results_opt = max_results if max_results > 0 else None

    recipe_obj = create_recipe_from_prompt(
        slug=slug,
        prompt=prompt,
        use_case=use_case,  # type: ignore
        name=name,
        countries=list(country),
        industries=list(industry),
        product_context=product_context,
        seller_context=seller_context,
        max_results=max_results_opt,
    )

    path = save_recipe(recipe_obj)
    click.echo(f"Recipe saved: {path}")
    click.echo(f"\nRun with: shoudao recipe run {slug}")


@recipe.command("run")
@click.argument("slug")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="runs",
    help="Output directory (default: runs/)",
)
def recipe_run(slug: str, output: str) -> None:
    """Run a saved recipe."""
    from .pipeline import run_pipeline, run_talent_pipeline
    from .recipe import load_recipe

    try:
        r = load_recipe(slug)
    except FileNotFoundError:
        click.echo(f"Recipe not found: {slug}", err=True)
        click.echo("Use 'shoudao recipe list' to see available recipes.", err=True)
        sys.exit(1)

    output_dir = Path(output)

    click.echo(f"[ShouDao] Running recipe: {r.name or r.slug}")
    click.echo(f"[ShouDao] Use case: {r.use_case}")
    click.echo(f"[ShouDao] Prompt: {r.prompt[:80]}...")

    try:
        if r.use_case == "talent":
            result = run_talent_pipeline(
                prompt=r.prompt,
                output_dir=output_dir,
                max_results=r.policy.max_results,
            )
            click.echo(f"\nFound {len(result.candidates)} candidates")
            click.echo(f"  Tier A: {result.tier_a_count}")
            click.echo(f"  Tier B: {result.tier_b_count}")
            click.echo(f"  Tier C: {result.tier_c_count}")
        else:
            result = run_pipeline(
                prompt=r.prompt,
                countries=r.filters.countries,
                industries=r.filters.industries,
                max_results=r.policy.max_results,
                output_dir=output_dir,
                product_context=r.context.product,
                seller_context=r.context.seller,
                seed_sources=r.policy.seed_sources,
            )
            click.echo(f"\nGenerated {len(result.leads)} leads")

        if result.errors:
            click.echo(f"Warnings: {len(result.errors)}")

    except Exception as e:
        click.echo(f"Pipeline error: {e}", err=True)
        sys.exit(1)


@recipe.command("delete")
@click.argument("slug")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def recipe_delete(slug: str, yes: bool) -> None:
    """Delete a recipe."""
    from .recipe import delete_recipe, load_recipe

    try:
        r = load_recipe(slug)
    except FileNotFoundError:
        click.echo(f"Recipe not found: {slug}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"Delete recipe '{r.name or r.slug}'?", abort=True)

    if delete_recipe(slug):
        click.echo(f"Deleted: {slug}")
    else:
        click.echo(f"Failed to delete: {slug}", err=True)
        sys.exit(1)


@main.command()
@click.argument("run_id")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="runs",
    help="Output directory for new run artifacts (default: runs/)",
)
@click.option(
    "--enrich/--no-enrich",
    default=True,
    help="Run GitHub enrichment (default: enabled)",
)
def reprocess(run_id: str, output: str, enrich: bool) -> None:
    """Re-process candidates from a previous run with updated scoring.

    RUN_ID is the folder name of the previous run (e.g., 20251230_122435_talent_cccf09)
    """
    import json
    import uuid
    from datetime import UTC, datetime

    from .dedupe import score_all_candidates
    from .exporter import (
        export_candidates_csv,
        export_candidates_excel,
        export_candidates_json,
        generate_talent_report,
    )
    from .github import get_github_provider
    from .models import Candidate, TalentRunResult

    output_dir = Path(output)
    source_dir = output_dir / run_id

    # Load candidates from previous run
    candidates_file = source_dir / "candidates.json"
    if not candidates_file.exists():
        click.echo(f"Cannot find {candidates_file}", err=True)
        sys.exit(1)

    click.echo(f"[Reprocess] Loading candidates from {run_id}")
    with open(candidates_file, encoding="utf-8") as f:
        data = json.load(f)

    # Clean data to handle old runs with invalid values
    candidates = []
    for c in data:
        # Cap years_experience to realistic max for Gauntlet target demo
        # 20 years = started at 22, now 42 (mature band, still reasonable)
        # Anything higher is likely bad LinkedIn parsing
        if c.get("years_experience") and c["years_experience"] > 20:
            c["years_experience"] = min(c["years_experience"], 20)
        # Clear estimated_age so it gets re-calculated from capped YOE
        if c.get("estimated_age") and c["estimated_age"] > 42:
            c["estimated_age"] = None  # Will be re-estimated from YOE
        try:
            candidates.append(Candidate(**c))
        except Exception as e:
            click.echo(f"  Warning: Skipping invalid candidate: {e}", err=True)

    click.echo(f"  Loaded {len(candidates)} candidates")

    # GitHub enrichment
    if enrich:
        provider = get_github_provider()
        if provider.is_authenticated():
            click.echo(f"[GitHub] Enriching {len(candidates)} candidates...")
            enriched_count = 0
            for i, candidate in enumerate(candidates):
                name = candidate.name
                if not name or name == "Unknown":
                    continue

                click.echo(f"  [{i + 1}/{len(candidates)}] {name}...", nl=False)

                # Skip if already has GitHub
                if candidate.github_url:
                    click.echo(" (already has GitHub)")
                    continue

                username = provider.search_user(name)
                if username:
                    profile = provider.get_user(username)
                    if profile:
                        # Verify name match (loose)
                        profile_name = (profile.name or "").lower()
                        candidate_name = name.lower()
                        if any(part in profile_name for part in candidate_name.split()[:2]):
                            profile = provider.enrich_profile(profile)
                            candidate.github_url = profile.html_url
                            candidate.public_repos = [r.html_url for r in profile.repos[:5]]
                            candidate.ai_signal_score = provider.calculate_ai_signal_score(profile)
                            candidate.build_in_public_score = (
                                provider.calculate_build_in_public_score(profile)
                            )
                            if profile.twitter_username:
                                candidate.twitter_url = (
                                    f"https://twitter.com/{profile.twitter_username}"
                                )
                            enriched_count += 1
                            click.echo(f" -> {username} ({len(profile.ai_repos)} AI repos)")
                        else:
                            click.echo(" (name mismatch)")
                    else:
                        click.echo(" (profile fetch failed)")
                else:
                    click.echo(" (not found)")

            click.echo(f"  Enriched {enriched_count}/{len(candidates)} candidates")
        else:
            click.echo("[GitHub] Not configured (GITHUB_TOKEN not set), skipping enrichment")

    # Re-score all candidates with new scoring logic
    click.echo("[Scoring] Applying updated scoring...")
    candidates = score_all_candidates(candidates)

    # Count tiers
    tier_a = sum(1 for c in candidates if c.overall_fit_tier == "A")
    tier_b = sum(1 for c in candidates if c.overall_fit_tier == "B")
    tier_c = sum(1 for c in candidates if c.overall_fit_tier == "C")
    click.echo(f"  Tier distribution: A={tier_a}, B={tier_b}, C={tier_c}")

    # Create new run folder
    new_run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_reprocess_" + uuid.uuid4().hex[:6]
    new_run_dir = output_dir / new_run_id
    new_run_dir.mkdir(parents=True, exist_ok=True)

    # Export
    csv_path = new_run_dir / "candidates.csv"
    json_path = new_run_dir / "candidates.json"
    excel_path = new_run_dir / "candidates.xlsx"
    report_path = new_run_dir / "report.md"

    export_candidates_csv(candidates, csv_path)
    export_candidates_json(candidates, json_path)
    export_candidates_excel(candidates, excel_path)

    # Create result for report
    result = TalentRunResult(
        run_id=new_run_id,
        prompt=f"Reprocessed from {run_id}",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        sources_fetched=len(candidates),
        total_candidates_extracted=len(candidates),
        total_candidates_after_dedupe=len(candidates),
        contactable_candidates=len(candidates),
        tier_a_count=tier_a,
        tier_b_count=tier_b,
        tier_c_count=tier_c,
        candidates=candidates,
    )
    generate_talent_report(result, report_path)

    click.echo("\n[Reprocess] Complete!")
    click.echo(f"  Output: {new_run_dir}")
    click.echo(f"  CSV: {csv_path}")
    click.echo(f"  Excel: {excel_path}")
    click.echo(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
