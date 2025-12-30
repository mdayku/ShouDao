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
    output: str,
    max_results: int,
    country: tuple[str, ...],
    industry: tuple[str, ...],
    product_context: str,
    seller_context: str,
) -> None:
    """Run a lead generation query."""
    from .pipeline import run_pipeline

    output_dir = Path(output)

    try:
        result = run_pipeline(
            prompt=prompt,
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


if __name__ == "__main__":
    main()
