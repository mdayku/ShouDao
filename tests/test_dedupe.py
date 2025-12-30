"""Tests for dedupe and scoring."""

from shoudao.dedupe import (
    apply_buyer_gate,
    classify_buyer_tier,
    compute_dedupe_key,
    dedupe_all_contacts,
    dedupe_contacts_by_email,
    dedupe_leads,
    is_caribbean_country,
    normalize_domain,
    normalize_org_name,
    score_lead,
)
from shoudao.models import Contact, ContactChannel, Evidence, Lead, Organization


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

    def test_score_contributions_complete(self, sample_lead: Lead) -> None:
        """Test that score contributions are properly populated."""
        score, contributions = score_lead(sample_lead)
        # Check that contributions are numeric
        for key, value in contributions.items():
            assert isinstance(value, (int, float)), f"{key} should be numeric"
        # Check that positive and negative contributions are possible
        assert any(v > 0 for v in contributions.values()), "Should have positive contributions"

    def test_score_caribbean_bonus(self, sample_evidence: Evidence) -> None:
        """Test Caribbean location gives a bonus."""
        org = Organization(name="Caribbean Co", country="Jamaica", evidence=[sample_evidence])
        lead = Lead(organization=org)
        score, contributions = score_lead(lead)
        assert "caribbean_location" in contributions
        assert contributions["caribbean_location"] > 0

    def test_score_domain_misalignment_penalty(self, sample_evidence: Evidence) -> None:
        """Test domain misalignment gives a penalty."""
        org = Organization(name="Test Co", evidence=[sample_evidence])
        lead = Lead(organization=org, domain_aligned=False)
        score, contributions = score_lead(lead)
        assert "domain_misaligned" in contributions
        assert contributions["domain_misaligned"] < 0


class TestDedupeContactsByEmail:
    """Tests for duplicate contact detection (Task 7.1.3)."""

    def test_removes_duplicate_emails(self, sample_evidence: Evidence) -> None:
        """Test that duplicate emails are removed."""
        channel1 = ContactChannel(
            type="email", value="test@example.com", evidence=[sample_evidence]
        )
        channel2 = ContactChannel(
            type="email", value="test@example.com", evidence=[sample_evidence]
        )
        contact1 = Contact(name="John", channels=[channel1])
        contact2 = Contact(name="John Duplicate", channels=[channel2])

        org = Organization(name="Test", evidence=[sample_evidence])
        lead = Lead(organization=org, contacts=[contact1, contact2])

        result = dedupe_contacts_by_email(lead)
        assert len(result.contacts) == 1
        assert result.contacts[0].name == "John"  # Keeps first

    def test_keeps_different_emails(self, sample_evidence: Evidence) -> None:
        """Test that different emails are kept."""
        channel1 = ContactChannel(
            type="email", value="john@example.com", evidence=[sample_evidence]
        )
        channel2 = ContactChannel(
            type="email", value="jane@example.com", evidence=[sample_evidence]
        )
        contact1 = Contact(name="John", channels=[channel1])
        contact2 = Contact(name="Jane", channels=[channel2])

        org = Organization(name="Test", evidence=[sample_evidence])
        lead = Lead(organization=org, contacts=[contact1, contact2])

        result = dedupe_contacts_by_email(lead)
        assert len(result.contacts) == 2

    def test_case_insensitive_email_match(self, sample_evidence: Evidence) -> None:
        """Test that email matching is case-insensitive."""
        channel1 = ContactChannel(
            type="email", value="Test@Example.com", evidence=[sample_evidence]
        )
        channel2 = ContactChannel(
            type="email", value="test@example.com", evidence=[sample_evidence]
        )
        contact1 = Contact(name="John", channels=[channel1])
        contact2 = Contact(name="John Again", channels=[channel2])

        org = Organization(name="Test", evidence=[sample_evidence])
        lead = Lead(organization=org, contacts=[contact1, contact2])

        result = dedupe_contacts_by_email(lead)
        assert len(result.contacts) == 1

    def test_keeps_contacts_without_email(self, sample_evidence: Evidence) -> None:
        """Test that contacts without email are kept."""
        channel1 = ContactChannel(type="phone", value="+1234567890", evidence=[sample_evidence])
        channel2 = ContactChannel(type="phone", value="+1234567891", evidence=[sample_evidence])
        contact1 = Contact(name="John", channels=[channel1])
        contact2 = Contact(name="Jane", channels=[channel2])

        org = Organization(name="Test", evidence=[sample_evidence])
        lead = Lead(organization=org, contacts=[contact1, contact2])

        result = dedupe_contacts_by_email(lead)
        assert len(result.contacts) == 2

    def test_dedupe_all_contacts_batch(self, sample_evidence: Evidence) -> None:
        """Test dedupe_all_contacts works on list of leads."""
        channel = ContactChannel(type="email", value="dup@test.com", evidence=[sample_evidence])
        contact1 = Contact(name="C1", channels=[channel])
        contact2 = Contact(name="C2", channels=[channel])

        org = Organization(name="Test", evidence=[sample_evidence])
        lead = Lead(organization=org, contacts=[contact1, contact2])

        results = dedupe_all_contacts([lead])
        assert len(results) == 1
        assert len(results[0].contacts) == 1


