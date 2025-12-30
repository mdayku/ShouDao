"""
ShouDao dedupe + scoring engine.
Includes buyer-only gate and Caribbean country filter.
"""

from datetime import datetime
from urllib.parse import urlparse

from .models import AgeBand, Candidate, CandidateTier, Lead, SalaryBand

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


def score_lead(lead: Lead) -> tuple[float, dict[str, float]]:
    """
    Score a lead based on evidence quality and buyer relevance.
    Returns (score 0-1, contributions dict).

    Scoring factors:
    - Contact quality (email, phone, role)
    - Evidence quality (multiple sources)
    - Caribbean location (bonus)
    - Hotel/resort/hurricane mentions (bonus)
    - Exporter signals (penalty)
    - Domain misalignment (penalty)
    """
    score = 0.0
    contributions: dict[str, float] = {}

    # +0.20 if email found with evidence
    has_email = any(ch.type == "email" and ch.evidence for c in lead.contacts for ch in c.channels)
    if has_email:
        score += 0.20
        contributions["email_with_evidence"] = 0.20

    # +0.15 if role matches target roles
    target_roles = {"owner", "exec", "founder", "ceo", "director", "procurement", "sales"}
    for contact in lead.contacts:
        if contact.role_category in target_roles:
            score += 0.15
            contributions["target_role"] = 0.15
            break

    # +0.15 if multiple evidence sources
    evidence_count = len(lead.evidence) + len(lead.organization.evidence)
    if evidence_count >= 2:
        score += 0.15
        contributions["multiple_evidence"] = 0.15

    # +0.10 if phone found
    has_phone = any(ch.type == "phone" for c in lead.contacts for ch in c.channels)
    if has_phone:
        score += 0.10
        contributions["phone"] = 0.10

    # +0.05 if website exists
    if lead.organization.website:
        score += 0.05
        contributions["website"] = 0.05

    # +0.05 if description exists
    if lead.organization.description:
        score += 0.05
        contributions["description"] = 0.05

    # === BUYER RELEVANCE BONUSES ===

    # +0.20 if Caribbean-based
    if is_caribbean_country(lead.organization.country):
        score += 0.20
        contributions["caribbean_location"] = 0.20

    # +0.10 if mentions hotels/resorts/hurricane
    desc = (lead.organization.description or "").lower()
    industries = " ".join(lead.organization.industries).lower()
    combined_text = f"{desc} {industries}"

    hotel_signals = ["hotel", "resort", "hospitality", "tourism", "commercial"]
    hurricane_signals = ["hurricane", "impact", "storm", "cyclone"]

    if any(sig in combined_text for sig in hotel_signals):
        score += 0.10
        contributions["hotel_resort_signal"] = 0.10

    if any(sig in combined_text for sig in hurricane_signals):
        score += 0.10
        contributions["hurricane_signal"] = 0.10

    # === PENALTIES ===

    # -0.25 if domain not aligned
    if not lead.domain_aligned:
        score -= 0.25
        contributions["domain_misaligned"] = -0.25

    # -0.20 if exporter signals detected
    if has_exporter_signals(lead):
        score -= 0.20
        contributions["exporter_signals"] = -0.20

    # -0.10 if country is unknown (less trustworthy)
    if not lead.organization.country or lead.organization.country.lower() in {"unknown", ""}:
        score -= 0.10
        contributions["unknown_country"] = -0.10

    return max(min(score, 1.0), 0.0), contributions  # Clamp to 0-1


def score_all_leads(leads: list[Lead]) -> list[Lead]:
    """Score all leads and update their confidence + score contributions."""
    for lead in leads:
        score, contributions = score_lead(lead)
        lead.confidence = score
        lead.score_contributions = contributions
    return leads


def dedupe_contacts_by_email(lead: Lead) -> Lead:
    """
    Remove duplicate contacts from a lead based on email address.
    Keeps the first contact for each email (Task 7.1.3).
    """
    seen_emails: set[str] = set()
    unique_contacts = []

    for contact in lead.contacts:
        # Get all emails for this contact
        contact_emails = [ch.value.lower() for ch in contact.channels if ch.type == "email"]

        # Check if any email is a duplicate
        is_duplicate = any(email in seen_emails for email in contact_emails)

        if not is_duplicate:
            unique_contacts.append(contact)
            seen_emails.update(contact_emails)

    lead.contacts = unique_contacts
    return lead


