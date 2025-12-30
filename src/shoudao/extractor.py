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
from urllib.parse import urlparse

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from .fetcher import FetchResult
from .models import (
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


class ExtractionResult(BaseModel):
    """Result of extracting leads from a page."""

    model_config = ConfigDict(extra="forbid")

    leads: list[ExtractedLead] = Field(default_factory=list)
    is_relevant: bool = Field(default=False)
    evidence_snippet: str = Field(default="", max_length=500)


EXTRACTION_PROMPT = """You are a B2B lead extraction assistant. Extract organization and contact information from the given webpage text.

User's search intent: {prompt}

IMPORTANT: Return leads as a list where each lead contains ONE organization with ITS associated contacts.
Do NOT return separate lists of orgs and contacts - contacts must be nested under their organization.

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
    """LLM-based lead extractor using OpenAI structured outputs."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def extract(self, fetch_result: FetchResult, prompt: str) -> ExtractionResult:
        """Extract leads from a fetched page."""
        if not fetch_result.success or not fetch_result.text:
            return ExtractionResult(is_relevant=False)

        # Truncate content to avoid token limits
        content = fetch_result.text[:8000]

        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract B2B leads from webpages. Each lead = one organization + its contacts. Be precise.",
                    },
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(prompt=prompt, content=content),
                    },
                ],
                response_format=ExtractionResult,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"Extraction error for {fetch_result.url}: {e}")
            return ExtractionResult(is_relevant=False)

    def extraction_to_leads(
        self,
        extraction: ExtractionResult,
        source_url: str,
    ) -> list[Lead]:
        """
        Convert extraction result to Lead objects.

        Fail-soft strategy:
        - Drop channels without value
        - Drop contacts with no channels AND no name
        - Keep leads that have org evidence OR usable contacts
        """
        if not extraction.is_relevant:
            return []

        leads = []

        # Create evidence object for this source
        evidence = Evidence(
            url=source_url,  # type: ignore (HttpUrl accepts str)
            snippet=extraction.evidence_snippet[:500] if extraction.evidence_snippet else None,
        )

        for extracted_lead in extraction.leads:
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

            # Build lead
            lead = Lead(
                organization=organization,
                contacts=contacts,
                evidence=[evidence],
                dedupe_key=_normalize_domain(normalized_website or source_url),
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
