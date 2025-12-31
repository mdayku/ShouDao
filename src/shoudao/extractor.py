"""
ShouDao extractor - LLM-based lead extraction with structured outputs.
Enforces evidence requirement for all contact channels.

Key design:
- Extraction schema is LEAD-CENTRIC (org + contacts nested together)
- Every contact channel MUST have evidence
- Fail-soft at field level, fail-closed at lead level
"""

import os
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from .fetcher import FetchResult
from .models import (
    Candidate,
    Contact,
    ContactChannel,
    ContactChannelType,
    Evidence,
    Lead,
    Organization,
    OrgType,
    RoleCategory,
)

# =============================================================================
# EXTRACTION SCHEMAS (for OpenAI structured outputs)
# Lead-centric: org + contacts are nested together
# =============================================================================


class ExtractedChannel(BaseModel):
    """A contact channel extracted from a page."""

    model_config = ConfigDict(extra="forbid")

    type: ContactChannelType
    value: str = Field(..., min_length=1)


class ExtractedContact(BaseModel):
    """A contact extracted from a page, associated with a specific org."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    title: str | None = None
    role_category: RoleCategory = "other"
    channels: list[ExtractedChannel] = Field(default_factory=list)


class ExtractedLead(BaseModel):
    """
    A lead extracted from a page: org + its contacts together.
    This is the key fix: contacts are nested under their org.
    """

    model_config = ConfigDict(extra="forbid")

    # Organization info
    org_name: str = Field(..., min_length=1)
    org_type: OrgType = "other"
    industries: list[str] = Field(default_factory=list)
    country: str | None = None
    region: str | None = None
    city: str | None = None
    website: str | None = None
    size_indicator: str | None = None
    description: str | None = None

    # Contacts associated with THIS org
    contacts: list[ExtractedContact] = Field(default_factory=list)


PageType = Literal["directory", "company_site", "article", "other"]


class ExtractionResult(BaseModel):
    """Result of extracting leads from a page."""

    model_config = ConfigDict(extra="forbid")

    page_type: PageType = Field(
        default="other",
        description="Type of page: directory (lists multiple companies), company_site (single company), article, other",
    )
    leads: list[ExtractedLead] = Field(default_factory=list)
    is_relevant: bool = Field(default=False)
    evidence_snippet: str = Field(default="", max_length=500)


EXTRACTION_PROMPT = """You are a B2B lead extraction assistant. Extract organization and contact information from the given webpage text.

User's search intent: {prompt}

STEP 1: CLASSIFY THE PAGE TYPE
- "directory": Lists multiple companies (e.g., supplier directory, partner page, "top 10" list, trade association members)
- "company_site": Single company's own website (about us, contact us, team page)
- "article": News, blog post, or informational content
- "other": Doesn't fit above categories

STEP 2: EXTRACT LEADS BASED ON PAGE TYPE
- If page_type = "directory": Extract ALL companies listed (multiple leads OK)
- If page_type = "company_site": Extract ONLY THE COMPANY THAT OWNS THIS SITE (max 1 lead)
- If page_type = "article" or "other": Extract only if organizations are clearly featured

CRITICAL RULE: A company's own contact/about page should NEVER yield multiple organizations.
The contact page of "Domus Windows" should only return Domus Windows, not their partners/clients mentioned.

Return leads as a list where each lead contains ONE organization with ITS associated contacts.

Rules:
1. Only extract information EXPLICITLY stated in the text
2. Do NOT guess or infer email addresses - only extract if clearly visible
3. org_type: contractor, developer, supplier, distributor, manufacturer, agency, consultant, architect, retailer, wholesaler, other
4. role_category: owner, exec, founder, ceo, director, procurement, operations, project, sales, manager, engineer, other
5. channel type: email, phone, linkedin, contact_page, other
6. Set is_relevant=true only if page contains B2B organization/contact information
7. Provide a short evidence_snippet proving the data exists on this page
8. Each contact should be listed under the organization they belong to

