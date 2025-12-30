"""Tests for dedupe and scoring."""

from shoudao.dedupe import (
    compute_dedupe_key,
    dedupe_leads,
    normalize_domain,
    normalize_org_name,
    score_lead,
)
from shoudao.models import Evidence, Lead, Organization


class TestNormalizeDomain:
    """Tests for normalize_domain function."""

    def test_normalize_url(self) -> None:
        """Test normalizing a full URL."""
        assert normalize_domain("https://www.example.com/page") == "example.com"

    def test_normalize_domain_only(self) -> None:
        """Test normalizing a domain string."""
        assert normalize_domain("www.example.com") == "example.com"

    def test_normalize_empty(self) -> None:
        """Test normalizing empty string."""
        assert normalize_domain("") == ""

    def test_normalize_no_www(self) -> None:
        """Test domain without www."""
        assert normalize_domain("https://example.com") == "example.com"


class TestNormalizeOrgName:
    """Tests for normalize_org_name function."""

    def test_normalize_basic(self) -> None:
        """Test basic name normalization."""
        assert normalize_org_name("Acme") == "acme"

    def test_normalize_suffix(self) -> None:
        """Test removing common suffixes."""
        assert normalize_org_name("Acme LLC") == "acme"
        assert normalize_org_name("Acme Inc") == "acme"
        assert normalize_org_name("Acme Ltd") == "acme"
        assert normalize_org_name("Acme Corp") == "acme"  # Corp is also stripped

    def test_normalize_punctuation(self) -> None:
        """Test removing punctuation."""
        # Punctuation removed, whitespace collapsed
        assert normalize_org_name("Acme & Sons") == "acme sons"


class TestComputeDedupeKey:
    """Tests for compute_dedupe_key function."""

    def test_dedupe_key_from_website(self, sample_lead: Lead) -> None:
        """Test computing dedupe key from website."""
        key = compute_dedupe_key(sample_lead)
        assert key == "acme.com"

    def test_dedupe_key_fallback(self, sample_evidence: Evidence) -> None:
        """Test fallback to name + country when no website."""
        org = Organization(
            name="Test Organization",  # No suffix to strip
            country="USA",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        key = compute_dedupe_key(lead)
        assert key == "test organization|usa"


class TestDedupe:
    """Tests for dedupe_leads function."""

    def test_dedupe_identical(self, sample_lead: Lead) -> None:
        """Test deduping identical leads."""
        leads = dedupe_leads([sample_lead, sample_lead])
        assert len(leads) == 1

    def test_dedupe_different(self, sample_lead: Lead, sample_evidence: Evidence) -> None:
        """Test keeping different leads."""
        org2 = Organization(
            name="Other Corp",
            website="https://other.com",
            evidence=[sample_evidence],
        )
        lead2 = Lead(organization=org2)

        leads = dedupe_leads([sample_lead, lead2])
        assert len(leads) == 2


class TestScoreLead:
    """Tests for score_lead function."""

    def test_score_with_email(self, sample_lead: Lead) -> None:
        """Test scoring a lead with email."""
        score, contributions = score_lead(sample_lead)
        assert score > 0.5  # Has email, role, website
        assert "email_with_evidence" in contributions

    def test_score_minimal(self, sample_evidence: Evidence) -> None:
        """Test scoring a minimal lead."""
        org = Organization(name="Minimal", evidence=[sample_evidence])
        lead = Lead(organization=org)
        score, contributions = score_lead(lead)
        assert score < 0.5  # No contacts, no website
        assert isinstance(contributions, dict)
