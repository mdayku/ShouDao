"""
ShouDao CSV exporter - derives CSV from canonical Lead JSON.
"""

import csv
import json
from pathlib import Path
from typing import TextIO

from .models import Lead, RunResult

# CSV column order (stable schema - derived from Lead model)
CSV_COLUMNS = [
    # Organization
    "organization_name",
    "org_type",
    "industries",
    "country",
    "region",
    "city",
    "website",
    "size_indicator",
    "description",
    # Contact (primary)
    "contact_name",
    "contact_title",
    "role_category",
    "email",
    "phone",
    "linkedin",
    "contact_page",
    # Evidence + Quality
    "evidence_urls",
    "evidence_snippets",
    "confidence",
    "dedupe_key",
    # Approach Advice
    "recommended_angle",
    "recommended_first_offer",
    "qualifying_question",
]


def lead_to_row(lead: Lead) -> dict:
    """Convert a Lead to a flat CSV row dict."""
    contact = lead.get_primary_contact()

    # Extract channels by type
    email = lead.get_primary_email() or ""
    phone = lead.get_primary_phone() or ""
    linkedin = ""
    contact_page = ""

    if contact:
        for ch in contact.channels:
            if ch.type == "linkedin" and not linkedin:
                linkedin = ch.value
            if ch.type == "contact_page" and not contact_page:
                contact_page = ch.value

    # Collect evidence
    evidence_urls = lead.get_evidence_urls()
    evidence_snippets = []
    for e in lead.evidence:
        if e.snippet:
            evidence_snippets.append(e.snippet)
    for e in lead.organization.evidence:
        if e.snippet:
            evidence_snippets.append(e.snippet)

    return {
        # Organization
        "organization_name": lead.organization.name,
        "org_type": lead.organization.org_type,
        "industries": ";".join(lead.organization.industries),
        "country": lead.organization.country or "",
        "region": lead.organization.region or "",
        "city": lead.organization.city or "",
        "website": str(lead.organization.website) if lead.organization.website else "",
        "size_indicator": lead.organization.size_indicator or "",
        "description": lead.organization.description or "",
        # Contact
        "contact_name": contact.name if contact else "",
        "contact_title": contact.title if contact else "",
        "role_category": contact.role_category if contact else "",
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "contact_page": contact_page,
        # Evidence
        "evidence_urls": ";".join(evidence_urls),
        "evidence_snippets": " | ".join(evidence_snippets[:3]),
        "confidence": f"{lead.confidence:.2f}",
        "dedupe_key": lead.dedupe_key or "",
        # Advice
        "recommended_angle": lead.advice.recommended_angle if lead.advice else "",
        "recommended_first_offer": lead.advice.recommended_first_offer if lead.advice else "",
        "qualifying_question": lead.advice.qualifying_question if lead.advice else "",
    }


def export_csv(leads: list[Lead], output: Path | TextIO) -> int:
    """Export leads to CSV file. Returns number of rows written."""
    rows = [lead_to_row(lead) for lead in leads]

    if isinstance(output, Path):
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def export_json(leads: list[Lead], output: Path) -> int:
    """Export leads to JSON file (canonical format)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    data = [lead.model_dump(mode="json") for lead in leads]
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return len(data)


def generate_report(result: RunResult, output: Path) -> None:
    """Generate a markdown run report."""
    output.parent.mkdir(parents=True, exist_ok=True)

    # Count by country and type
    by_country: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_industry: dict[str, int] = {}

    for lead in result.leads:
        country = lead.organization.country or "Unknown"
        by_country[country] = by_country.get(country, 0) + 1
        by_type[lead.organization.org_type] = by_type.get(lead.organization.org_type, 0) + 1
        for ind in lead.organization.industries:
            by_industry[ind] = by_industry.get(ind, 0) + 1

    report = f"""# ShouDao Run Report

## Run Info
| Field | Value |
|---|---|
| Run ID | {result.run_id} |
| Started | {result.started_at.isoformat()} |
| Finished | {result.finished_at.isoformat() if result.finished_at else "In progress"} |
| Sources Fetched | {result.sources_fetched} |
| Domains Hit | {result.domains_hit} |
| Total Leads | {len(result.leads)} |

## Prompt
```
{result.config.prompt}
```

## Leads by Country
| Country | Count |
|---|---|
"""
    for country, count in sorted(by_country.items(), key=lambda x: -x[1]):
        report += f"| {country} | {count} |\n"

    report += """
## Leads by Type
| Type | Count |
|---|---|
"""
    for otype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        report += f"| {otype} | {count} |\n"

    if by_industry:
        report += """
## Leads by Industry
| Industry | Count |
|---|---|
"""
        for ind, count in sorted(by_industry.items(), key=lambda x: -x[1]):
            report += f"| {ind} | {count} |\n"

    if result.errors:
        report += "\n## Errors\n"
        for err in result.errors:
            report += f"- {err}\n"

    with open(output, "w", encoding="utf-8") as f:
        f.write(report)
