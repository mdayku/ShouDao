"""
ShouDao data models - strict Pydantic schemas for lead generation.

Design principles:
- extra="forbid" everywhere (fail fast if LLM invents fields)
- Evidence is a first-class object required for contact channels
- Fail closed: no evidence URL → drop or mark invalid
- Canonical Lead JSON model; CSV derived from it
- Generic/flexible for any industry/product/geography
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# =============================================================================
# TYPE LITERALS (extensible via Literal union)
# =============================================================================

RoleCategory = Literal[
    "owner",
    "exec",
    "founder",
    "ceo",
    "director",
    "procurement",
    "operations",
    "project",
    "sales",
    "manager",
    "engineer",
    "other",
]

OrgType = Literal[
    "contractor",
    "developer",
    "supplier",
    "distributor",
    "manufacturer",
    "agency",
    "consultant",
    "architect",
    "retailer",
    "wholesaler",
    "other",
]

ContactChannelType = Literal["email", "phone", "linkedin", "contact_page", "other"]


# =============================================================================
# EVIDENCE (first-class, required for channels)
# =============================================================================


class Evidence(BaseModel):
    """Evidence linking a data point to its source. Required for all contact channels."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl = Field(..., description="Source URL where data was found")
    snippet: str | None = Field(
        default=None, max_length=500, description="Short text snippet as proof"
    )
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# CONTACT CHANNEL (generic abstraction)
# =============================================================================


class ContactChannel(BaseModel):
    """A contact channel with required evidence."""

    model_config = ConfigDict(extra="forbid")

    type: ContactChannelType
    value: str = Field(..., min_length=1, description="The actual value (email, phone, URL)")
    evidence: list[Evidence] = Field(
        ..., min_length=1, description="At least one evidence source required"
    )


# =============================================================================
# CONTACT
# =============================================================================


class Contact(BaseModel):
    """A person at an organization."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="Full name")
    title: str | None = Field(default=None, description="Job title")
    role_category: RoleCategory = Field(default="other", description="Role bucket")
    channels: list[ContactChannel] = Field(
        default_factory=list, description="Contact channels with evidence"
    )


# =============================================================================
# ORGANIZATION
# =============================================================================


class Organization(BaseModel):
    """A B2B organization - works for any industry/vertical."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Organization name")
    org_type: OrgType = Field(default="other", description="Organization type")

    # Industry (free-form list for flexibility)
    industries: list[str] = Field(default_factory=list, description="Industry labels")

    # Geography
    country: str | None = Field(default=None, description="Country or territory")
    region: str | None = Field(default=None, description="State/province/region")
    city: str | None = Field(default=None, description="City")

    # Digital presence
    website: HttpUrl | None = Field(default=None, description="Primary domain")

    # Size indicator (proxy-based)
    size_indicator: str | None = Field(
        default=None, description="small/medium/large/enterprise or count"
    )

    # Description
    description: str | None = Field(default=None, max_length=500)

    # General evidence for the org itself
    evidence: list[Evidence] = Field(default_factory=list)


# =============================================================================
# APPROACH ADVICE
# =============================================================================


class ApproachAdvice(BaseModel):
    """Outreach guidance for a lead."""

    model_config = ConfigDict(extra="forbid")

    recommended_angle: str = Field(
        ..., min_length=1, max_length=300, description="1-2 line outreach angle"
    )
    recommended_first_offer: str = Field(
        ..., min_length=1, max_length=200, description="What to offer first"
    )
    qualifying_question: str = Field(
        ..., min_length=1, max_length=200, description="One qualifying question"
    )


# =============================================================================
# LEAD (THE CANONICAL UNIT)
# =============================================================================


