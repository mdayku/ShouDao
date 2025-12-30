"""
ShouDao dedupe + scoring engine.
"""

from urllib.parse import urlparse

from .models import Lead


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


def score_lead(lead: Lead) -> float:
    """Score a lead based on evidence quality. Returns 0-1."""
    score = 0.0

    # +0.25 if email found with evidence
    has_email = any(ch.type == "email" and ch.evidence for c in lead.contacts for ch in c.channels)
    if has_email:
        score += 0.25

    # +0.20 if role matches target roles
    target_roles = {"owner", "exec", "founder", "ceo", "director", "procurement", "sales"}
    for contact in lead.contacts:
        if contact.role_category in target_roles:
            score += 0.20
            break

    # +0.20 if multiple evidence sources
    evidence_count = len(lead.evidence) + len(lead.organization.evidence)
    if evidence_count >= 2:
        score += 0.20

    # +0.15 if phone found
    has_phone = any(ch.type == "phone" for c in lead.contacts for ch in c.channels)
    if has_phone:
        score += 0.15

    # +0.10 if website exists
    if lead.organization.website:
        score += 0.10

    # +0.10 if description exists
    if lead.organization.description:
        score += 0.10

    # PENALTY: -0.30 if domain not aligned (extracted from different domain than org website)
    if not lead.domain_aligned:
        score -= 0.30

    return max(min(score, 1.0), 0.0)  # Clamp to 0-1


def score_all_leads(leads: list[Lead]) -> list[Lead]:
    """Score all leads and update their confidence."""
    for lead in leads:
        lead.confidence = score_lead(lead)
    return leads