def dedupe_all_contacts(leads: list[Lead]) -> list[Lead]:
    """Dedupe contacts within each lead by email."""
    return [dedupe_contacts_by_email(lead) for lead in leads]


# =============================================================================
# CANDIDATE SCORING (Gauntlet Talent Discovery)
# =============================================================================

# Known "elite" universities for CS/STEM (highest CCAT correlation)
TOP_CS_UNIVERSITIES = {
    # US Elite
    "stanford",
    "mit",
    "cmu",
    "carnegie mellon",
    "berkeley",
    "uc berkeley",
    "cornell",
    "harvard",
    "princeton",
    "caltech",
    "georgia tech",
    "illinois",
    "uiuc",
    "michigan",
    "washington",
    "columbia",
    "yale",
    "ucla",
    "usc",
    "nyu",
    "penn",
    "upenn",
    "brown",
    "duke",
    "northwestern",
    "purdue",
    "texas",
    "ut austin",
    # International Elite
    "waterloo",
    "toronto",
    "oxford",
    "cambridge",
    "imperial",
    "eth",
    "epfl",
    "tsinghua",
    "peking",
    "nus",
    "nanyang",
    "iit",
    "technion",
}

# Good universities - still strong signal, slightly lower bonus
MID_TIER_CS_UNIVERSITIES = {
    # US Strong Programs
    "wisconsin",
    "uw madison",
    "maryland",
    "umd",
    "virginia",
    "uva",
    "ohio state",
    "penn state",
    "minnesota",
    "colorado",
    "cu boulder",
    "rutgers",
    "rice",
    "vanderbilt",
    "notre dame",
    "boston university",
    "bu",
    "northeastern",
    "rochester",
    "rpi",
    "wpi",
    "santa clara",
    "uc san diego",
    "ucsd",
    "uc irvine",
    "uci",
    "uc davis",
    "uc santa barbara",
    "arizona state",
    "asu",
    "arizona",
    "utah",
    "oregon",
    "nc state",
    "virginia tech",
    "unc",
    "north carolina",
    "florida",
    "uf",
    "miami",
    "emory",
    "tulane",
    "case western",
    "stony brook",
    "buffalo",
    # CSU/State Schools with good CS
    "san jose state",
    "sjsu",
    "cal poly",
    "san diego state",
    "sdsu",
    "texas a&m",
    "tamu",
    "texas tech",
    "ut dallas",
    "utd",
    "ut arlington",
    "iowa state",
    "kansas",
    "missouri",
    "indiana",
    "clemson",
    "auburn",
    # International Good
    "mcgill",
    "ubc",
    "british columbia",
    "alberta",
    "montreal",
    "edinburgh",
    "manchester",
    "ucl",
    "kings college",
    "warwick",
    "bristol",
    "tu munich",
    "rwth aachen",
    "tu berlin",
    "kit",
    "heidelberg",
    "delft",
    "eindhoven",
    "amsterdam",
    "leiden",
    "zurich",
    "tokyo",
    "kyoto",
    "osaka",
    "seoul national",
    "kaist",
    "postech",
    "melbourne",
    "sydney",
    "unsw",
    "anu",
    "queensland",
    "tel aviv",
    "hebrew university",
    "weizmann",
    # Bootcamps/Accelerators (strong signal for self-starters)
    "hack reactor",
    "app academy",
    "fullstack",
    "flatiron",
    "lambda school",
    "codesmith",
    "recurse center",
    "bradfield",
}

# Companies known for high compensation (>$150k likely)
HIGH_COMP_COMPANIES = {
    "google",
    "meta",
    "facebook",
    "amazon",
    "apple",
    "microsoft",
    "netflix",
    "stripe",
    "openai",
    "anthropic",
    "deepmind",
    "nvidia",
    "tesla",
    "uber",
    "airbnb",
    "coinbase",
    "databricks",
    "snowflake",
    "palantir",
    "salesforce",
    "linkedin",
    "twitter",
    "tiktok",
    "bytedance",
    "figma",
    "notion",
    "discord",
    "doordash",
    "instacart",
    "robinhood",
    "plaid",
    "ramp",
    "brex",
}

