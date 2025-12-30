"""
ShouDao pipeline - orchestrates the full prompt-to-CSV flow.
Now includes sources.json for audit trail.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from .advisor import Advisor
from .dedupe import dedupe_leads, score_all_leads
from .exporter import export_csv, export_json, generate_report
from .extractor import Extractor
from .fetcher import Fetcher, FetcherConfig, dedupe_by_domain, filter_urls
from .models import Lead, RunConfig, RunResult
from .search import expand_prompt_to_queries, get_search_provider
from .sources import SourcesLog


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(self, config: RunConfig):
        self.config = config
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

    def run(self, output_dir: Path | None = None) -> RunResult:
        """Execute the full pipeline."""
        result = RunResult(
            config=self.config,
            run_id=self.run_id,
            started_at=datetime.now(UTC),
        )

        # Initialize sources log for audit trail
        sources_log = SourcesLog(
            run_id=self.run_id,
            prompt=self.config.prompt,
        )

        print(f"[ShouDao] Starting run: {self.run_id}")
        print(f"[ShouDao] Prompt: {self.config.prompt}")

        # Step 1: Expand prompt to queries
        print("[ShouDao] Step 1/6: Expanding prompt to queries...")
        filters_dict = {
            "countries": self.config.countries,
            "industries": self.config.industries,
        }
        queries = expand_prompt_to_queries(self.config.prompt, filters_dict)
        print(f"  Generated {len(queries)} search queries")

        # Step 2: Search for URLs
        print("[ShouDao] Step 2/6: Searching for sources...")
        search_provider = get_search_provider(self.config)
        provider_name = self.config.search_provider
        all_urls = []
        query_url_map: dict[str, list[str]] = {}  # Track which query found each URL

        for query in queries:
            try:
                urls = search_provider.search(query, num_results=10)
                sources_log.add_query(query, provider_name, urls)
                for url in urls:
                    query_url_map[url] = query_url_map.get(url, query)  # Keep first query
                all_urls.extend(urls)
                print(f"  Query returned {len(urls)} URLs")
            except Exception as e:
                result.errors.append(f"Search error: {e}")
                print(f"  Search error: {e}")

        result.total_urls_searched = len(all_urls)

        # Filter and dedupe URLs
        all_urls_before_filter = set(all_urls)
        all_urls = filter_urls(all_urls)
        all_urls = dedupe_by_domain(list(set(all_urls)), max_per_domain=2)

        # Track filtered URLs
        filtered_out = all_urls_before_filter - set(all_urls)
        for url in filtered_out:
            sources_log.add_filtered_url(url)

        print(f"  Total unique URLs after filtering: {len(all_urls)}")

        # Step 3: Fetch pages
        print("[ShouDao] Step 3/6: Fetching pages...")
        fetcher = Fetcher(FetcherConfig(delay_between_requests=1.5))
        fetch_results = fetcher.fetch_many(all_urls[:30])  # Cap at 30 for MVP

        successful = []
        for fr in fetch_results:
            source_query = query_url_map.get(fr.url, "")
            if fr.success:
                sources_log.add_fetch_result(
                    url=fr.url,
                    source_query=source_query,
                    success=True,
                    status_code=fr.status_code,
                    content_length=len(fr.text),
                )
                successful.append(fr)
            else:
                sources_log.add_fetch_result(
                    url=fr.url,
                    source_query=source_query,
                    success=False,
                    error=fr.error,
                )

        result.sources_fetched = len(successful)
        result.domains_hit = len(set(r.url.split("/")[2] for r in successful))
        print(f"  Fetched {len(successful)}/{len(all_urls)} pages")

        # Step 4: Extract leads
        print("[ShouDao] Step 4/6: Extracting leads...")
        extractor = Extractor()
        all_leads: list[Lead] = []

        for fetch_result in successful:
            try:
                extraction = extractor.extract(fetch_result, self.config.prompt)
                leads = extractor.extraction_to_leads(extraction, fetch_result.url)
                all_leads.extend(leads)

                # Update sources log with extraction count
                for url_rec in sources_log.urls_fetched:
                    if url_rec.url == fetch_result.url:
                        url_rec.leads_extracted = len(leads)
                        break

                if leads:
                    print(f"  Found {len(leads)} lead(s) from {fetch_result.url[:60]}...")
            except Exception as e:
                result.errors.append(f"Extraction error: {e}")
                print(f"  Extraction error: {e}")

        result.total_leads_extracted = len(all_leads)
        print(f"  Total raw leads: {len(all_leads)}")

        # Step 5: Dedupe and score
        print("[ShouDao] Step 5/6: Deduplicating and scoring...")
        leads = dedupe_leads(all_leads)
        leads = score_all_leads(leads)
        result.total_leads_after_dedupe = len(leads)
        print(f"  Leads after dedupe: {len(leads)}")

        # Step 6: Generate advice
        print("[ShouDao] Step 6/6: Generating outreach advice...")
        advisor = Advisor()
        leads = advisor.advise_all(
            leads,
            product_context=self.config.product_context,
            seller_context=self.config.seller_context,
        )
        print(f"  Advice generated for {len(leads)} leads")

        # Cap at max_results, sorted by confidence
        leads = sorted(leads, key=lambda lead: -lead.confidence)[: self.config.max_results]

        result.leads = leads
        result.finished_at = datetime.now(UTC)
        sources_log.finish()

        # Export outputs
        if output_dir:
            run_dir = output_dir / self.run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            csv_path = run_dir / "leads.csv"
            json_path = run_dir / "leads.json"
            report_path = run_dir / "report.md"
            sources_path = run_dir / "sources.json"

            export_csv(leads, csv_path)
            export_json(leads, json_path)
            generate_report(result, report_path)
            sources_log.save(sources_path)

            print("\n[ShouDao] Run complete!")
            print(f"  Output: {run_dir}")
            print(f"  Leads: {len(leads)}")
            print(f"  CSV: {csv_path}")
            print(f"  Sources: {sources_path}")

        return result


def run_pipeline(
    prompt: str,
    countries: list[str] | None = None,
    industries: list[str] | None = None,
    seed_sources: list[str] | None = None,
    max_results: int = 50,
    output_dir: Path | None = None,
    product_context: str = "",
    seller_context: str = "",
) -> RunResult:
    """Convenience function to run a pipeline."""
    config = RunConfig(
        prompt=prompt,
        countries=countries or [],
        industries=industries or [],
        seed_sources=seed_sources or [],
        max_results=max_results,
        product_context=product_context,
        seller_context=seller_context,
    )
    pipeline = Pipeline(config)
    return pipeline.run(output_dir=output_dir)