class TestIsCaribbeanCountry:
    """Tests for Caribbean country detection."""

    def test_english_caribbean(self) -> None:
        """Test English-speaking Caribbean countries."""
        assert is_caribbean_country("Jamaica")
        assert is_caribbean_country("Barbados")
        assert is_caribbean_country("Trinidad and Tobago")

    def test_spanish_caribbean(self) -> None:
        """Test Spanish-speaking Caribbean countries."""
        assert is_caribbean_country("Puerto Rico")
        assert is_caribbean_country("Dominican Republic")

    def test_french_caribbean(self) -> None:
        """Test French-speaking Caribbean countries."""
        assert is_caribbean_country("Haiti")
        assert is_caribbean_country("Martinique")
        assert is_caribbean_country("Guadeloupe")

    def test_dutch_caribbean(self) -> None:
        """Test Dutch-speaking Caribbean countries."""
        assert is_caribbean_country("Aruba")
        assert is_caribbean_country("Curacao")

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        assert is_caribbean_country("JAMAICA")
        assert is_caribbean_country("jamaica")
        assert is_caribbean_country("Jamaica")

    def test_non_caribbean(self) -> None:
        """Test non-Caribbean countries return False."""
        assert not is_caribbean_country("United States")
        assert not is_caribbean_country("China")
        assert not is_caribbean_country("Germany")

    def test_empty_or_none(self) -> None:
        """Test empty/None handling."""
        assert not is_caribbean_country(None)
        assert not is_caribbean_country("")


class TestClassifyBuyerTier:
    """Tests for buyer tier classification."""

    def test_tier_a_caribbean_distributor(self, sample_evidence: Evidence) -> None:
        """Test that Caribbean distributors get Tier A."""
        org = Organization(
            name="Caribbean Windows Ltd",
            org_type="distributor",
            country="Jamaica",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        tier, likelihood = classify_buyer_tier(lead)
        assert tier == "A"
        assert likelihood >= 0.7

    def test_tier_excluded_exporter(self, sample_evidence: Evidence) -> None:
        """Test that foreign exporters are excluded."""
        org = Organization(
            name="China Export Trading Company",
            org_type="manufacturer",
            country="China",
            description="Export worldwide, international trading",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        tier, likelihood = classify_buyer_tier(lead)
        assert tier == "excluded"

    def test_tier_b_uncertain(self, sample_evidence: Evidence) -> None:
        """Test that uncertain leads get Tier B."""
        org = Organization(
            name="Unknown Co",
            org_type="other",
            country="Unknown",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        tier, likelihood = classify_buyer_tier(lead)
        assert tier in ("B", "C")  # Uncertain leads


class TestApplyBuyerGate:
    """Tests for buyer gate application."""

    def test_keeps_tier_a_leads(self, sample_evidence: Evidence) -> None:
        """Test that Tier A leads are kept."""
        org = Organization(
            name="Jamaica Distributors",
            org_type="distributor",
            country="Jamaica",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        results = apply_buyer_gate([lead])
        assert len(results) == 1
        assert results[0].buyer_tier == "A"

    def test_drops_excluded_leads(self, sample_evidence: Evidence) -> None:
        """Test that excluded leads are dropped."""
        org = Organization(
            name="China Export Co",
            org_type="manufacturer",
            country="China",
            description="International export trading company",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        results = apply_buyer_gate([lead])
        assert len(results) == 0

    def test_flags_tier_b_for_review(self, sample_evidence: Evidence) -> None:
        """Test that Tier B leads are flagged for review."""
        org = Organization(
            name="Unknown Caribbean Co",
            org_type="other",
            country="Barbados",
            evidence=[sample_evidence],
        )
        lead = Lead(organization=org)
        results = apply_buyer_gate([lead])
        if results and results[0].buyer_tier == "B":
            assert results[0].needs_review is True
