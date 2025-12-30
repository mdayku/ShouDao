"""
LinkedIn integration via Apify actors.

Provides profile search and enrichment for talent discovery.
"""

import os
from dataclasses import dataclass

from pydantic import BaseModel


class LinkedInProfile(BaseModel):
    """Normalized LinkedIn profile data."""

    url: str
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    current_company: str | None = None
    current_title: str | None = None

    # Education
    school: str | None = None
    degree: str | None = None
    field_of_study: str | None = None

    # Experience
    years_experience: int | None = None
    experience_summary: str | None = None

    # Contact
    email: str | None = None
    twitter: str | None = None
    website: str | None = None

    # Raw data for debugging
    raw_data: dict | None = None


@dataclass
class LinkedInConfig:
    """Configuration for LinkedIn provider."""

    api_key: str
    # Actor IDs from Apify marketplace
    # Format: "username/actor-name" or raw actor ID like "M2FMdjRVeF1HPGFcc"
    # Can be overridden via environment variables
    profile_scraper_actor: str = ""  # Set via APIFY_LINKEDIN_PROFILE_ACTOR
    search_actor: str = ""  # Set via APIFY_LINKEDIN_SEARCH_ACTOR
    max_results_per_search: int = 50
    timeout_secs: int = 300


class LinkedInProvider:
    """
    LinkedIn data provider using Apify actors.

    Usage:
        provider = LinkedInProvider.from_env()

        # Search for profiles
        profiles = provider.search_profiles("software engineer AI")

        # Scrape specific profile
        profile = provider.scrape_profile("https://linkedin.com/in/someone")
    """

    def __init__(self, config: LinkedInConfig):
        self.config = config
        self._client = None

    @classmethod
    def from_env(cls) -> "LinkedInProvider":
        """Create provider from environment variables.

        Required:
            APIFY_API_KEY: Your Apify API token

        Optional (for actor configuration):
            APIFY_LINKEDIN_SEARCH_ACTOR: Actor for profile search
            APIFY_LINKEDIN_PROFILE_ACTOR: Actor for profile scraping
        """
        api_key = os.getenv("APIFY_API_KEY")
        if not api_key:
            raise ValueError("APIFY_API_KEY not set in environment")

        # Get actor IDs from env, with sensible defaults
        # These can be actor names ("username/actor-name") or raw IDs
        search_actor = os.getenv(
            "APIFY_LINKEDIN_SEARCH_ACTOR",
            "harvestapi/linkedin-profile-search",  # Default search actor
        )
        profile_actor = os.getenv(
            "APIFY_LINKEDIN_PROFILE_ACTOR",
            "harvestapi/linkedin-profile-scraper",  # Default profile actor
        )

        config = LinkedInConfig(
            api_key=api_key,
            search_actor=search_actor,
            profile_scraper_actor=profile_actor,
        )
        return cls(config)

    @property
    def client(self):
        """Lazy-load Apify client."""
        if self._client is None:
            try:
                from apify_client import ApifyClient

                self._client = ApifyClient(self.config.api_key)
            except ImportError as e:
                raise ImportError(
                    "apify-client not installed. Run: pip install apify-client"
                ) from e
        return self._client

    def search_profiles(
        self,
        keywords: str,
        max_results: int | None = None,
        job_titles: list[str] | None = None,
        locations: list[str] | None = None,
        scraper_mode: str = "Short",
    ) -> list[LinkedInProfile]:
        """
        Search LinkedIn for profiles matching keywords/filters.

        Args:
            keywords: General search query (e.g., "software engineer AI")
            max_results: Max profiles to return (default: config value)
            job_titles: List of current job titles to filter by
            locations: List of locations to filter by
            scraper_mode: "Short" (basic), "Full" (detailed), "Full + email search"

        Returns:
            List of LinkedInProfile objects
        """
        max_results = max_results or self.config.max_results_per_search

        print(f"[LinkedIn] Searching: {keywords[:50]}...")
        print(f"[LinkedIn] Mode: {scraper_mode}, Max: {max_results}")

        # Build input for HarvestAPI actor
        # See: https://apify.com/harvestapi/linkedin-profile-search
        run_input: dict = {
            "profileScraperMode": scraper_mode,
            "maxItems": max_results,
        }

        # Add search query if provided
        if keywords:
            run_input["searchQuery"] = keywords

        # Add job title filter if provided
        if job_titles:
            run_input["currentJobTitles"] = job_titles

        # Add location filter if provided
        if locations:
            run_input["locations"] = locations

        try:
            run = self.client.actor(self.config.search_actor).call(
                run_input=run_input,
                timeout_secs=self.config.timeout_secs,
            )

            profiles = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                profile = self._parse_search_result(item)
                if profile:
                    profiles.append(profile)

            print(f"[LinkedIn] Found {len(profiles)} profiles")
            return profiles

        except Exception as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                print(f"[LinkedIn] Actor not found: {self.config.search_actor}")
                print("[LinkedIn] Set APIFY_LINKEDIN_SEARCH_ACTOR in .env to your actor ID")
                print("[LinkedIn] Find actors at: https://apify.com/store?search=linkedin")
            else:
                print(f"[LinkedIn] Search error: {e}")
            return []

    def scrape_profile(self, linkedin_url: str) -> LinkedInProfile | None:
        """
        Scrape detailed data from a specific LinkedIn profile.

        Args:
            linkedin_url: Full LinkedIn profile URL

        Returns:
            LinkedInProfile with detailed data, or None on error
        """
        print(f"[LinkedIn] Scraping: {linkedin_url[:60]}...")

        try:
            run = self.client.actor(self.config.profile_scraper_actor).call(
                run_input={
                    "profileUrls": [linkedin_url],
                },
                timeout_secs=self.config.timeout_secs,
            )

            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                return self._parse_profile_data(item)

            return None

        except Exception as e:
            print(f"[LinkedIn] Scrape error: {e}")
            return None

    def scrape_profiles_batch(
        self,
        linkedin_urls: list[str],
    ) -> list[LinkedInProfile]:
        """
        Scrape multiple LinkedIn profiles in one batch.

        More efficient than individual calls for rate limits and cost.

        Args:
            linkedin_urls: List of LinkedIn profile URLs

        Returns:
            List of LinkedInProfile objects (may be fewer than input if errors)
        """
        if not linkedin_urls:
            return []

        print(f"[LinkedIn] Batch scraping {len(linkedin_urls)} profiles...")

        try:
            run = self.client.actor(self.config.profile_scraper_actor).call(
                run_input={
                    "profileUrls": linkedin_urls,
                },
                timeout_secs=self.config.timeout_secs * 2,  # More time for batch
            )

            profiles = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                profile = self._parse_profile_data(item)
                if profile:
                    profiles.append(profile)

            print(f"[LinkedIn] Scraped {len(profiles)} profiles")
            return profiles

        except Exception as e:
            print(f"[LinkedIn] Batch scrape error: {e}")
            return []

    def _parse_search_result(self, item: dict) -> LinkedInProfile | None:
        """Parse search result into LinkedInProfile (HarvestAPI format)."""
        try:
            url = item.get("linkedinUrl") or item.get("profileUrl") or item.get("url")
            if not url:
                return None

            # Parse name
            first_name = item.get("firstName", "")
            last_name = item.get("lastName", "")
            name = f"{first_name} {last_name}".strip() or item.get("name")

            # Parse location
            location_data = item.get("location", {})
            if isinstance(location_data, dict):
                location = location_data.get("linkedinText") or location_data.get("text")
            else:
                location = location_data

            # Parse current position
            current_positions = item.get("currentPosition", [])
            current_company = None
            current_title = None
            if current_positions and len(current_positions) > 0:
                pos = current_positions[0]
                current_company = pos.get("companyName")
                # Title might be in experience section

            # Try headline for title
            headline = item.get("headline")

            # Parse education
            education = item.get("education", []) or item.get("profileTopEducation", [])
            school = None
            degree = None
            field_of_study = None
            if education and len(education) > 0:
                edu = education[0]
                school = edu.get("schoolName")
                degree = edu.get("degree")
                field_of_study = edu.get("fieldOfStudy")

            # Parse experience for years
            experience = item.get("experience", [])
            years_exp = self._calculate_years_experience(experience)
            exp_summary = self._summarize_experience(experience)

            # Get current title from experience
            if experience and len(experience) > 0:
                current_title = experience[0].get("position") or experience[0].get("title")
                if not current_company:
                    current_company = experience[0].get("companyName")

            return LinkedInProfile(
                url=url,
                name=name,
                headline=headline,
                location=location,
                current_company=current_company,
                current_title=current_title,
                school=school,
                degree=degree,
                field_of_study=field_of_study,
                years_experience=years_exp,
                experience_summary=exp_summary,
                raw_data=item,
            )
        except Exception:
            return None

    def _parse_profile_data(self, item: dict) -> LinkedInProfile | None:
        """Parse detailed profile data into LinkedInProfile."""
        try:
            url = item.get("profileUrl") or item.get("url") or item.get("linkedinUrl")
            if not url:
                return None

            # Extract education (first/most recent)
            education = item.get("education", [])
            school = None
            degree = None
            field_of_study = None
            if education and len(education) > 0:
                edu = education[0]
                school = edu.get("schoolName") or edu.get("school")
                degree = edu.get("degree") or edu.get("degreeName")
                field_of_study = edu.get("fieldOfStudy") or edu.get("field")

            # Calculate years of experience
            experience = item.get("experience", []) or item.get("positions", [])
            years_exp = self._calculate_years_experience(experience)

            # Experience summary (current + 1-2 previous)
            exp_summary = self._summarize_experience(experience)

            # Extract contact info
            email = item.get("email") or item.get("emailAddress")
            twitter = item.get("twitter") or item.get("twitterUrl")
            website = item.get("website") or item.get("websiteUrl")

            return LinkedInProfile(
                url=url,
                name=item.get("name") or item.get("fullName"),
                headline=item.get("headline") or item.get("title"),
                location=item.get("location"),
                current_company=item.get("company") or item.get("currentCompany"),
                current_title=item.get("title") or item.get("currentTitle"),
                school=school,
                degree=degree,
                field_of_study=field_of_study,
                years_experience=years_exp,
                experience_summary=exp_summary,
                email=email,
                twitter=twitter,
                website=website,
                raw_data=item,
            )
        except Exception:
            return None

    def _calculate_years_experience(self, experience: list[dict]) -> int | None:
        """Estimate years of professional experience from positions."""
        if not experience:
            return None

        # Simple heuristic: count positions, assume avg 2 years each
        # More sophisticated: parse dates if available
        total_years = 0
        for pos in experience:
            # Try to get duration
            duration = pos.get("duration") or pos.get("durationInMonths")
            if isinstance(duration, int):
                total_years += duration / 12
            elif isinstance(duration, str) and "yr" in duration.lower():
                # Parse "2 yrs 3 mos" format
                try:
                    years = int(duration.split()[0])
                    total_years += years
                except (ValueError, IndexError):
                    total_years += 2  # Default estimate
            else:
                total_years += 2  # Default estimate per position

        return int(total_years) if total_years > 0 else None

    def _summarize_experience(self, experience: list[dict]) -> str | None:
        """Create brief experience summary."""
        if not experience:
            return None

        summaries = []
        for pos in experience[:3]:  # Top 3 positions
            title = pos.get("title") or pos.get("position")
            company = pos.get("companyName") or pos.get("company")
            if title and company:
                summaries.append(f"{title} at {company}")
            elif title:
                summaries.append(title)

        return "; ".join(summaries) if summaries else None