# Roles that typically pay >$150k
HIGH_COMP_ROLES = {
    "staff",
    "senior staff",
    "principal",
    "director",
    "vp",
    "head of",
    "lead",
    "manager",
}

# Startup indicators (likely lower salary than big tech)
STARTUP_INDICATORS = {
    "stealth",
    "startup",
    "early stage",
    "seed",
    "series a",
    "pre-seed",
    "founder",
    "co-founder",
    "founding",
    "senior manager",
}


# Cap years of experience for scoring purposes
# Beyond 10 years, no additional credit (diminishing returns for Gauntlet fit)
MAX_YOE_FOR_SCORING = 10


def estimate_salary_band(candidate: Candidate) -> SalaryBand:
    """
    Estimate salary band based on company, role, and experience.

    Logic:
    - FAANG/top-tier companies at any level → likely >$150k
    - Senior/staff roles anywhere → likely >$150k
    - Startups get a discount (equity vs cash tradeoff)
    - Junior/mid roles at startups/smaller cos → likely <$150k
    - Cap years at 10 for estimation (beyond that, same treatment)
    - Unknown → unknown
    """
    company = (candidate.current_company or "").lower()
    role = (candidate.current_role or "").lower()
    # Cap years for salary estimation
    years = min(candidate.years_experience or 0, MAX_YOE_FOR_SCORING)

    # Check for high-comp company
    is_high_comp_company = any(c in company for c in HIGH_COMP_COMPANIES)

    # Check for high-comp role
    is_high_comp_role = any(r in role for r in HIGH_COMP_ROLES)

    # Check for startup (likely lower cash comp, more equity)
    is_startup = any(s in company for s in STARTUP_INDICATORS) or any(
        s in role for s in STARTUP_INDICATORS
    )

    # If at a top company, likely high comp
    if is_high_comp_company:
        if is_high_comp_role or years >= 5:
            return "200k_plus"
        else:
            return "150k_200k"

    # Startups typically pay less cash (equity tradeoff)
    if is_startup:
        if years >= 10:
            return "150k_200k"  # Senior startup folks still make decent money
        elif years >= 5:
            return "100k_150k"
        else:
            return "under_100k"

    # If senior role at non-startup
    if is_high_comp_role:
        return "150k_200k"

    # Years of experience heuristic (capped at 10)
    if years >= 7:
        return "150k_200k"
    elif years >= 4:
        return "100k_150k"
    elif years >= 1:
        return "under_100k"

    # Can't determine
    return "unknown"


def estimate_age(candidate: Candidate) -> int | None:
    """
    Estimate age from graduation year or years of experience.

    Logic:
    - If graduation_year known: age = current_year - graduation_year + 22
    - If years_experience known: age = 22 + min(years, 25) (cap at 25 for estimation)
    - Otherwise: None

    Returns:
        Estimated age in years, or None if cannot estimate.
    """
    current_year = datetime.now().year

    # Prefer graduation year (more accurate)
    if candidate.graduation_year:
        # Assume graduated at 22 (typical 4-year degree)
        estimated_birth_year = candidate.graduation_year - 22
        return current_year - estimated_birth_year

    # Fall back to years of experience (cap at 25 to avoid absurd ages)
    if candidate.years_experience:
        # Assume started working at 22, cap experience at 25 years
        capped_years = min(candidate.years_experience, 25)
        return 22 + capped_years

    return None


def classify_age_band(age: int | None) -> AgeBand:
    """
    Classify age into bands based on Gauntlet demographics.

    Gauntlet mean age ~30, std dev ~6-7
    - young (<24): May lack experience, but high potential
    - optimal (24-36): Sweet spot for the program
    - mature (36-42): Good if signals are strong
    - senior (>42): Higher bar needed, more risk-averse

    Args:
        age: Estimated age in years, or None.

    Returns:
        Age band classification.
    """
    if age is None:
        return "unknown"

    if age < 24:
        return "young"
    elif 24 <= age <= 36:
        return "optimal"
    elif 36 < age <= 42:
        return "mature"
    else:
        return "senior"