class Lead(BaseModel):
    """
    A complete lead: organization + contacts + evidence + advice.
    This is the canonical unit that gets exported to CSV.
    """

    model_config = ConfigDict(extra="forbid")

    organization: Organization
    contacts: list[Contact] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Quality score 0-1")
    evidence: list[Evidence] = Field(
        default_factory=list, description="General evidence for this lead"
    )
    advice: ApproachAdvice | None = Field(default=None)
    dedupe_key: str | None = Field(default=None, description="Normalized key for deduplication")

    # Source tracking
    extracted_from_url: str | None = Field(
        default=None, description="The URL that produced this lead"
    )
    domain_aligned: bool = Field(
        default=True, description="Whether org domain matches source domain"
    )
    needs_review: bool = Field(default=False, description="Flagged for manual review")

    # Buyer classification (tiered instead of binary)
    buyer_tier: Literal["A", "B", "C", "excluded"] = Field(
        default="B",
        description="A=high confidence buyer, B=probable buyer, C=needs verification, excluded=non-buyer",
    )
    buyer_likelihood: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Likelihood this is a real buyer (0-1)"
    )

    # Query context
    query_context: str | None = Field(
        default=None, description="The prompt that generated this lead"
    )

    # Score explanation (Task 7.2.2)
    score_contributions: dict[str, float] = Field(
        default_factory=dict, description="Breakdown of what contributed to confidence score"
    )

    def has_usable_contact(self) -> bool:
        """Check if lead has at least one usable contact channel."""
        for contact in self.contacts:
            if contact.channels:
                return True
        return False

    def get_evidence_urls(self) -> list[str]:
        """Collect all evidence URLs for this lead."""
        urls = [str(e.url) for e in self.evidence]
        urls.extend(str(e.url) for e in self.organization.evidence)
        for contact in self.contacts:
            for channel in contact.channels:
                urls.extend(str(e.url) for e in channel.evidence)
        return list(set(urls))

    def get_primary_contact(self) -> Contact | None:
        """Get the first/primary contact if any."""
        return self.contacts[0] if self.contacts else None

    def get_primary_email(self) -> str | None:
        """Get the first email found."""
        for contact in self.contacts:
            for channel in contact.channels:
                if channel.type == "email":
                    return channel.value
        return None

    def get_primary_phone(self) -> str | None:
        """Get the first phone found."""
        for contact in self.contacts:
            for channel in contact.channels:
                if channel.type == "phone":
                    return channel.value
        return None


# =============================================================================
# TALENT DISCOVERY MODELS (Gauntlet Cohort 4)
# =============================================================================

SalaryBand = Literal["under_100k", "100k_150k", "150k_200k", "200k_plus", "unknown"]
CandidateTier = Literal["A", "B", "C"]
AgeBand = Literal["young", "optimal", "mature", "senior", "unknown"]


class Candidate(BaseModel):
    """
    A talent candidate for Gauntlet-style programs.
    Qualified if we have email OR social media (GitHub, LinkedIn, Twitter).
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    name: str | None = Field(default=None, description="Full name if found")
    primary_profile: str = Field(..., min_length=1, description="Main profile URL (GitHub, site)")

    # Contact channels (need at least one of: email OR social)
    email: str | None = Field(default=None, description="Public email if found")
    github_url: str | None = Field(default=None, description="GitHub profile URL")
    linkedin_url: str | None = Field(default=None, description="LinkedIn profile URL")
    twitter_url: str | None = Field(default=None, description="Twitter/X profile URL")
    website_url: str | None = Field(default=None, description="Personal website/blog")

    # Education signals
    degree_signal: str | None = Field(
        default=None, description="Education info, e.g. 'CS, MIT' or 'Self-taught'"
    )
    university: str | None = Field(default=None, description="University name if found")

    # Experience signals
    engineering_experience: str | None = Field(
        default=None, description="Work experience summary, e.g. '2 years SWE at startup'"
    )
    current_role: str | None = Field(default=None, description="Current job title")
    current_company: str | None = Field(default=None, description="Current employer")
    years_experience: int | None = Field(default=None, ge=0, description="Years of experience")

    # Age estimation (Gauntlet sweet spot: mean ~30, std dev ~6-7)
    graduation_year: int | None = Field(default=None, description="Undergrad graduation year if found")
    estimated_age: int | None = Field(default=None, ge=18, le=70, description="Estimated age in years")
    age_band: AgeBand = Field(
        default="unknown",
        description="young (<24), optimal (24-36), mature (36-42), senior (>42)",
    )

    # Salary estimation
    estimated_salary_band: SalaryBand = Field(
        default="unknown", description="Estimated salary band based on role/company/geo"
    )

    # Public work (the key signal)
    public_repos: list[str] = Field(default_factory=list, description="GitHub repo URLs")
    public_demos: list[str] = Field(
        default_factory=list, description="Streamlit, HF Spaces, deployed apps"
    )
    blog_posts: list[str] = Field(default_factory=list, description="Technical blog post URLs")

    # Scoring
    ai_signal_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="AI/LLM project engagement (0-1)"
    )
    build_in_public_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Public building activity (0-1)"
    )
    overall_fit_tier: CandidateTier = Field(default="C", description="A/B/C tier")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall confidence")

    # Explanation
    why_flagged: str = Field(
        default="", description="Human-readable justification for why this candidate was flagged"
    )
    score_contributions: dict[str, float] = Field(
        default_factory=dict, description="Breakdown of scoring factors"
    )

    # Evidence
    evidence: list[Evidence] = Field(default_factory=list)
    extracted_from_url: str | None = Field(default=None)

    def is_contactable(self) -> bool:
        """Check if we have enough to reach out (email OR social)."""
        return bool(
            self.email or self.github_url or self.linkedin_url or self.twitter_url
        )

    def get_contact_channels(self) -> list[str]:
        """Get all available contact channels."""
        channels = []
        if self.email:
            channels.append(f"email:{self.email}")
        if self.github_url:
            channels.append(f"github:{self.github_url}")
        if self.linkedin_url:
            channels.append(f"linkedin:{self.linkedin_url}")
        if self.twitter_url:
            channels.append(f"twitter:{self.twitter_url}")
        return channels

    def get_public_work_count(self) -> int:
        """Count total public work artifacts."""
        return len(self.public_repos) + len(self.public_demos) + len(self.blog_posts)


class TalentRunResult(BaseModel):
    """Result of a talent discovery run."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[Candidate] = Field(default_factory=list)
    run_id: str = Field(default="")
    prompt: str = Field(default="")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = Field(default=None)

    # Stats
    sources_fetched: int = Field(default=0)
    total_candidates_extracted: int = Field(default=0)
    total_candidates_after_dedupe: int = Field(default=0)
    contactable_candidates: int = Field(default=0)

    # Tier breakdown
    tier_a_count: int = Field(default=0)
    tier_b_count: int = Field(default=0)
    tier_c_count: int = Field(default=0)

    # Errors
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# QUERY RECIPE
# =============================================================================


