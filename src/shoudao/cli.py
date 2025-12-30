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
    help="Maximum number of leads to return (default: 50)",
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
            max_results=max_results,
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

    if openai_key:
        click.echo(f"  OPENAI_API_KEY: {openai_key[:8]}...{openai_key[-4:]}")
    else:
        click.echo("  OPENAI_API_KEY: NOT SET (required)")

    if serper_key:
        click.echo(f"  SERPER_API_KEY: {serper_key[:8]}...{serper_key[-4:]}")
    else:
        click.echo("  SERPER_API_KEY: NOT SET (required for search)")

    if openai_key and serper_key:
        click.echo("\nAll required keys are set. Ready to run!")
    else:
        click.echo("\nMissing keys. Copy env.example to .env and fill in your values.")
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


if __name__ == "__main__":
    main()