Page content:
{content}
"""


class Extractor:
    """LLM-based lead extractor using OpenAI Responses API with structured outputs."""

    # Default model: gpt-5-mini (cost-optimized reasoning)
    # Fallback: gpt-4o (if gpt-5-mini fails)
    DEFAULT_MODEL = "gpt-5-mini"
    FALLBACK_MODEL = "gpt-4o"

    # GPT-5.x models that support Responses API parameters
    GPT5_MODELS = {"gpt-5-mini", "gpt-5-nano", "gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.2-pro"}

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)
        # Model can be set via env var SHOUDAO_MODEL, defaults to gpt-5-mini
        self.model = model or os.getenv("SHOUDAO_MODEL", self.DEFAULT_MODEL)

    def _is_gpt5_model(self, model: str) -> bool:
        """Check if model supports GPT-5.x Responses API parameters."""
        return any(model.startswith(m) for m in self.GPT5_MODELS)

    def _ensure_all_required(self, schema: dict) -> dict:
        """Recursively ensure all properties are in 'required' array at every level.
        
        OpenAI strict mode requires this for all nested objects and $defs.
        """
        if not isinstance(schema, dict):
            return schema
        
        # Fix $defs (where Pydantic puts nested model definitions)
        if "$defs" in schema:
            for def_name, def_schema in schema["$defs"].items():
                schema["$defs"][def_name] = self._ensure_all_required(def_schema)
        
        # Fix this level's properties
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
            # Recurse into each property
            for prop_name, prop_schema in schema["properties"].items():
                schema["properties"][prop_name] = self._ensure_all_required(prop_schema)
        
        # Handle arrays with items
        if "items" in schema:
            schema["items"] = self._ensure_all_required(schema["items"])
        
        # Handle anyOf/oneOf (for Optional types)
        for key in ("anyOf", "oneOf"):
            if key in schema:
                schema[key] = [self._ensure_all_required(s) for s in schema[key]]
        
        return schema

    def _call_model(self, model: str, system_prompt: str, user_prompt: str, response_format: type):
        """Call the model with structured output. Returns parsed result or raises.

        Uses Responses API for GPT-5.x models with:
        - reasoning.effort: "minimal" (low-latency, prompting handles reasoning)
        - strict: True (enforce schema compliance)
        """
        # Combine system + user prompt for Responses API input format
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        if self._is_gpt5_model(model):
            # Use Responses API for GPT-5.x models
            # Build schema with all properties required at EVERY level (OpenAI requirement)
            schema = response_format.model_json_schema()
            schema = self._ensure_all_required(schema)

            response = self.client.responses.create(
                model=model,
                input=full_prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": response_format.__name__,
                        "strict": True,
                        "schema": schema,
                    }
                },
                reasoning={"effort": "minimal"},
            )
            # Parse the JSON response into the Pydantic model
            import json

            return response_format.model_validate(json.loads(response.output_text))
        else:
            # Fallback to Chat Completions for older models (gpt-4o, etc.)
            completion = self.client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
            )
            return completion.choices[0].message.parsed

    def extract(self, fetch_result: FetchResult, prompt: str) -> ExtractionResult:
        """Extract leads from a fetched page."""
        if not fetch_result.success or not fetch_result.text:
            return ExtractionResult(is_relevant=False)

        # Truncate content to avoid token limits
        content = fetch_result.text[:8000]

        system_prompt = "You extract B2B leads from webpages. Each lead = one organization + its contacts. Be precise."
        user_prompt = EXTRACTION_PROMPT.format(prompt=prompt, content=content)

        # Try primary model first, then fallback
        try:
            return self._call_model(self.model, system_prompt, user_prompt, ExtractionResult)
        except Exception as e:
            # If using default model and it failed, try fallback
            if self.model == self.DEFAULT_MODEL:
                print(
                    f"Primary model ({self.model}) failed, trying fallback ({self.FALLBACK_MODEL}): {e}"
                )
                try:
                    return self._call_model(
                        self.FALLBACK_MODEL, system_prompt, user_prompt, ExtractionResult
                    )
                except Exception as e2:
                    print(f"Fallback model also failed for {fetch_result.url}: {e2}")
                    return ExtractionResult(is_relevant=False)
            else:
                print(f"Extraction error for {fetch_result.url}: {e}")
                return ExtractionResult(is_relevant=False)

    def extraction_to_leads(
        self,
        extraction: ExtractionResult,
        source_url: str,
    ) -> list[Lead]:
        """
        Convert extraction result to Lead objects.

        GUARDRAIL: If page_type is NOT 'directory', only keep first lead.
        This prevents over-extraction from single-company pages.

        Fail-soft strategy:
        - Drop channels without value
        - Drop contacts with no channels AND no name
        - Keep leads that have org evidence OR usable contacts
        """
        if not extraction.is_relevant:
            return []

        # GUARDRAIL: If not a directory page, only process first lead
        # This prevents over-extraction from single-company pages
        extracted_leads = extraction.leads
        if extraction.page_type != "directory" and len(extracted_leads) > 1:
            print(
                f"  [Guardrail] {source_url}: page_type={extraction.page_type}, "
                f"limiting from {len(extracted_leads)} to 1 lead"
            )
            extracted_leads = extracted_leads[:1]

        leads = []

        # Create evidence object for this source
        evidence = Evidence(
            url=source_url,  # type: ignore (HttpUrl accepts str)
            snippet=extraction.evidence_snippet[:500] if extraction.evidence_snippet else None,
        )

        for extracted_lead in extracted_leads:
            # Build contacts with evidence-backed channels
            contacts = []
            for ec in extracted_lead.contacts:
                # Fail-soft: only include channels with non-empty, non-sentinel values
                channels = []
                for ch in ec.channels:
                    cleaned_value = _clean_value(ch.value)
                    if cleaned_value:
                        channel = ContactChannel(
                            type=ch.type,
                            value=cleaned_value,
                            evidence=[evidence],
                        )
                        channels.append(channel)

                # Keep contact if it has channels OR at least a name
                cleaned_name = _clean_value(ec.name)
                cleaned_title = _clean_value(ec.title)
                if channels or cleaned_name:
                    contact = Contact(
                        name=cleaned_name,
                        title=cleaned_title,
                        role_category=ec.role_category,
                        channels=channels,
                    )
                    contacts.append(contact)

            # Normalize website URL and country
            normalized_website = _normalize_website(extracted_lead.website)
            normalized_country = _normalize_country(extracted_lead.country)

            # Build organization
            organization = Organization(
                name=extracted_lead.org_name,
                org_type=extracted_lead.org_type,
                industries=extracted_lead.industries,
                country=normalized_country,
                region=_clean_value(extracted_lead.region),
                city=_clean_value(extracted_lead.city),
                website=normalized_website,  # type: ignore
                size_indicator=_clean_value(extracted_lead.size_indicator),
                description=_clean_value(extracted_lead.description),
                evidence=[evidence],
            )

            # Check domain alignment between org website and source URL
            source_domain = _normalize_domain(source_url)
            org_domain = _normalize_domain(normalized_website) if normalized_website else None

            # Domain alignment check:
            # - If org has no website, assume it came from the source (aligned)
            # - If org domain matches source domain, aligned
            # - If org domain differs from source domain, misaligned (needs review)
            domain_aligned = True
            needs_review = False

            if org_domain and org_domain != source_domain:
                # Different domains - this might be a directory page or misattribution
                domain_aligned = False
                needs_review = True

            # Build lead
            lead = Lead(
                organization=organization,
                contacts=contacts,
                evidence=[evidence],
                dedupe_key=_normalize_domain(normalized_website or source_url),
                extracted_from_url=source_url,
                domain_aligned=domain_aligned,
                needs_review=needs_review,
            )

            # Fail-closed at lead level: must have evidence-backed org OR usable contact
            if lead.organization.evidence or lead.has_usable_contact():
                leads.append(lead)

        return leads


def _normalize_domain(url_or_domain: str) -> str:
    """Normalize domain for deduplication."""
    if url_or_domain.startswith("http"):
        domain = urlparse(url_or_domain).netloc
    else:
        domain = url_or_domain
    domain = domain.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _normalize_website(website: str | None) -> str | None:
    """
    Normalize a website URL extracted by the LLM.
    Handles bare domains, invalid values, etc.
    """
    if not website:
        return None

    website = website.strip()

    # Filter out obvious non-URLs
    invalid_patterns = [
        "visit website",
        "click here",
        "n/a",
        "none",
        "not provided",
        "unknown",
    ]
    if website.lower() in invalid_patterns:
        return None

    # If it looks like a bare domain, add https://
    if not website.startswith(("http://", "https://")):
        # Check if it looks like a domain (has a dot, no spaces)
        if "." in website and " " not in website:
            website = f"https://{website}"
        else:
            return None

    return website


# Sentinel values that should be treated as None/empty
SENTINEL_VALUES = {
    "not provided",
    "n/a",
    "none",
    "unknown",
    "not available",
    "not specified",
    "-",
    "null",
    "na",
}


def _clean_value(value: str | None) -> str | None:
    """Clean a string value, converting sentinel strings to None."""
    if not value:
        return None
    value = value.strip()
    if value.lower() in SENTINEL_VALUES:
        return None
    return value


# Country normalization map
COUNTRY_ALIASES = {
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "england": "United Kingdom",
}


def _normalize_country(country: str | None) -> str | None:
    """Normalize country names to a consistent format."""
    if not country:
        return None
    country = country.strip()
    if country.lower() in SENTINEL_VALUES:
        return None
    # Check alias map
    normalized = COUNTRY_ALIASES.get(country.lower())
    if normalized:
        return normalized
    return country


# =============================================================================
# REGEX FALLBACK EXTRACTORS
# =============================================================================

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(
    r"[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}"
)


def extract_emails_regex(text: str) -> list[str]:
    """Extract emails using regex (fallback)."""
    emails = EMAIL_REGEX.findall(text)
    filtered = [
        e for e in emails if not e.endswith((".png", ".jpg", ".gif")) and "@example" not in e
    ]
    return list(set(filtered))


def extract_phones_regex(text: str) -> list[str]:
    """Extract phone numbers using regex (fallback)."""
    phones = PHONE_REGEX.findall(text)
    return [p for p in phones if len(p.replace(" ", "").replace("-", "")) >= 7]


# =============================================================================
# RULE-BASED SIGNAL EXTRACTION AND MERGING
# =============================================================================


@dataclass
class RuleBasedSignals:
    """Signals extracted via regex/rules (fallback for LLM)."""

    emails: list[str]
    phones: list[str]
    github_urls: list[str]
    linkedin_urls: list[str]
    twitter_urls: list[str]


def extract_rule_based_signals(text: str) -> RuleBasedSignals:
    """
    Extract contact signals using regex/rules.

    This runs as a fallback to LLM extraction, catching emails/phones
    that the LLM may have missed.

    Args:
        text: Raw text content to extract from

    Returns:
        RuleBasedSignals with all found contact channels
    """
    return RuleBasedSignals(
        emails=extract_emails_regex(text),
        phones=extract_phones_regex(text),
        github_urls=extract_github_urls_regex(text),
        linkedin_urls=extract_linkedin_urls_regex(text),
        twitter_urls=extract_twitter_urls_regex(text),
    )


def merge_rule_signals_into_lead(
    lead: Lead,
    signals: RuleBasedSignals,
    source_url: str,
) -> Lead:
    """
    Merge rule-based signals into an existing LLM-extracted lead.

    Strategy:
    - Add emails/phones not already in lead's contacts
    - Associate new channels with evidence from source_url
    - Don't create new contacts, just enrich existing ones

    Args:
        lead: The LLM-extracted lead to enrich
        signals: Rule-based signals to merge
        source_url: Source URL for evidence

    Returns:
        Enriched lead with merged signals
    """
    # Collect existing channels from all contacts
    existing_emails: set[str] = set()
    existing_phones: set[str] = set()

    for contact in lead.contacts:
        for channel in contact.channels:
            if channel.type == "email":
                existing_emails.add(channel.value.lower())
            elif channel.type == "phone":
                existing_phones.add(channel.value)

    # Find new signals
    new_emails = [e for e in signals.emails if e.lower() not in existing_emails]
    new_phones = [p for p in signals.phones if p not in existing_phones]

    # If we have new signals and at least one contact, add to first contact
    if (new_emails or new_phones) and lead.contacts:
        evidence = Evidence(
            url=source_url,  # type: ignore
            snippet="Extracted via regex fallback",
        )

        first_contact = lead.contacts[0]
        for email in new_emails[:3]:  # Cap at 3 new emails
            first_contact.channels.append(
                ContactChannel(type="email", value=email, evidence=[evidence])
            )
        for phone in new_phones[:2]:  # Cap at 2 new phones
            first_contact.channels.append(
                ContactChannel(type="phone", value=phone, evidence=[evidence])
            )

    return lead


# =============================================================================
# TALENT EXTRACTION (Gauntlet Cohort 4)
# =============================================================================


class ExtractedCandidate(BaseModel):
    """A candidate extracted from a page (GitHub, blog, portfolio)."""

    model_config = ConfigDict(extra="forbid")

    # Identity
    name: str | None = None
    primary_profile_url: str | None = None

    # Contact channels (need at least email OR social)
    email: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    twitter_url: str | None = None
    website_url: str | None = None

    # Education
    degree_signal: str | None = Field(
        default=None, description="Education, e.g. 'CS degree from MIT' or 'Self-taught'"
    )
    university: str | None = None

    # Experience
    current_role: str | None = None
    current_company: str | None = None
    years_experience: int | None = None

    # Public work (key signals)
    repo_names: list[str] = Field(default_factory=list, description="GitHub repo names found")
    has_ai_projects: bool = Field(default=False, description="Has AI/LLM related projects")
    has_demos: bool = Field(default=False, description="Has deployed demos/apps")
    has_blog: bool = Field(default=False, description="Has technical blog/writing")


class TalentExtractionResult(BaseModel):
    """Result of extracting candidates from a page."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[ExtractedCandidate] = Field(default_factory=list)
    is_relevant: bool = Field(default=False, description="Page has talent signals")
    evidence_snippet: str = Field(default="", max_length=500)


