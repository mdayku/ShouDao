"""Tests for GitHub integration."""

from shoudao.github import (
    AI_KEYWORDS,
    GitHubConfig,
    GitHubProfile,
    GitHubProvider,
    GitHubRepo,
)


class TestGitHubConfig:
    """Tests for GitHub configuration."""

    def test_default_config(self) -> None:
        """Default config should have reasonable values."""
        config = GitHubConfig()
        assert config.token is None
        assert config.requests_per_hour == 60  # Unauthenticated rate

    def test_config_with_token(self) -> None:
        """Config with token should have higher rate limit."""
        config = GitHubConfig(token="test_token", requests_per_hour=5000)
        assert config.token == "test_token"
        assert config.requests_per_hour == 5000


class TestGitHubRepo:
    """Tests for GitHubRepo model."""

    def test_repo_creation(self) -> None:
        """Should create a repo with required fields."""
        repo = GitHubRepo(
            name="test-repo",
            full_name="user/test-repo",
            html_url="https://github.com/user/test-repo",
        )
        assert repo.name == "test-repo"
        assert repo.stargazers_count == 0
        assert repo.forks_count == 0

    def test_repo_with_all_fields(self) -> None:
        """Should create a repo with all fields."""
        repo = GitHubRepo(
            name="ai-project",
            full_name="user/ai-project",
            html_url="https://github.com/user/ai-project",
            description="An AI project using LLM",
            language="Python",
            stargazers_count=100,
            forks_count=20,
            topics=["ai", "llm", "machine-learning"],
        )
        assert repo.stargazers_count == 100
        assert "ai" in repo.topics


class TestGitHubProfile:
    """Tests for GitHubProfile model."""

    def test_profile_creation(self) -> None:
        """Should create a profile with required fields."""
        profile = GitHubProfile(
            login="testuser",
            html_url="https://github.com/testuser",
        )
        assert profile.login == "testuser"
        assert profile.repos == []

    def test_profile_with_repos(self) -> None:
        """Should create a profile with repos."""
        repo = GitHubRepo(
            name="project",
            full_name="testuser/project",
            html_url="https://github.com/testuser/project",
        )
        profile = GitHubProfile(
            login="testuser",
            html_url="https://github.com/testuser",
            repos=[repo],
        )
        assert len(profile.repos) == 1


class TestGitHubProvider:
    """Tests for GitHubProvider."""

    def test_provider_creation(self) -> None:
        """Provider should be creatable with config."""
        config = GitHubConfig(token=None)
        provider = GitHubProvider(config)
        assert provider.config.token is None

    def test_provider_with_token(self) -> None:
        """Provider with token should store it."""
        config = GitHubConfig(token="test_token", requests_per_hour=5000)
        provider = GitHubProvider(config)
        assert provider.config.token == "test_token"

    def test_calculate_ai_signal_score_no_repos(self) -> None:
        """Profile with no repos should have zero AI signal."""
        profile = GitHubProfile(
            login="testuser",
            html_url="https://github.com/testuser",
            repos=[],
        )
        config = GitHubConfig(token="test")
        provider = GitHubProvider(config)
        score = provider.calculate_ai_signal_score(profile)
        assert score == 0.0

    def test_calculate_ai_signal_score_with_ai_repos(self) -> None:
        """Profile with AI repos should have higher AI signal."""
        ai_repo = GitHubRepo(
            name="llm-agent",
            full_name="testuser/llm-agent",
            html_url="https://github.com/testuser/llm-agent",
            description="An LLM-powered agent",
            topics=["llm", "ai", "agent"],
            stargazers_count=50,
        )
        # ai_repos must be populated (this is done during enrichment)
        profile = GitHubProfile(
            login="testuser",
            html_url="https://github.com/testuser",
            repos=[ai_repo],
            ai_repos=[ai_repo],  # Explicitly set AI repos
        )
        config = GitHubConfig(token="test")
        provider = GitHubProvider(config)
        score = provider.calculate_ai_signal_score(profile)
        assert score > 0.0

    def test_calculate_build_in_public_score(self) -> None:
        """Profile with public repos should have build-in-public score."""
        repos = [
            GitHubRepo(
                name=f"project-{i}",
                full_name=f"testuser/project-{i}",
                html_url=f"https://github.com/testuser/project-{i}",
                stargazers_count=10 * i,
            )
            for i in range(5)
        ]
        profile = GitHubProfile(
            login="testuser",
            html_url="https://github.com/testuser",
            repos=repos,
            public_repos=5,
            followers=50,
        )
        config = GitHubConfig(token="test")
        provider = GitHubProvider(config)
        score = provider.calculate_build_in_public_score(profile)
        assert score > 0.0


class TestAIKeywords:
    """Tests for AI keyword detection."""

    def test_ai_keywords_exist(self) -> None:
        """AI keywords list should exist and have entries."""
        assert len(AI_KEYWORDS) > 0
        assert "llm" in AI_KEYWORDS
        assert "openai" in AI_KEYWORDS
        assert "langchain" in AI_KEYWORDS
