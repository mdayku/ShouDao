"""Tests for talent discovery models and scoring."""

import pytest

from shoudao.dedupe import (
    classify_candidate_tier,
    dedupe_candidates,
    estimate_salary_band,
    score_candidate,
)
from shoudao.models import Candidate, Evidence


@pytest.fixture
def sample_evidence() -> Evidence:
    """Create a sample evidence object."""
    return Evidence(url="https://github.com/example", snippet="Test snippet")


@pytest.fixture
def strong_candidate(sample_evidence: Evidence) -> Candidate:
    """A strong Tier A candidate."""
    return Candidate(
        name="Jane Doe",
        primary_profile="https://github.com/janedoe",
        email="jane@example.com",
        github_url="https://github.com/janedoe",
        linkedin_url="https://linkedin.com/in/janedoe",
        degree_signal="CS from Stanford",
        university="Stanford",
        current_role="Software Engineer",
        current_company="Startup Inc",
        years_experience=3,
        public_repos=["llm-agent", "chatbot", "ml-project", "data-pipeline", "api-server"],
        ai_signal_score=0.8,
        build_in_public_score=0.7,
        evidence=[sample_evidence],
    )


@pytest.fixture
def weak_candidate(sample_evidence: Evidence) -> Candidate:
    """A weak Tier C candidate."""
    return Candidate(
        name="John Smith",
        primary_profile="https://github.com/johnsmith",
        github_url="https://github.com/johnsmith",
        public_repos=["hello-world"],
        ai_signal_score=0.1,
        build_in_public_score=0.2,
        evidence=[sample_evidence],
    )


@pytest.fixture
def faang_candidate(sample_evidence: Evidence) -> Candidate:
    """A FAANG engineer (high salary, may have less incentive)."""
    return Candidate(
        name="Alex FAANG",
        primary_profile="https://github.com/alexfaang",
        email="alex@google.com",
        linkedin_url="https://linkedin.com/in/alexfaang",
        degree_signal="CS from MIT",
        university="MIT",
        current_role="Staff Software Engineer",
        current_company="Google",
        years_experience=8,
        public_repos=["tensorflow-contrib", "ml-papers"],
        ai_signal_score=0.9,
        build_in_public_score=0.5,
        evidence=[sample_evidence],
    )


class TestCandidateModel:
    """Tests for Candidate model."""

    def test_is_contactable_with_email(self, sample_evidence: Evidence) -> None:
        """Candidate with email is contactable."""
        c = Candidate(
            primary_profile="https://example.com",
            email="test@example.com",
            evidence=[sample_evidence],
        )
        assert c.is_contactable() is True

    def test_is_contactable_with_github(self, sample_evidence: Evidence) -> None:
        """Candidate with GitHub is contactable."""
        c = Candidate(
            primary_profile="https://github.com/test",
            github_url="https://github.com/test",
            evidence=[sample_evidence],
        )
        assert c.is_contactable() is True

    def test_is_contactable_with_linkedin(self, sample_evidence: Evidence) -> None:
        """Candidate with LinkedIn is contactable."""
        c = Candidate(
            primary_profile="https://linkedin.com/in/test",
            linkedin_url="https://linkedin.com/in/test",
            evidence=[sample_evidence],
        )
        assert c.is_contactable() is True

    def test_is_contactable_with_twitter(self, sample_evidence: Evidence) -> None:
        """Candidate with Twitter is contactable."""
        c = Candidate(
            primary_profile="https://twitter.com/test",
            twitter_url="https://twitter.com/test",
            evidence=[sample_evidence],
        )
        assert c.is_contactable() is True

    def test_not_contactable_without_channels(self, sample_evidence: Evidence) -> None:
        """Candidate without any contact channel is not contactable."""
        c = Candidate(
            primary_profile="https://example.com",
            evidence=[sample_evidence],
        )
        assert c.is_contactable() is False

    def test_get_contact_channels(self, sample_evidence: Evidence) -> None:
        """Test getting all contact channels."""
        c = Candidate(
            primary_profile="https://github.com/test",
            email="test@example.com",
            github_url="https://github.com/test",
            linkedin_url="https://linkedin.com/in/test",
            evidence=[sample_evidence],
        )
        channels = c.get_contact_channels()
        assert len(channels) == 3
        assert "email:test@example.com" in channels
        assert "github:https://github.com/test" in channels

    def test_get_public_work_count(self, sample_evidence: Evidence) -> None:
        """Test counting public work artifacts."""
        c = Candidate(
            primary_profile="https://github.com/test",
            public_repos=["repo1", "repo2"],
            public_demos=["demo1"],
            blog_posts=["post1", "post2", "post3"],
            evidence=[sample_evidence],
        )
        assert c.get_public_work_count() == 6