def score_candidate(candidate: Candidate) -> tuple[float, dict[str, float]]:
    """
    Score a candidate based on Gauntlet qualification signals.

    Returns (score 0-1, contributions dict).

    Scoring factors:
    - CS degree from good school (+0.20)
    - Engineering experience 2+ years (+0.20)
    - Public AI/LLM projects (+0.25)
    - Build-in-public activity (+0.15)
    - Multiple public repos (+0.10)
    - Salary likely <$150k (+0.10)
    """
    score = 0.0
    contributions: dict[str, float] = {}

    # Education signals
    degree = (candidate.degree_signal or "").lower()
    university = (candidate.university or "").lower()

    # Detect degree level (PhD > Masters > Bachelors)
    has_phd = any(kw in degree for kw in ["phd", "ph.d", "doctorate", "doctor of"])
    has_masters = any(kw in degree for kw in ["master", "ms ", "m.s.", "msc", "mba", "meng"])

    # Detect CS/technical field
    has_cs = any(
        kw in degree
        for kw in ["cs", "computer", "software", "electrical", "math", "physics", "engineering"]
    )

    # School tier
    is_top_school = any(u in university for u in TOP_CS_UNIVERSITIES)
    is_mid_school = any(u in university for u in MID_TIER_CS_UNIVERSITIES)

    # Scoring: School tier + Degree level + Field
    # Top school + PhD + CS = highest (0.30)
    # Top school + Masters + CS = 0.25
    # Top school + Bachelors + CS = 0.20
    # Mid school follows similar pattern but -0.05
    if is_top_school:
        if has_phd and has_cs:
            score += 0.30
            contributions["phd_cs_top_school"] = 0.30
        elif has_masters and has_cs:
            score += 0.25
            contributions["masters_cs_top_school"] = 0.25
        elif has_cs:
            score += 0.20
            contributions["cs_top_school"] = 0.20
        elif has_phd or has_masters:
            score += 0.15
            contributions["grad_top_school"] = 0.15
        else:
            score += 0.10
            contributions["top_school"] = 0.10
    elif is_mid_school:
        if has_phd and has_cs:
            score += 0.25
            contributions["phd_cs_mid_school"] = 0.25
        elif has_masters and has_cs:
            score += 0.20
            contributions["masters_cs_mid_school"] = 0.20
        elif has_cs:
            score += 0.15
            contributions["cs_mid_school"] = 0.15
        elif has_phd or has_masters:
            score += 0.12
            contributions["grad_mid_school"] = 0.12
        else:
            score += 0.08
            contributions["mid_school"] = 0.08
    elif has_cs:
        # CS degree from unknown school
        if has_phd:
            score += 0.20
            contributions["phd_cs"] = 0.20
        elif has_masters:
            score += 0.15
            contributions["masters_cs"] = 0.15
        else:
            score += 0.10
            contributions["cs_degree"] = 0.10

    # Engineering experience (cap at 10 years for scoring)
    years = min(candidate.years_experience or 0, MAX_YOE_FOR_SCORING)
    if years >= 2:
        score += 0.20
        contributions["engineering_experience"] = 0.20
    elif years >= 1:
        score += 0.10
        contributions["some_experience"] = 0.10

    # AI/LLM project signal
    if candidate.ai_signal_score >= 0.7:
        score += 0.25
        contributions["strong_ai_signal"] = 0.25
    elif candidate.ai_signal_score >= 0.4:
        score += 0.15
        contributions["some_ai_signal"] = 0.15

    # Build in public
    if candidate.build_in_public_score >= 0.6:
        score += 0.15
        contributions["builds_in_public"] = 0.15
    elif candidate.build_in_public_score >= 0.3:
        score += 0.08
        contributions["some_public_work"] = 0.08

    # Multiple public repos
    repo_count = len(candidate.public_repos)
    if repo_count >= 5:
        score += 0.10
        contributions["many_repos"] = 0.10
    elif repo_count >= 2:
        score += 0.05
        contributions["some_repos"] = 0.05

    # Salary band bonus (incentive alignment)
    salary = candidate.estimated_salary_band
    if salary == "under_100k":
        score += 0.10
        contributions["salary_incentive_aligned"] = 0.10
    elif salary == "100k_150k":
        score += 0.05
        contributions["salary_moderate"] = 0.05
    # No bonus for 150k+ (less incentive to join)

    # Contact quality bonus
    if candidate.email:
        score += 0.05
        contributions["has_email"] = 0.05
    if candidate.linkedin_url:
        score += 0.05
        contributions["has_linkedin"] = 0.05

    # Age band adjustments (Gauntlet sweet spot: mean ~30, std dev ~6-7)
    age_band = candidate.age_band
    if age_band == "optimal":
        score += 0.10
        contributions["age_optimal"] = 0.10
    elif age_band == "young":
        score -= 0.10
        contributions["age_young_penalty"] = -0.10
    elif age_band == "senior":
        score -= 0.15
        contributions["age_senior_penalty"] = -0.15
    # "mature" and "unknown" have no adjustment

    return min(max(score, 0.0), 1.0), contributions


