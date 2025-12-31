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
    """LLM-based outreach advisor using Responses API."""

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

    def _call_model(self, model: str, system_prompt: str, user_prompt: str, response_format: type):
        """Call the model with structured output. Returns parsed result or raises."""
        import json

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        if self._is_gpt5_model(model):
            # Use Responses API for GPT-5.x models
            response = self.client.responses.create(
                model=model,
                input=full_prompt,
                text={
                    "format": {"type": "json_schema", "schema": response_format.model_json_schema()}
                },
                reasoning={"effort": "none"},
            )
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

        system_prompt = (
            "You are a B2B sales advisor. Generate specific, actionable outreach advice."
        )
        user_prompt = ADVICE_PROMPT.format(
            org_name=lead.organization.name,
            org_type=lead.organization.org_type,
            industries=", ".join(lead.organization.industries) or "Unknown",
            location=location,
            size=lead.organization.size_indicator or "Unknown",
            description=lead.organization.description or "No description",
            role=role,
            seller_context=seller_context or "B2B sales",
            product_context=product_context or "B2B product/service",
        )

        # Try primary model first, then fallback
        try:
            result = self._call_model(self.model, system_prompt, user_prompt, AdviceOutput)
            return ApproachAdvice(
                recommended_angle=result.recommended_angle,
                recommended_first_offer=result.recommended_first_offer,
                qualifying_question=result.qualifying_question,
            )
        except Exception as e:
            # If using default model and it failed, try fallback
            if self.model == self.DEFAULT_MODEL:
                print(
                    f"Primary model ({self.model}) failed, trying fallback ({self.FALLBACK_MODEL}): {e}"
                )
                try:
                    result = self._call_model(
                        self.FALLBACK_MODEL, system_prompt, user_prompt, AdviceOutput
                    )
                    return ApproachAdvice(
                        recommended_angle=result.recommended_angle,
                        recommended_first_offer=result.recommended_first_offer,
                        qualifying_question=result.qualifying_question,
                    )
                except Exception as e2:
                    print(f"Fallback model also failed for {lead.organization.name}: {e2}")
            else:
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
