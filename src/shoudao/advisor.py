"""
ShouDao advisor - generate outreach advice for leads.
"""

import os

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from .models import ApproachAdvice, Lead


class AdviceOutput(BaseModel):
    """Structured advice output from LLM."""

    model_config = ConfigDict(extra="forbid")

    recommended_angle: str = Field(..., min_length=1, max_length=300)
    recommended_first_offer: str = Field(..., min_length=1, max_length=200)
    qualifying_question: str = Field(..., min_length=1, max_length=200)


ADVICE_PROMPT = """Generate outreach advice for this B2B lead.

=== THE LEAD ===
Organization: {org_name}
Type: {org_type}
Industries: {industries}
Location: {location}
Size: {size}
Description: {description}
Contact Role: {role}

=== WHO IS SELLING ===
{seller_context}

=== WHAT IS BEING SOLD ===
{product_context}

=== YOUR TASK ===
Generate outreach advice specifically for selling the product/service above to this lead.

1. recommended_angle: 1-2 sentence positioning that connects the seller's offering to this lead's likely needs
2. recommended_first_offer: One specific thing to offer (NOT generic "consultation" - tie to the actual product)
3. qualifying_question: One question to determine if they're a good fit for the specific product

CRITICAL: Your advice must be about selling the SPECIFIC product above, not generic B2B software/services.
If no product context is provided, focus on the lead's industry needs.
"""


class Advisor:
    """LLM-based outreach advisor."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def generate_advice(
        self,
        lead: Lead,
        product_context: str = "",
        seller_context: str = "",
    ) -> ApproachAdvice:
        """Generate outreach advice for a single lead."""
        contact = lead.get_primary_contact()
        role = contact.role_category if contact else "other"

        location_parts = [
            lead.organization.city,
            lead.organization.region,
            lead.organization.country,
        ]
        location = ", ".join(p for p in location_parts if p) or "Unknown"

        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a B2B sales advisor. Generate specific, actionable outreach advice.",
                    },
                    {
                        "role": "user",
                        "content": ADVICE_PROMPT.format(
                            org_name=lead.organization.name,
                            org_type=lead.organization.org_type,
                            industries=", ".join(lead.organization.industries) or "Unknown",
                            location=location,
                            size=lead.organization.size_indicator or "Unknown",
                            description=lead.organization.description or "No description",
                            role=role,
                            seller_context=seller_context or "B2B sales",
                            product_context=product_context or "B2B product/service",
                        ),
                    },
                ],
                response_format=AdviceOutput,
            )
            result = completion.choices[0].message.parsed
            return ApproachAdvice(
                recommended_angle=result.recommended_angle,
                recommended_first_offer=result.recommended_first_offer,
                qualifying_question=result.qualifying_question,
            )
        except Exception as e:
            print(f"Advice generation error for {lead.organization.name}: {e}")
            # Return a minimal valid advice
            return ApproachAdvice(
                recommended_angle="Research this lead further before outreach.",
                recommended_first_offer="Offer a discovery call to understand their needs.",
                qualifying_question="What are your current priorities in this area?",
            )

    def advise_all(
        self,
        leads: list[Lead],
        product_context: str = "",
        seller_context: str = "",
    ) -> list[Lead]:
        """Generate advice for all leads."""
        for lead in leads:
            lead.advice = self.generate_advice(lead, product_context, seller_context)
        return leads