def classify_candidate_tier(candidate: Candidate) -> CandidateTier:
    """
    Classify a candidate into fit tiers.

    Tier A: High score + either low salary OR strong AI signal (willing to pivot)
    Tier B: Good score, good potential
    Tier C: Early but promising, needs verification
    """
    score = candidate.confidence
    salary = candidate.estimated_salary_band
    ai_signal = candidate.ai_signal_score

    # Tier A paths:
    # 1. High score + not already making big money
    # 2. High score + very strong AI signal (they're building, likely to pivot)
    # 3. Very high score (0.8+) regardless of salary
    if score >= 0.6:
        if salary in ("under_100k", "100k_150k", "unknown"):
            return "A"
        # Strong AI builders are likely to take a pay cut to join Gauntlet
        if ai_signal >= 0.6:
            return "A"
        # Very high overall score overrides salary concerns
        if score >= 0.8:
            return "A"

    # Tier B: Decent score
    if score >= 0.4:
        return "B"

    # Tier C: Everyone else (contactable)
    return "C"


def score_all_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Score all candidates and update their fields."""
    for candidate in candidates:
        # Estimate age and classify band
        candidate.estimated_age = estimate_age(candidate)
        candidate.age_band = classify_age_band(candidate.estimated_age)

        # Estimate salary band
        candidate.estimated_salary_band = estimate_salary_band(candidate)

        # Score
        score, contributions = score_candidate(candidate)
        candidate.confidence = score
        candidate.score_contributions = contributions

        # Classify tier
        candidate.overall_fit_tier = classify_candidate_tier(candidate)

        # Generate why_flagged explanation
        candidate.why_flagged = _generate_why_flagged(candidate)

    return candidates


def _generate_why_flagged(candidate: Candidate) -> str:
    """Generate a human-readable explanation for why this candidate was flagged."""
    reasons = []

    if candidate.score_contributions.get("cs_top_school"):
        reasons.append(f"CS from {candidate.university or 'top school'}")
    elif candidate.score_contributions.get("cs_degree"):
        reasons.append("CS background")

    if candidate.score_contributions.get("engineering_experience"):
        years = candidate.years_experience or 0
        reasons.append(f"{years}+ years engineering")

    if candidate.score_contributions.get("strong_ai_signal"):
        reasons.append("strong AI/LLM projects")
    elif candidate.score_contributions.get("some_ai_signal"):
        reasons.append("AI project interest")

    if candidate.score_contributions.get("builds_in_public"):
        reasons.append("builds in public")

    repo_count = len(candidate.public_repos)
    if repo_count > 0:
        reasons.append(f"{repo_count} public repos")

    if candidate.estimated_salary_band in ("under_100k", "100k_150k"):
        reasons.append("salary incentive aligned")

    # Age band info
    if candidate.age_band == "optimal" and candidate.estimated_age:
        reasons.append(f"~{candidate.estimated_age}yo (optimal)")
    elif candidate.age_band == "young" and candidate.estimated_age:
        reasons.append(f"~{candidate.estimated_age}yo (young)")
    elif candidate.age_band == "mature" and candidate.estimated_age:
        reasons.append(f"~{candidate.estimated_age}yo (mature)")

    return "; ".join(reasons) if reasons else "Basic qualification signals"


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Deduplicate candidates by primary profile URL or email."""
    seen_profiles: set[str] = set()
    seen_emails: set[str] = set()
    unique = []

    for c in candidates:
        # Check profile
        profile_key = c.primary_profile.lower().rstrip("/")
        if profile_key in seen_profiles:
            continue

        # Check email
        if c.email:
            email_key = c.email.lower()
            if email_key in seen_emails:
                continue
            seen_emails.add(email_key)

        seen_profiles.add(profile_key)
        unique.append(c)

    return unique
