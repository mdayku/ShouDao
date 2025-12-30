"""
ShouDao pipeline - orchestrates the full prompt-to-CSV flow.
Now includes sources.json for audit trail.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from .advisor import Advisor
from .dedupe import (
    apply_buyer_gate,
    dedupe_all_contacts,
    dedupe_candidates,
    dedupe_leads,
    score_all_candidates,
    score_all_leads,
)
from .exporter import (
    export_candidates_csv,
    export_candidates_excel,
    export_candidates_json,
    export_csv,
    export_excel,
    export_json,
    generate_report,
    generate_talent_report,
)
from .extractor import Extractor, TalentExtractor
from .fetcher import Fetcher, FetcherConfig, dedupe_by_domain, filter_urls
from .logger import ProgressLogger
from .models import Candidate, Lead, RunConfig, RunResult, TalentRunResult
from .search import expand_prompt_to_queries, expand_talent_queries, get_search_provider
from .sources import SourcesLog


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(self, config: RunConfig, verbose: bool = False):
        self.config = config
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.logger = ProgressLogger(self.run_id, verbose=verbose)

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

        self.logger.phase("Starting run", f"ID={self.run_id}")
        if len(self.config.prompt) > 100:
            print(f"  Prompt: {self.config.prompt[:100]}...")
        else:
            print(f"  Prompt: {self.config.prompt}")

        # Step 1: Expand prompt to queries
        self.logger.phase("Query expansion", "Step 1/6")
        filters_dict = {
            "countries": self.config.countries,
            "industries": self.config.industries,
        }
        queries = expand_prompt_to_queries(self.config.prompt, filters_dict)
        print(f"  Generated {len(queries)} search queries")

        # Step 2: Search for URLs
        self.logger.phase("Searching for sources", "Step 2/6")
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
        self.logger.phase("Fetching pages", f"Step 3/6 - {len(all_urls)} URLs")
        fetcher = Fetcher(FetcherConfig(delay_between_requests=1.5))
        fetch_results = fetcher.fetch_many(all_urls[:100])  # Cap at 100 for 100+ lead runs

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
        self.logger.phase("Extracting leads", f"Step 4/6 - {len(successful)} pages")
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

        # Step 5: Dedupe, filter, and score
        self.logger.phase("Deduplication and scoring", f"Step 5/6 - {len(all_leads)} raw leads")
        leads = dedupe_leads(all_leads)
        leads = dedupe_all_contacts(leads)  # Task 7.1.3: dedupe contacts by email
        pre_filter_count = len(leads)

        # Apply buyer-only gate (drops exporters, flags unknowns)
        leads = apply_buyer_gate(leads)
        leads = score_all_leads(leads)

        result.total_leads_after_dedupe = len(leads)
        filtered_count = pre_filter_count - len(leads)
        print(f"  Leads after dedupe: {pre_filter_count}")
        print(f"  Leads after buyer gate: {len(leads)} (dropped {filtered_count} non-buyers)")

        # Step 6: Generate advice
        self.logger.phase("Generating advice", f"Step 6/6 - {len(leads)} leads")
        advisor = Advisor()
        leads = advisor.advise_all(
            leads,
            product_context=self.config.product_context,
            seller_context=self.config.seller_context,
        )
        print(f"  Advice generated for {len(leads)} leads")

        # Cap at max_results (if configured), sorted by confidence
        leads = sorted(leads, key=lambda lead: -lead.confidence)
        if self.config.max_results is not None:
            leads = leads[: self.config.max_results]

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
            export_excel(leads, run_dir / "leads.xlsx")
            export_json(leads, json_path)
            generate_report(result, report_path)
            sources_log.save(sources_path)

            self.logger.finish(len(leads), str(run_dir))
            print(f"  CSV: {csv_path}")
            print(f"  Sources: {sources_path}")

        return result


def run_pipeline(
    prompt: str,
    countries: list[str] | None = None,
    industries: list[str] | None = None,
    seed_sources: list[str] | None = None,
    max_results: int | None = 50,
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


# =============================================================================
# TALENT DISCOVERY PIPELINE (Gauntlet Cohort 4)
# =============================================================================


class TalentPipeline:
    """Talent discovery pipeline for finding Gauntlet candidates."""

    def __init__(
        self,
        prompt: str,
        verbose: bool = False,
        use_linkedin: bool = False,
        linkedin_mode: str = "Full",
        locations: list[str] | None = None,
        enrich_github: bool = False,
    ):
        self.prompt = prompt
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_talent_" + uuid.uuid4().hex[:6]
        self.logger = ProgressLogger(self.run_id, verbose=verbose)
        self.use_linkedin = use_linkedin
        self.linkedin_mode = linkedin_mode
        self.locations = locations
        self.enrich_github = enrich_github

    def _enrich_with_github(
        self, candidates: list[Candidate], result: TalentRunResult
    ) -> list[Candidate]:
        """Enrich candidates with GitHub data."""
        from .github import get_github_provider

        provider = get_github_provider()
        self.logger.phase("GitHub enrichment", f"Step 5/6 - {len(candidates)} candidates")

        if provider.is_authenticated():
            print("  [GitHub] Using authenticated API (5000 req/hr)")
        else:
            print("  [GitHub] Using unauthenticated API (60 req/hr)")
            print("  [GitHub] Set GITHUB_TOKEN in .env for higher limits")

        enriched_count = 0
        for i, candidate in enumerate(candidates):
            # Skip if we already have a GitHub URL
            if candidate.github_url:
                # Just fetch repos for existing URL
                username = candidate.github_url.rstrip("/").split("/")[-1]
                profile = provider.get_user(username)
                if profile:
                    profile = provider.enrich_profile(profile)
                    self._apply_github_signals(candidate, profile)
                    enriched_count += 1
                continue

            # Search for GitHub by name
            name = candidate.name
            if not name or name == "Unknown":
                continue

            print(f"    [{i + 1}/{len(candidates)}] Searching GitHub for: {name}")
            username = provider.search_user(name)

            if username:
                profile = provider.get_user(username)
                if profile:
                    profile = provider.enrich_profile(profile)

                    # Verify it's likely the same person (check for name match)
                    if profile.name and self._names_match(name, profile.name):
                        candidate.github_url = profile.html_url
                        self._apply_github_signals(candidate, profile)
                        enriched_count += 1
                        print(f"      Found: {profile.html_url} ({len(profile.ai_repos)} AI repos)")
                    else:
                        print(f"      Found {username} but name mismatch, skipping")
            else:
                print("      Not found")

        print(f"  [GitHub] Enriched {enriched_count}/{len(candidates)} candidates")
        return candidates

    def _apply_github_signals(self, candidate: Candidate, profile) -> None:
        """Apply GitHub signals to a candidate."""
        from .github import GitHubProfile

        if not isinstance(profile, GitHubProfile):
            return

        # Update GitHub URL
        if not candidate.github_url:
            candidate.github_url = profile.html_url

        # Update Twitter if found
        if profile.twitter_username and not candidate.twitter_url:
            candidate.twitter_url = f"https://twitter.com/{profile.twitter_username}"

        # Update website if found
        if profile.blog and not candidate.website_url:
            candidate.website_url = profile.blog

        # Update email if found and not already set
        if profile.email and not candidate.email:
            candidate.email = profile.email

        # Add public repos
        for repo in profile.ai_repos[:5]:  # Top 5 AI repos
            if repo.html_url not in candidate.public_repos:
                candidate.public_repos.append(repo.html_url)

        # Calculate scores
        from .github import get_github_provider

        provider = get_github_provider()
        candidate.ai_signal_score = max(
            candidate.ai_signal_score,
            provider.calculate_ai_signal_score(profile),
        )
        candidate.build_in_public_score = max(
            candidate.build_in_public_score,
            provider.calculate_build_in_public_score(profile),
        )

    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two names are likely the same person."""
        # Simple check: first name matches
        parts1 = name1.lower().split()
        parts2 = name2.lower().split()

        if not parts1 or not parts2:
            return False

        # First name match
        if parts1[0] == parts2[0]:
            return True

        # Last name match
        if len(parts1) > 1 and len(parts2) > 1:
            if parts1[-1] == parts2[-1]:
                return True

        return False

    def _run_linkedin_source(
        self, max_results: int | None, result: TalentRunResult
    ) -> list[Candidate]:
        """Source candidates from LinkedIn via Apify."""
        from .linkedin import get_linkedin_provider, linkedin_profile_to_candidate

        provider = get_linkedin_provider()
        if not provider:
            result.errors.append("LinkedIn not configured (APIFY_API_KEY not set)")
            print("  ERROR: LinkedIn not configured")
            return []

        self.logger.phase("Searching LinkedIn", "Step 2/5")
        profiles = provider.search_profiles(
            self.prompt,
            max_results=max_results or 25,
            scraper_mode=self.linkedin_mode,
            locations=self.locations,
            profile_language="en",  # Default to English profiles
        )

        print(f"  Found {len(profiles)} LinkedIn profiles")
        result.sources_fetched = len(profiles)

        # Convert profiles to candidates
        self.logger.phase("Converting profiles to candidates", "Step 3/5")
        candidates = []
        for profile in profiles:
            try:
                candidate = linkedin_profile_to_candidate(profile)
                candidates.append(candidate)
                print(f"    Converted: {profile.name or 'Unknown'}")
            except Exception as e:
                import traceback

                tb = traceback.format_exc()
                result.errors.append(f"Profile conversion error ({profile.name}): {e}")
                print(f"    ERROR converting {profile.name}:")
                # Print just the last 5 lines of traceback
                tb_lines = tb.strip().split("\n")
                for line in tb_lines[-5:]:
                    print(f"      {line}")

        return candidates

    def _run_web_source(
        self, max_results: int | None, filters: dict | None, result: TalentRunResult
    ) -> list[Candidate]:
        """Source candidates from web search."""
        # Step 1: Generate talent queries
        self.logger.phase("Query expansion", "Step 1/5")
        queries = expand_talent_queries(self.prompt, filters)
        print(f"  Generated {len(queries)} talent discovery queries")

        # Step 2: Search for URLs
        self.logger.phase("Searching for sources", "Step 2/5")
        # Use Serper for now (could add GitHub API later)
        config = RunConfig(prompt=self.prompt, search_provider="serper")
        search_provider = get_search_provider(config)

        all_urls = []
        for query in queries:
            try:
                urls = search_provider.search(query, num_results=10)
                all_urls.extend(urls)
                print(f"  Query returned {len(urls)} URLs")
            except Exception as e:
                result.errors.append(f"Search error: {e}")
                print(f"  Search error: {e}")

        # Filter and dedupe URLs
        all_urls = filter_urls(all_urls)
        all_urls = dedupe_by_domain(list(set(all_urls)), max_per_domain=3)
        print(f"  Total unique URLs after filtering: {len(all_urls)}")

        # Step 3: Fetch pages
        self.logger.phase("Fetching pages", f"Step 3/5 - {len(all_urls)} URLs")
        fetcher = Fetcher(FetcherConfig(delay_between_requests=1.0))
        fetch_results = fetcher.fetch_many(all_urls[:150])  # Higher cap for talent

        successful = [fr for fr in fetch_results if fr.success]
        result.sources_fetched = len(successful)
        print(f"  Fetched {len(successful)}/{len(all_urls)} pages")

        # Step 4: Extract candidates
        self.logger.phase("Extracting candidates", f"Step 4/5 - {len(successful)} pages")
        extractor = TalentExtractor()
        all_candidates: list[Candidate] = []

        for fetch_result in successful:
            try:
                extraction = extractor.extract(fetch_result)
                candidates = extractor.extraction_to_candidates(extraction, fetch_result.url)
                all_candidates.extend(candidates)

                if candidates:
                    print(f"  Found {len(candidates)} candidate(s) from {fetch_result.url[:60]}...")
            except Exception as e:
                result.errors.append(f"Extraction error: {e}")
                print(f"  Extraction error: {e}")

        return all_candidates

    def run(
        self,
        output_dir: Path | None = None,
        max_results: int | None = None,
        filters: dict | None = None,
    ) -> TalentRunResult:
        """Execute the talent discovery pipeline."""
        result = TalentRunResult(
            run_id=self.run_id,
            prompt=self.prompt,
            started_at=datetime.now(UTC),
        )

        source_type = "LinkedIn" if self.use_linkedin else "Web"
        self.logger.phase("Starting talent discovery", f"ID={self.run_id} Source={source_type}")
        print(
            f"  Prompt: {self.prompt[:100]}..."
            if len(self.prompt) > 100
            else f"  Prompt: {self.prompt}"
        )
        print(f"  Source: {source_type}")

        # Source candidates based on configuration
        if self.use_linkedin:
            all_candidates = self._run_linkedin_source(max_results, result)
        else:
            all_candidates = self._run_web_source(max_results, filters, result)

        result.total_candidates_extracted = len(all_candidates)
        print(f"  Total raw candidates: {len(all_candidates)}")

        # Step 5: Enrich with GitHub data (if enabled)
        if self.enrich_github and all_candidates:
            all_candidates = self._enrich_with_github(all_candidates, result)

        # Step 6: Dedupe, score, and classify
        self.logger.phase(
            "Scoring and classification", f"Step 6/6 - {len(all_candidates)} candidates"
        )
        candidates = dedupe_candidates(all_candidates)
        candidates = score_all_candidates(candidates)

        # Filter to only contactable candidates
        candidates = [c for c in candidates if c.is_contactable()]
        result.contactable_candidates = len(candidates)

        # Sort by confidence and apply max_results
        candidates = sorted(candidates, key=lambda c: -c.confidence)
        if max_results is not None:
            candidates = candidates[:max_results]

        # Count tiers
        result.tier_a_count = sum(1 for c in candidates if c.overall_fit_tier == "A")
        result.tier_b_count = sum(1 for c in candidates if c.overall_fit_tier == "B")
        result.tier_c_count = sum(1 for c in candidates if c.overall_fit_tier == "C")

        print(
            f"  Tier distribution: A={result.tier_a_count}, B={result.tier_b_count}, C={result.tier_c_count}"
        )

        result.candidates = candidates
        result.total_candidates_after_dedupe = len(candidates)
        result.finished_at = datetime.now(UTC)

        # Export outputs
        if output_dir:
            run_dir = output_dir / self.run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            csv_path = run_dir / "candidates.csv"
            json_path = run_dir / "candidates.json"
            report_path = run_dir / "report.md"

            export_candidates_csv(candidates, csv_path)
            export_candidates_excel(candidates, run_dir / "candidates.xlsx")
            export_candidates_json(candidates, json_path)
            generate_talent_report(result, report_path)

            self.logger.finish(len(candidates), str(run_dir))
            print(f"  CSV: {csv_path}")
            print(f"  Report: {report_path}")

        return result


def run_talent_pipeline(
    prompt: str,
    output_dir: Path | None = None,
    max_results: int | None = None,
    filters: dict | None = None,
    use_linkedin: bool = False,
    linkedin_mode: str = "Full",
    locations: list[str] | None = None,
    enrich_github: bool = False,
) -> TalentRunResult:
    """Convenience function to run a talent discovery pipeline."""
    pipeline = TalentPipeline(
        prompt,
        use_linkedin=use_linkedin,
        linkedin_mode=linkedin_mode,
        locations=locations,
        enrich_github=enrich_github,
    )
    return pipeline.run(output_dir=output_dir, max_results=max_results, filters=filters)