def check_linkedin_config() -> bool:
    """Check if LinkedIn/Apify is configured."""
    return bool(os.getenv("APIFY_API_KEY"))


def get_linkedin_provider() -> LinkedInProvider | None:
    """Get LinkedIn provider if configured, else None."""
    if not check_linkedin_config():
        return None
    try:
        return LinkedInProvider.from_env()
    except Exception as e:
        print(f"[LinkedIn] Could not initialize: {e}")
        return None


def linkedin_profile_to_candidate(profile: LinkedInProfile):
    """Convert a LinkedInProfile to a Candidate model.

    This enables LinkedIn sourced candidates to flow through the same
    pipeline as web-sourced candidates, including:
    - Scoring and tier classification
    - Deduplication
    - Export to JSON/CSV/Excel/Markdown

    Args:
        profile: LinkedInProfile from Apify scraping

    Returns:
        Candidate model ready for pipeline processing
    """
    from datetime import UTC, datetime

    from .models import AgeBand, Candidate, CandidateTier, Evidence, SalaryBand

    # Build degree signal from education
    degree_signal = None
    if profile.school:
        degree_parts = []
        if profile.degree:
            degree_parts.append(profile.degree)
        if profile.field_of_study:
            degree_parts.append(profile.field_of_study)
        degree_parts.append(profile.school)
        degree_signal = ", ".join(degree_parts)

    # Estimate salary band from experience and title
    salary_band = SalaryBand.UNKNOWN
    if profile.years_experience:
        if profile.years_experience >= 10:
            salary_band = SalaryBand.SENIOR
        elif profile.years_experience >= 5:
            salary_band = SalaryBand.MID
        elif profile.years_experience >= 2:
            salary_band = SalaryBand.JUNIOR
        else:
            salary_band = SalaryBand.ENTRY

    # Estimate age band from experience
    age_band = AgeBand.UNKNOWN
    if profile.years_experience:
        # Rough estimate: experience + 22 (college graduation age)
        estimated_age = profile.years_experience + 22
        if estimated_age < 25:
            age_band = AgeBand.YOUNG_PROFESSIONAL
        elif estimated_age < 35:
            age_band = AgeBand.EARLY_CAREER
        elif estimated_age < 45:
            age_band = AgeBand.MID_CAREER
        else:
            age_band = AgeBand.SENIOR

    # Create evidence from LinkedIn profile
    evidence = [
        Evidence(
            url=profile.url,
            snippet=profile.headline or f"{profile.name} - LinkedIn",
            retrieved_at=datetime.now(UTC),
        )
    ]

    return Candidate(
        name=profile.name or "Unknown",
        primary_profile=profile.url,
        linkedin_url=profile.url,
        github_url=None,  # Would need separate enrichment
        twitter_url=profile.twitter,
        email=profile.email,
        degree_signal=degree_signal,
        engineering_experience=profile.experience_summary,
        current_role=profile.current_title or profile.headline,
        current_company=profile.current_company,
        location=profile.location,
        estimated_salary_band=salary_band,
        estimated_age_band=age_band,
        public_work=[],  # LinkedIn doesn't expose this
        ai_signal_score=0.0,  # Not assessed from LinkedIn
        build_in_public_score=0.0,  # Not assessed from LinkedIn
        overall_fit_tier=CandidateTier.C,  # Default, will be updated by scoring
        why_flagged="Found via LinkedIn search",
        evidence=evidence,
        confidence=0.5,  # Default for LinkedIn sources
        score=None,  # Will be set by scoring
        score_contributions=None,
    )
