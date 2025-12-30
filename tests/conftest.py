"""Pytest configuration and fixtures."""

from datetime import UTC, datetime

import pytest

from shoudao.models import (
    ApproachAdvice,
    Contact,
    ContactChannel,
    Evidence,
    Lead,
    Organization,
    RunConfig,
    RunResult,
)


@pytest.fixture
def sample_evidence() -> Evidence:
    """Create a sample evidence object."""
    return Evidence(
        url="https://example.com/about",
        snippet="Contact our team at info@example.com",
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_channel(sample_evidence: Evidence) -> ContactChannel:
    """Create a sample contact channel."""
    return ContactChannel(
        type="email",
        value="info@example.com",
        evidence=[sample_evidence],
    )


@pytest.fixture
def sample_contact(sample_channel: ContactChannel) -> Contact:
    """Create a sample contact."""
    return Contact(
        name="John Smith",
        title="CEO",
        role_category="exec",
        channels=[sample_channel],
    )


@pytest.fixture
def sample_organization(sample_evidence: Evidence) -> Organization:
    """Create a sample organization."""
    return Organization(
        name="Acme Corp",
        org_type="contractor",
        industries=["construction"],
        country="USA",
        region="Florida",
        city="Miami",
        website="https://acme.com",
        size_indicator="medium",
        description="A construction company",
        evidence=[sample_evidence],
    )


@pytest.fixture
def sample_advice() -> ApproachAdvice:
    """Create sample approach advice."""
    return ApproachAdvice(
        recommended_angle="Position as a time-saving solution for their construction projects.",
        recommended_first_offer="Free consultation on project optimization.",
        qualifying_question="What is your current project pipeline for the next quarter?",
    )


@pytest.fixture
def sample_lead(
    sample_organization: Organization,
    sample_contact: Contact,
    sample_evidence: Evidence,
    sample_advice: ApproachAdvice,
) -> Lead:
    """Create a sample lead."""
    return Lead(
        organization=sample_organization,
        contacts=[sample_contact],
        confidence=0.8,
        evidence=[sample_evidence],
        advice=sample_advice,
        dedupe_key="acme.com",
    )


@pytest.fixture
def sample_run_config() -> RunConfig:
    """Create a sample run configuration."""
    return RunConfig(
        prompt="construction contractors in Florida",
        countries=["USA"],
        industries=["construction"],
        max_results=10,
    )


@pytest.fixture
def sample_run_result(sample_run_config: RunConfig, sample_lead: Lead) -> RunResult:
    """Create a sample run result."""
    return RunResult(
        config=sample_run_config,
        leads=[sample_lead],
        run_id="20251229_120000_abc123",
        sources_fetched=5,
        domains_hit=3,
    )