TALENT_EXTRACTION_PROMPT = """You are a talent scout looking for software engineers who would be good candidates for an AI-focused accelerator program.

Extract candidate information from this page. Look for:
1. Individual developers/engineers (NOT companies)
2. People building with AI/LLM tools
3. GitHub profiles, personal sites, portfolios
4. Education and work experience signals

Qualification signals (look for these):
- CS degree or equivalent background
- Engineering work experience
- Public AI/LLM projects (agents, demos, tools)
- Technical blog posts or "building in public" content
- GitHub activity with real projects

Extract ALL contact channels you find:
- Email addresses
- GitHub profile URLs
- LinkedIn profile URLs
- Twitter/X profile URLs
- Personal website/blog URLs

IMPORTANT: A candidate is qualified if we have at least:
- Email address, OR
- Any social media profile (GitHub, LinkedIn, Twitter)

We do NOT require name + phone - just a way to reach them.

Page content:
{content}
"""


class TalentExtractor:
    """LLM-based candidate extractor for talent discovery using Responses API."""

    # Default model: gpt-5-mini (cost-optimized reasoning)
    # Fallback: gpt-4o (if gpt-5-mini fails)
    DEFAULT_MODEL = "gpt-5-mini"
    FALLBACK_MODEL = "gpt-4o"

    # GPT-5.x models that support Responses API parameters
    GPT5_MODELS = {"gpt-5-mini", "gpt-5-nano", "gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.2-pro"}

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model or os.getenv("SHOUDAO_MODEL", self.DEFAULT_MODEL)

    def _is_gpt5_model(self, model: str) -> bool:
        """Check if model supports GPT-5.x Responses API parameters."""
        return any(model.startswith(m) for m in self.GPT5_MODELS)

    def _ensure_all_required(self, schema: dict) -> dict:
        """Recursively ensure all properties are in 'required' array at every level."""
        if not isinstance(schema, dict):
            return schema
        if "$defs" in schema:
            for def_name, def_schema in schema["$defs"].items():
                schema["$defs"][def_name] = self._ensure_all_required(def_schema)
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
            for prop_name, prop_schema in schema["properties"].items():
                schema["properties"][prop_name] = self._ensure_all_required(prop_schema)
        if "items" in schema:
            schema["items"] = self._ensure_all_required(schema["items"])
        for key in ("anyOf", "oneOf"):
            if key in schema:
                schema[key] = [self._ensure_all_required(s) for s in schema[key]]
        return schema

    def _call_model(self, model: str, system_prompt: str, user_prompt: str, response_format: type):
        """Call the model with structured output. Returns parsed result or raises."""
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        if self._is_gpt5_model(model):
            # Use Responses API for GPT-5.x models
            # Build schema with all properties required at EVERY level (OpenAI requirement)
            schema = response_format.model_json_schema()
            schema = self._ensure_all_required(schema)

            response = self.client.responses.create(
                model=model,
                input=full_prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": response_format.__name__,
                        "strict": True,
                        "schema": schema,
                    }
                },
                reasoning={"effort": "minimal"},
            )
            import json

            return response_format.model_validate(json.loads(response.output_text))
        else:
            # Fallback to Chat Completions for older models
            completion = self.client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
            )
            return completion.choices[0].message.parsed

    def extract(self, fetch_result: FetchResult) -> TalentExtractionResult:
        """Extract candidates from a fetched page."""
        if not fetch_result.success or not fetch_result.text:
            return TalentExtractionResult(is_relevant=False)

        # Truncate content to avoid token limits
        content = fetch_result.text[:8000]

        system_prompt = "You are a talent scout extracting candidate information from webpages. Focus on individuals (not companies) who build software, especially AI/LLM projects."
        user_prompt = TALENT_EXTRACTION_PROMPT.format(content=content)

        # Try primary model first, then fallback
        try:
            return self._call_model(self.model, system_prompt, user_prompt, TalentExtractionResult)
        except Exception as e:
            # If using default model and it failed, try fallback
            if self.model == self.DEFAULT_MODEL:
                print(
                    f"Primary model ({self.model}) failed, trying fallback ({self.FALLBACK_MODEL}): {e}"
                )
                try:
                    return self._call_model(
                        self.FALLBACK_MODEL, system_prompt, user_prompt, TalentExtractionResult
                    )
                except Exception as e2:
                    print(f"Fallback model also failed for {fetch_result.url}: {e2}")
                    return TalentExtractionResult(is_relevant=False)
            else:
                print(f"Talent extraction error for {fetch_result.url}: {e}")
                return TalentExtractionResult(is_relevant=False)

    def extraction_to_candidates(
        self,
        extraction: TalentExtractionResult,
        source_url: str,
    ) -> list[Candidate]:
        """Convert extraction result to Candidate objects."""
        if not extraction.is_relevant:
            return []

        candidates = []
        evidence = Evidence(
            url=source_url,  # type: ignore
            snippet=extraction.evidence_snippet[:500] if extraction.evidence_snippet else None,
        )

        for ec in extraction.candidates:
            # Clean all values
            email = _clean_value(ec.email)
            github_url = _clean_value(ec.github_url)
            linkedin_url = _clean_value(ec.linkedin_url)
            twitter_url = _clean_value(ec.twitter_url)
            website_url = _clean_value(ec.website_url)

            # Determine primary profile URL
            primary_profile = _clean_value(ec.primary_profile_url)
            if not primary_profile:
                # Fallback priority: GitHub > LinkedIn > Twitter > Website > Source
                primary_profile = (
                    github_url or linkedin_url or twitter_url or website_url or source_url
                )

            # Check if contactable (email OR any social)
            is_contactable = bool(email or github_url or linkedin_url or twitter_url)

            if not is_contactable:
                continue  # Skip candidates we can't contact

            # Calculate AI signal score based on extracted signals
            ai_signal_score = 0.0
            if ec.has_ai_projects:
                ai_signal_score += 0.5
            if len(ec.repo_names) >= 3:
                ai_signal_score += 0.3
            if ec.has_demos:
                ai_signal_score += 0.2
            ai_signal_score = min(ai_signal_score, 1.0)

            # Calculate build-in-public score
            build_in_public_score = 0.0
            if ec.has_blog:
                build_in_public_score += 0.4
            if github_url:
                build_in_public_score += 0.3
            if twitter_url:
                build_in_public_score += 0.2
            if len(ec.repo_names) > 0:
                build_in_public_score += 0.1
            build_in_public_score = min(build_in_public_score, 1.0)

            # Build candidate
            candidate = Candidate(
                name=_clean_value(ec.name),
                primary_profile=primary_profile,
                email=email,
                github_url=github_url,
                linkedin_url=linkedin_url,
                twitter_url=twitter_url,
                website_url=website_url,
                degree_signal=_clean_value(ec.degree_signal),
                university=_clean_value(ec.university),
                current_role=_clean_value(ec.current_role),
                current_company=_clean_value(ec.current_company),
                years_experience=ec.years_experience,
                public_repos=ec.repo_names,
                ai_signal_score=ai_signal_score,
                build_in_public_score=build_in_public_score,
                evidence=[evidence],
                extracted_from_url=source_url,
            )
            candidates.append(candidate)

        return candidates


# GitHub URL regex for extraction
GITHUB_URL_REGEX = re.compile(r"https?://github\.com/[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)?")
LINKEDIN_URL_REGEX = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+")
TWITTER_URL_REGEX = re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+")


def extract_github_urls_regex(text: str) -> list[str]:
    """Extract GitHub URLs using regex (fallback)."""
    urls = GITHUB_URL_REGEX.findall(text)
    return list(set(urls))


def extract_linkedin_urls_regex(text: str) -> list[str]:
    """Extract LinkedIn URLs using regex (fallback)."""
    urls = LINKEDIN_URL_REGEX.findall(text)
    return list(set(urls))


def extract_twitter_urls_regex(text: str) -> list[str]:
    """Extract Twitter/X URLs using regex (fallback)."""
    urls = TWITTER_URL_REGEX.findall(text)
    return list(set(urls))
