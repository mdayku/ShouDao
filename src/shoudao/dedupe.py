"""
ShouDao dedupe + scoring engine.
Includes buyer-only gate and Caribbean country filter.
"""

from urllib.parse import urlparse

from .models import Lead

# =============================================================================
# CARIBBEAN COUNTRY WHITELIST
# =============================================================================

CARIBBEAN_COUNTRIES = {
    # English-speaking
    "jamaica",
    "trinidad",
    "trinidad and tobago",
    "barbados",
    "bahamas",
    "the bahamas",
    "cayman islands",
    "cayman",
    "turks and caicos",
    "saint lucia",
    "st. lucia",
    "st lucia",
    "grenada",
    "antigua",
    "antigua and barbuda",
    "saint vincent",
    "st. vincent",
    "st vincent",
    "saint vincent and the grenadines",
    "dominica",
    "british virgin islands",
    "bvi",
    "us virgin islands",
    "usvi",
    # Spanish-speaking
    "puerto rico",
    "dominican republic",
    "cuba",
    # French-speaking
    "haiti",
    "guadeloupe",
    "martinique",
    "saint barthelemy",
    "st. barthelemy",
    "st barth",
    "saint martin",
    "st. martin",
    # Dutch-speaking
    "aruba",
    "curacao",
    "curaçao",
    "sint maarten",
    # Generic
    "caribbean",
}

# Exporter/foreign manufacturer signals
EXPORTER_SIGNALS = [
    "export",
    "exporter",
    "international",
    "overseas",
    "global",
    "worldwide",
    "import and export",
    "trading company",
    "factory direct",
    "oem",
    "odm",
    "bulk supplier",
]

# Buyer-friendly org types
BUYER_ORG_TYPES = {"distributor", "installer", "contractor", "supplier", "retailer", "consultant"}

# Non-buyer org types that need extra scrutiny
MANUFACTURER_TYPES = {"manufacturer"}