class TestEstimateSalaryBand:
    """Tests for salary band estimation."""

    def test_faang_high_salary(self, faang_candidate: Candidate) -> None:
        """FAANG engineer should be estimated as 200k+."""
        band = estimate_salary_band(faang_candidate)
        assert band == "200k_plus"

    def test_startup_lower_salary(self, strong_candidate: Candidate) -> None:
        """Startup engineer with 3 years should be in a lower band (good incentive)."""
        band = estimate_salary_band(strong_candidate)
        # 3 years at unknown startup = under_100k or 100k_150k (both are good incentive)
        assert band in ("under_100k", "100k_150k")

    def test_junior_under_100k(self, sample_evidence: Evidence) -> None:
        """Junior engineer should be under 100k."""
        c = Candidate(
            primary_profile="https://github.com/junior",
            current_role="Junior Developer",
            current_company="Small Startup",
            years_experience=1,
            evidence=[sample_evidence],
        )
        band = estimate_salary_band(c)
        assert band == "under_100k"

    def test_unknown_salary(self, sample_evidence: Evidence) -> None:
        """No signals should return unknown."""
        c = Candidate(
            primary_profile="https://github.com/mystery",
            evidence=[sample_evidence],
        )
        band = estimate_salary_band(c)
        assert band == "unknown"


class TestScoreCandidate:
    """Tests for candidate scoring."""

    def test_strong_candidate_high_score(self, strong_candidate: Candidate) -> None:
        """Strong candidate should have high score."""
        score, contributions = score_candidate(strong_candidate)
        assert score >= 0.6
        assert "cs_top_school" in contributions
        assert "engineering_experience" in contributions

    def test_weak_candidate_low_score(self, weak_candidate: Candidate) -> None:
        """Weak candidate should have low score."""
        score, contributions = score_candidate(weak_candidate)
        assert score < 0.3

    def test_score_capped_at_one(self, strong_candidate: Candidate) -> None:
        """Score should be capped at 1.0."""
        # Add everything possible
        strong_candidate.estimated_salary_band = "under_100k"
        score, _ = score_candidate(strong_candidate)
        assert score <= 1.0

    def test_contributions_explain_score(self, strong_candidate: Candidate) -> None:
        """Contributions should explain the score."""
        score, contributions = score_candidate(strong_candidate)
        total = sum(contributions.values())
        # Total contributions should approximately equal score (some capping may occur)
        assert abs(total - score) < 0.1 or score == 1.0


