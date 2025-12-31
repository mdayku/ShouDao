"""Tests for LinkedIn integration."""

from shoudao.linkedin import (
    LinkedInConfig,
    LinkedInProfile,
    LinkedInProvider,
    linkedin_profile_to_candidate,
)
from shoudao.models import Candidate


class TestLinkedInConfig:
    """Tests for LinkedIn configuration."""

    def test_config_creation(self) -> None:
        """Should create config with required api_key."""
        config = LinkedInConfig(api_key="test_key")
        assert config.api_key == "test_key"
        assert config.max_results_per_search == 50

    def test_config_with_actor_ids(self) -> None:
        """Should create config with custom actor IDs."""
        config = LinkedInConfig(
            api_key="test_key",
            profile_scraper_actor="custom/profile-actor",
            search_actor="custom/search-actor",
        )
        assert config.profile_scraper_actor == "custom/profile-actor"
        assert config.search_actor == "custom/search-actor"


class TestLinkedInProfile:
    """Tests for LinkedInProfile model."""

    def test_profile_creation(self) -> None:
        """Should create a profile with required fields."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/johndoe",
        )
        assert profile.url == "https://linkedin.com/in/johndoe"

    def test_profile_with_name(self) -> None:
        """Should create a profile with name."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/janedoe",
            name="Jane Doe",
        )
        assert profile.name == "Jane Doe"

    def test_profile_with_experience(self) -> None:
        """Should create a profile with experience."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/engineer",
            name="Alex Engineer",
            headline="Software Engineer at Google",
            current_company="Google",
            current_title="Software Engineer",
            years_experience=5,
        )
        assert profile.current_company == "Google"
        assert profile.years_experience == 5

    def test_profile_with_education(self) -> None:
        """Should create a profile with education."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/graduate",
            name="Sam Graduate",
            school="MIT",
            degree="Computer Science",
        )
        assert profile.school == "MIT"


class TestLinkedInProvider:
    """Tests for LinkedInProvider."""

    def test_provider_creation(self) -> None:
        """Provider should be creatable with config."""
        config = LinkedInConfig(api_key="test_key")
        provider = LinkedInProvider(config)
        assert provider.config.api_key == "test_key"


class TestLinkedInProfileToCandidate:
    """Tests for converting LinkedIn profiles to candidates."""

    def test_basic_conversion(self) -> None:
        """Should convert a basic profile to a candidate."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/johndoe",
            name="John Doe",
            headline="Software Engineer",
        )
        candidate = linkedin_profile_to_candidate(profile)
        assert isinstance(candidate, Candidate)
        assert candidate.name == "John Doe"
        assert candidate.linkedin_url == "https://linkedin.com/in/johndoe"

    def test_conversion_with_education(self) -> None:
        """Should include education signals."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/graduate",
            name="Jane Graduate",
            school="Stanford",
            degree="Computer Science",
        )
        candidate = linkedin_profile_to_candidate(profile)
        assert candidate.university == "Stanford"

    def test_conversion_with_experience(self) -> None:
        """Should include experience signals."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/engineer",
            name="Alex Engineer",
            current_company="Google",
            current_title="Staff Engineer",
            years_experience=8,
        )
        candidate = linkedin_profile_to_candidate(profile)
        assert candidate.current_company == "Google"
        assert candidate.current_role == "Staff Engineer"
        assert candidate.years_experience == 8

    def test_conversion_evidence(self) -> None:
        """Candidate should have evidence from LinkedIn."""
        profile = LinkedInProfile(
            url="https://linkedin.com/in/test",
            name="Test User",
        )
        candidate = linkedin_profile_to_candidate(profile)
        assert len(candidate.evidence) > 0
        # Evidence URL is an HttpUrl, convert to string
        assert "linkedin.com" in str(candidate.evidence[0].url)