def normalize_domain(url_or_domain: str) -> str:
    """Normalize a domain for deduplication."""
    if not url_or_domain:
        return ""
    if url_or_domain.startswith("http"):
        domain = urlparse(url_or_domain).netloc
    else:
        domain = url_or_domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_org_name(name: str) -> str:
    """Normalize organization name for deduplication."""
    name = name.lower().strip()
    suffixes = [
        " llc",
        " inc",
        " ltd",
        " corp",
        " co",
        " company",
        " limited",
        " gmbh",
        " ag",
        " sa",
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    name = "".join(c for c in name if c.isalnum() or c.isspace())
    name = " ".join(name.split())
    return name


def compute_dedupe_key(lead: Lead) -> str:
    """Compute a deduplication key for a lead."""
    if lead.organization.website:
        return normalize_domain(str(lead.organization.website))
    name = normalize_org_name(lead.organization.name)
    location = (lead.organization.country or "").lower()
    return f"{name}|{location}"


def merge_leads(existing: Lead, new: Lead) -> Lead:
    """Merge two leads into one, combining contacts and evidence."""
    # Combine contacts (avoid duplicates by checking channels)
    existing_emails = set()
    for c in existing.contacts:
        for ch in c.channels:
            if ch.type == "email":
                existing_emails.add(ch.value)

    for contact in new.contacts:
        has_new_email = False
        for ch in contact.channels:
            if ch.type == "email" and ch.value not in existing_emails:
                has_new_email = True
                break
        if has_new_email or not any(ch.type == "email" for ch in contact.channels):
            existing.contacts.append(contact)

    # Combine organization evidence
    existing_urls = {str(e.url) for e in existing.organization.evidence}
    for ev in new.organization.evidence:
        if str(ev.url) not in existing_urls:
            existing.organization.evidence.append(ev)

    # Combine lead-level evidence
    existing_lead_urls = {str(e.url) for e in existing.evidence}
    for ev in new.evidence:
        if str(ev.url) not in existing_lead_urls:
            existing.evidence.append(ev)

    # Take higher confidence
    existing.confidence = max(existing.confidence, new.confidence)

    # Merge industries
    for ind in new.organization.industries:
        if ind not in existing.organization.industries:
            existing.organization.industries.append(ind)

    # Fill missing fields
    if not existing.organization.description and new.organization.description:
        existing.organization.description = new.organization.description
    if not existing.organization.size_indicator and new.organization.size_indicator:
        existing.organization.size_indicator = new.organization.size_indicator
    if not existing.organization.city and new.organization.city:
        existing.organization.city = new.organization.city
    if not existing.organization.region and new.organization.region:
        existing.organization.region = new.organization.region

    return existing


def dedupe_leads(leads: list[Lead]) -> list[Lead]:
    """Deduplicate a list of leads."""
    by_key: dict[str, Lead] = {}

    for lead in leads:
        key = compute_dedupe_key(lead)
        lead.dedupe_key = key

        if key in by_key:
            by_key[key] = merge_leads(by_key[key], lead)
        else:
            by_key[key] = lead

    return list(by_key.values())


def is_caribbean_country(country: str | None) -> bool:
    """Check if a country is in the Caribbean whitelist."""
    if not country:
        return False
    return country.lower().strip() in CARIBBEAN_COUNTRIES


def has_exporter_signals(lead: Lead) -> bool:
    """Check if lead has signals of being an exporter/foreign manufacturer."""
    text_to_check = " ".join(
        [
            lead.organization.name.lower(),
            (lead.organization.description or "").lower(),
            " ".join(lead.organization.industries).lower(),
        ]
    )

    for signal in EXPORTER_SIGNALS:
        if signal in text_to_check:
            return True

    return False


def classify_buyer_tier(lead: Lead) -> tuple[str, float]:
    """
    Classify a lead into buyer tiers with likelihood score.

    Returns:
        (tier, likelihood) where tier is A/B/C/excluded
    """
    country = lead.organization.country
    org_type = lead.organization.org_type
    is_caribbean = is_caribbean_country(country)
    is_exporter = has_exporter_signals(lead)

    likelihood = 0.5  # Start neutral

    # Exporter signals are very negative
    if is_exporter:
        likelihood -= 0.3

    # Caribbean location is very positive
    if is_caribbean:
        likelihood += 0.3

    # Buyer-friendly org types are positive
    if org_type in BUYER_ORG_TYPES:
        likelihood += 0.2

    # Manufacturers are neutral unless clearly local
    if org_type in MANUFACTURER_TYPES:
        if is_caribbean:
            likelihood += 0.1  # Local manufacturer is OK
        else:
            likelihood -= 0.1  # Foreign manufacturer is suspicious

    # Unknown country is slightly negative
    if not country or country.lower() in {"unknown", ""}:
        likelihood -= 0.1

    # Clamp to 0-1
    likelihood = max(0.0, min(1.0, likelihood))

    # Determine tier based on likelihood and flags
    if is_exporter and not is_caribbean:
        tier = "excluded"
    elif likelihood >= 0.7:
        tier = "A"
    elif likelihood >= 0.4:
        tier = "B"
    elif likelihood >= 0.2:
        tier = "C"
    else:
        tier = "excluded"

    return tier, likelihood


def apply_buyer_gate(leads: list[Lead]) -> list[Lead]:
    """
    Apply tiered buyer classification.

    Instead of dropping leads, classify them into tiers:
    - Tier A: High confidence buyers (keep)
    - Tier B: Probable buyers (keep, may need review)
    - Tier C: Needs verification (keep, flagged for review)
    - Excluded: Non-buyers (drop)

    Returns list with only excluded leads removed.
    """
    filtered = []
    tier_counts = {"A": 0, "B": 0, "C": 0, "excluded": 0}

    for lead in leads:
        tier, likelihood = classify_buyer_tier(lead)
        lead.buyer_tier = tier
        lead.buyer_likelihood = likelihood

        # Flag Tier B and C for review
        if tier in ("B", "C"):
            lead.needs_review = True

        tier_counts[tier] += 1

        # Only exclude the clearly non-buyers
        if tier != "excluded":
            filtered.append(lead)

    # Log tier distribution
    print(
        f"  Tier distribution: A={tier_counts['A']}, B={tier_counts['B']}, "
        f"C={tier_counts['C']}, excluded={tier_counts['excluded']}"
    )

    return filtered


def score_lead(lead: Lead) -> float:
    """
    Score a lead based on evidence quality and buyer relevance.
    Returns 0-1.

    Scoring factors:
    - Contact quality (email, phone, role)
    - Evidence quality (multiple sources)
    - Caribbean location (bonus)
    - Hotel/resort/hurricane mentions (bonus)
    - Exporter signals (penalty)
    - Domain misalignment (penalty)
    """
    score = 0.0

    # +0.20 if email found with evidence
    has_email = any(ch.type == "email" and ch.evidence for c in lead.contacts for ch in c.channels)
    if has_email:
        score += 0.20

    # +0.15 if role matches target roles
    target_roles = {"owner", "exec", "founder", "ceo", "director", "procurement", "sales"}
    for contact in lead.contacts:
        if contact.role_category in target_roles:
            score += 0.15
            break

    # +0.15 if multiple evidence sources
    evidence_count = len(lead.evidence) + len(lead.organization.evidence)
    if evidence_count >= 2:
        score += 0.15

    # +0.10 if phone found
    has_phone = any(ch.type == "phone" for c in lead.contacts for ch in c.channels)
    if has_phone:
        score += 0.10

    # +0.05 if website exists
    if lead.organization.website:
        score += 0.05

    # +0.05 if description exists
    if lead.organization.description:
        score += 0.05

    # === BUYER RELEVANCE BONUSES ===

    # +0.20 if Caribbean-based
    if is_caribbean_country(lead.organization.country):
        score += 0.20

    # +0.10 if mentions hotels/resorts/hurricane
    desc = (lead.organization.description or "").lower()
    industries = " ".join(lead.organization.industries).lower()
    combined_text = f"{desc} {industries}"

    hotel_signals = ["hotel", "resort", "hospitality", "tourism", "commercial"]
    hurricane_signals = ["hurricane", "impact", "storm", "cyclone"]

    if any(sig in combined_text for sig in hotel_signals):
        score += 0.10

    if any(sig in combined_text for sig in hurricane_signals):
        score += 0.10

    # === PENALTIES ===

    # -0.25 if domain not aligned
    if not lead.domain_aligned:
        score -= 0.25

    # -0.20 if exporter signals detected
    if has_exporter_signals(lead):
        score -= 0.20

    # -0.10 if country is unknown (less trustworthy)
    if not lead.organization.country or lead.organization.country.lower() in {"unknown", ""}:
        score -= 0.10

    return max(min(score, 1.0), 0.0)  # Clamp to 0-1


def score_all_leads(leads: list[Lead]) -> list[Lead]:
    """Score all leads and update their confidence."""
    for lead in leads:
        lead.confidence = score_lead(lead)
    return leads