class TestClassifyCandidateTier:
    """Tests for tier classification."""

    def test_tier_a_strong_candidate(self, strong_candidate: Candidate) -> None:
        """Strong candidate with low salary should be Tier A."""
        strong_candidate.confidence = 0.7
        strong_candidate.estimated_salary_band = "under_100k"
        tier = classify_candidate_tier(strong_candidate)
        assert tier == "A"

    def test_tier_b_moderate_candidate(self, strong_candidate: Candidate) -> None:
        """Moderate confidence candidate should be Tier B."""
        strong_candidate.confidence = 0.5
        tier = classify_candidate_tier(strong_candidate)
        assert tier == "B"

    def test_tier_c_weak_candidate(self, weak_candidate: Candidate) -> None:
        """Weak candidate should be Tier C."""
        weak_candidate.confidence = 0.2
        tier = classify_candidate_tier(weak_candidate)
        assert tier == "C"

    def test_high_salary_demotes_tier(self, faang_candidate: Candidate) -> None:
        """High salary candidate might be demoted even with strong signals."""
        faang_candidate.confidence = 0.7
        faang_candidate.estimated_salary_band = "200k_plus"
        # Must also lower AI signal to test salary demotion path
        # (high AI signal can override salary concerns)
        faang_candidate.ai_signal_score = 0.3
        tier = classify_candidate_tier(faang_candidate)
        # High salary + low AI signal with decent score should be B (not A)
        assert tier == "B"

    def test_high_ai_signal_overrides_salary(self, faang_candidate: Candidate) -> None:
        """Strong AI builders may take pay cut - AI signal overrides salary concerns."""
        faang_candidate.confidence = 0.7
        faang_candidate.estimated_salary_band = "200k_plus"
        faang_candidate.ai_signal_score = 0.8  # Strong AI builder
        tier = classify_candidate_tier(faang_candidate)
        # High AI signal overrides high salary - still Tier A
        assert tier == "A"


class TestDedupeCandidates:
    """Tests for candidate deduplication."""

    def test_dedupe_by_profile(self, sample_evidence: Evidence) -> None:
        """Candidates with same profile URL should be deduped."""
        c1 = Candidate(
            primary_profile="https://github.com/same",
            email="one@example.com",
            evidence=[sample_evidence],
        )
        c2 = Candidate(
            primary_profile="https://github.com/same",
            email="two@example.com",
            evidence=[sample_evidence],
        )
        unique = dedupe_candidates([c1, c2])
        assert len(unique) == 1

    def test_dedupe_by_email(self, sample_evidence: Evidence) -> None:
        """Candidates with same email should be deduped."""
        c1 = Candidate(
            primary_profile="https://github.com/one",
            email="same@example.com",
            evidence=[sample_evidence],
        )
        c2 = Candidate(
            primary_profile="https://github.com/two",
            email="same@example.com",
            evidence=[sample_evidence],
        )
        unique = dedupe_candidates([c1, c2])
        assert len(unique) == 1

    def test_different_candidates_kept(self, sample_evidence: Evidence) -> None:
        """Different candidates should be kept."""
        c1 = Candidate(
            primary_profile="https://github.com/alice",
            email="alice@example.com",
            evidence=[sample_evidence],
        )
        c2 = Candidate(
            primary_profile="https://github.com/bob",
            email="bob@example.com",
            evidence=[sample_evidence],
        )
        unique = dedupe_candidates([c1, c2])
        assert len(unique) == 2