class QueryRecipe(BaseModel):
    """A saved query configuration for reproducible runs."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., min_length=1, description="Unique identifier")
    prompt: str = Field(..., min_length=1, description="The search prompt")

    # Filters (generic dict for flexibility)
    region: dict[str, Any] | None = Field(default=None, description="Region filter config")
    segments: list[str] = Field(default_factory=list, description="Target segments")
    role_targets: list[RoleCategory] = Field(default_factory=list, description="Target roles")

    # Policy
    policy: dict[str, Any] = Field(
        default_factory=dict, description="allow/block lists, max pages, etc."
    )

    # Seed sources
    seed_sources: list[str] = Field(default_factory=list, description="Known-good URLs to crawl")


# =============================================================================
# RUN CONFIGURATION & RESULTS
# =============================================================================


class RunConfig(BaseModel):
    """Configuration for a single run."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, description="The user's search prompt")
    recipe_slug: str | None = Field(default=None, description="If run from a recipe")

    # Filters (simplified for MVP)
    countries: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    org_types: list[OrgType] = Field(default_factory=list)
    role_targets: list[RoleCategory] = Field(default_factory=list)

    # Source controls
    seed_sources: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)

    # Limits
    max_results: int | None = Field(
        default=50,
        description="Maximum number of leads to keep after scoring; None means unlimited.",
    )

    @field_validator("max_results")
    @classmethod
    def _validate_max_results(cls, v: int | None) -> int | None:
        """Validate max_results.

        Args:
            v: The max results value.

        Returns:
            The validated value.

        Raises:
            ValueError: If v is non-null and less than 1.
        """
        if v is None:
            return None
        if v < 1:
            raise ValueError("max_results must be >= 1, or None for unlimited")
        return v

    # Context for advice
    product_context: str = Field(default="", description="What's being sold")
    seller_context: str = Field(default="", description="Who's selling")

    # Provider
    search_provider: Literal["serper", "serpapi", "mock"] = Field(default="serper")


class RunResult(BaseModel):
    """Result of a pipeline run."""

    model_config = ConfigDict(extra="forbid")

    config: RunConfig
    leads: list[Lead] = Field(default_factory=list)
    run_id: str = Field(default="")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = Field(default=None)

    # Stats
    sources_fetched: int = Field(default=0)
    domains_hit: int = Field(default=0)
    total_urls_searched: int = Field(default=0)
    total_leads_extracted: int = Field(default=0)
    total_leads_after_dedupe: int = Field(default=0)

    # Errors
    errors: list[str] = Field(default_factory=list)
