"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from shoudao.models import (
    ApproachAdvice,
    Contact,
    ContactChannel,
    Evidence,
    Lead,
    Organization,
    RunConfig,
)


class TestEvidence:
    """Tests for Evidence model."""

    def test_valid_evidence(self) -> None:
        """Test creating valid evidence."""
        ev = Evidence(url="https://example.com", snippet="test snippet")
        assert str(ev.url) == "https://example.com/"
        assert ev.snippet == "test snippet"

    def test_evidence_requires_url(self) -> None:
        """Test that evidence requires a URL."""
        with pytest.raises(ValidationError):
            Evidence(snippet="no url")  # type: ignore

    def test_evidence_forbids_extra(self) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            Evidence(url="https://example.com", extra_field="bad")  # type: ignore


class TestContactChannel:
    """Tests for ContactChannel model."""

    def test_valid_channel(self, sample_evidence: Evidence) -> None:
        """Test creating a valid contact channel."""
        ch = ContactChannel(
            type="email",
            value="test@example.com",
            evidence=[sample_evidence],
        )
        assert ch.type == "email"
        assert ch.value == "test@example.com"

    def test_channel_requires_evidence(self) -> None:
        """Test that channel requires at least one evidence."""
        with pytest.raises(ValidationError):
            ContactChannel(type="email", value="test@example.com", evidence=[])

    def test_channel_requires_value(self, sample_evidence: Evidence) -> None:
        """Test that channel requires a non-empty value."""
        with pytest.raises(ValidationError):
            ContactChannel(type="email", value="", evidence=[sample_evidence])

    def test_channel_forbids_extra(self, sample_evidence: Evidence) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            ContactChannel(
                type="email",
                value="test@example.com",
                evidence=[sample_evidence],
                extra="bad",  # type: ignore
            )


class TestContact:
    """Tests for Contact model."""

    def test_valid_contact(self, sample_channel: ContactChannel) -> None:
        """Test creating a valid contact."""
        contact = Contact(
            name="John Doe",
            title="CEO",
            role_category="exec",
            channels=[sample_channel],
        )
        assert contact.name == "John Doe"
        assert contact.role_category == "exec"

    def test_contact_default_role(self) -> None:
        """Test that contact defaults to 'other' role."""
        contact = Contact(name="Test")
        assert contact.role_category == "other"

    def test_contact_forbids_extra(self) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            Contact(name="Test", extra="bad")  # type: ignore


class TestOrganization:
    """Tests for Organization model."""

    def test_valid_organization(self, sample_evidence: Evidence) -> None:
        """Test creating a valid organization."""
        org = Organization(
            name="Acme Corp",
            org_type="contractor",
            industries=["construction"],
            country="USA",
            evidence=[sample_evidence],
        )
        assert org.name == "Acme Corp"
        assert org.org_type == "contractor"

    def test_organization_requires_name(self) -> None:
        """Test that organization requires a name."""
        with pytest.raises(ValidationError):
            Organization(org_type="contractor")  # type: ignore

    def test_organization_forbids_extra(self) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            Organization(name="Test", extra="bad")  # type: ignore


class TestLead:
    """Tests for Lead model."""

    def test_valid_lead(self, sample_organization: Organization) -> None:
        """Test creating a valid lead."""
        lead = Lead(organization=sample_organization)
        assert lead.organization.name == "Acme Corp"
        assert lead.confidence == 0.5  # default

    def test_lead_confidence_bounds(self, sample_organization: Organization) -> None:
        """Test that confidence must be 0-1."""
        with pytest.raises(ValidationError):
            Lead(organization=sample_organization, confidence=1.5)

        with pytest.raises(ValidationError):
            Lead(organization=sample_organization, confidence=-0.1)

    def test_lead_has_usable_contact(self, sample_lead: Lead) -> None:
        """Test has_usable_contact method."""
        assert sample_lead.has_usable_contact() is True

    def test_lead_no_usable_contact(self, sample_organization: Organization) -> None:
        """Test has_usable_contact returns False when no channels."""
        lead = Lead(organization=sample_organization)
        assert lead.has_usable_contact() is False

    def test_lead_get_evidence_urls(self, sample_lead: Lead) -> None:
        """Test get_evidence_urls method."""
        urls = sample_lead.get_evidence_urls()
        assert len(urls) > 0
        assert "https://example.com/about" in urls

    def test_lead_get_primary_email(self, sample_lead: Lead) -> None:
        """Test get_primary_email method."""
        email = sample_lead.get_primary_email()
        assert email == "info@example.com"

    def test_lead_forbids_extra(self, sample_organization: Organization) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            Lead(organization=sample_organization, extra="bad")  # type: ignore


class TestApproachAdvice:
    """Tests for ApproachAdvice model."""

    def test_valid_advice(self) -> None:
        """Test creating valid advice."""
        advice = ApproachAdvice(
            recommended_angle="Test angle",
            recommended_first_offer="Test offer",
            qualifying_question="Test question?",
        )
        assert advice.recommended_angle == "Test angle"

    def test_advice_requires_all_fields(self) -> None:
        """Test that advice requires all three fields."""
        with pytest.raises(ValidationError):
            ApproachAdvice(recommended_angle="Test")  # type: ignore

    def test_advice_min_length(self) -> None:
        """Test that advice fields have min length."""
        with pytest.raises(ValidationError):
            ApproachAdvice(
                recommended_angle="",
                recommended_first_offer="Test",
                qualifying_question="Test?",
            )


class TestRunConfig:
    """Tests for RunConfig model."""

    def test_valid_config(self) -> None:
        """Test creating valid run config."""
        config = RunConfig(prompt="test query")
        assert config.prompt == "test query"
        assert config.max_results == 50  # default

    def test_config_requires_prompt(self) -> None:
        """Test that config requires a prompt."""
        with pytest.raises(ValidationError):
            RunConfig()  # type: ignore

    def test_config_max_results_bounds(self) -> None:
        """Test max_results bounds."""
        with pytest.raises(ValidationError):
            RunConfig(prompt="test", max_results=0)

        with pytest.raises(ValidationError):
            RunConfig(prompt="test", max_results=1000)