class TestOptOutFiltering:
    """Tests for opt-out list filtering."""

    def test_filter_by_company_name(self) -> None:
        """Leads with opt-out company names should be filtered."""
        from shoudao.dedupe import filter_opt_out_leads
        from shoudao.models import Evidence, Lead, Organization

        evidence = Evidence(url="https://example.com", snippet="Test")
        lead1 = Lead(
            organization=Organization(name="Good Company", evidence=[evidence]),
            contacts=[],
            evidence=[evidence],
        )
        lead2 = Lead(
            organization=Organization(name="Bad Company", evidence=[evidence]),
            contacts=[],
            evidence=[evidence],
        )

        kept, filtered = filter_opt_out_leads(
            [lead1, lead2],
            opt_out_companies=["bad company"],
        )
        assert len(kept) == 1
        assert len(filtered) == 1
        assert kept[0].organization.name == "Good Company"

    def test_filter_by_domain(self) -> None:
        """Leads with opt-out domains should be filtered."""
        from shoudao.dedupe import filter_opt_out_leads
        from shoudao.models import Evidence, Lead, Organization

        evidence = Evidence(url="https://example.com", snippet="Test")
        lead1 = Lead(
            organization=Organization(name="Good Corp", evidence=[evidence]),
            contacts=[],
            evidence=[evidence],
            dedupe_key="goodcorp.com",
        )
        lead2 = Lead(
            organization=Organization(name="Bad Corp", evidence=[evidence]),
            contacts=[],
            evidence=[evidence],
            dedupe_key="badcorp.com",
        )

        kept, filtered = filter_opt_out_leads(
            [lead1, lead2],
            opt_out_domains=["badcorp.com"],
        )
        assert len(kept) == 1
        assert len(filtered) == 1

    def test_no_opt_out_returns_all(self) -> None:
        """With no opt-out lists, all leads should be returned."""
        from shoudao.dedupe import filter_opt_out_leads
        from shoudao.models import Evidence, Lead, Organization

        evidence = Evidence(url="https://example.com", snippet="Test")
        leads = [
            Lead(
                organization=Organization(name="Company A", evidence=[evidence]),
                contacts=[],
                evidence=[evidence],
            ),
            Lead(
                organization=Organization(name="Company B", evidence=[evidence]),
                contacts=[],
                evidence=[evidence],
            ),
        ]

        kept, filtered = filter_opt_out_leads(leads)
        assert len(kept) == 2
        assert len(filtered) == 0


class TestContactPageDiscovery:
    """Tests for contact page discovery functions."""

    def test_discover_contact_pages_returns_candidates(self) -> None:
        """Should return candidate URLs for common contact paths."""
        from shoudao.fetcher import discover_contact_pages

        candidates = discover_contact_pages("https://example.com")
        assert len(candidates) > 0
        assert any("/contact" in url for url in candidates)
        assert any("/about" in url for url in candidates)

    def test_extract_contact_links_from_html(self) -> None:
        """Should extract contact-related links from HTML."""
        from shoudao.fetcher import extract_contact_links_from_html

        html = """
        <html>
        <body>
            <a href="/about">About Us</a>
            <a href="/contact">Contact</a>
            <a href="/products">Products</a>
            <a href="/team">Our Team</a>
        </body>
        </html>
        """
        links = extract_contact_links_from_html(html, "https://example.com")
        assert any("/about" in link for link in links)
        assert any("/contact" in link for link in links)
        assert any("/team" in link for link in links)
        # Products should not be included
        assert not any("/products" in link for link in links)


class TestRuleBasedSignals:
    """Tests for rule-based signal extraction."""

    def test_extract_rule_based_signals(self) -> None:
        """Should extract emails and phones via regex."""
        from shoudao.extractor import extract_rule_based_signals

        text = """
        Contact us at info@company.com or sales@company.com.
        Phone: +1 555-123-4567
        Visit https://github.com/company for our code.
        """
        signals = extract_rule_based_signals(text)
        assert len(signals.emails) >= 2
        assert "info@company.com" in signals.emails
        assert len(signals.phones) >= 1
        assert len(signals.github_urls) >= 1

    def test_extract_emails_regex(self) -> None:
        """Should extract valid emails (filters out @example)."""
        from shoudao.extractor import extract_emails_regex

        # Note: @example emails are filtered out by the extractor
        text = "Contact jane@testmail.com or bob@company.org for info"
        emails = extract_emails_regex(text)
        assert "jane@testmail.com" in emails
        assert "bob@company.org" in emails

    def test_extract_emails_filters_example(self) -> None:
        """Should filter out @example emails."""
        from shoudao.extractor import extract_emails_regex

        text = "Contact test@example.com for testing"
        emails = extract_emails_regex(text)
        assert "test@example.com" not in emails

    def test_extract_phones_regex(self) -> None:
        """Should extract phone numbers."""
        from shoudao.extractor import extract_phones_regex

        text = "Call us: 555-123-4567 or (800) 555-0000"
        phones = extract_phones_regex(text)
        assert len(phones) >= 1
