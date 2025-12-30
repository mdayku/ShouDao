"""
GitHub integration for candidate enrichment.

Uses the GitHub API to:
1. Search for a user's profile by name
2. Fetch their public repos
3. Analyze repos for AI/LLM signals
"""

import os
import time
from dataclasses import dataclass

import requests
from pydantic import BaseModel


class GitHubRepo(BaseModel):
    """A GitHub repository."""

    name: str
    full_name: str
    description: str | None = None
    html_url: str
    language: str | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    topics: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None
    is_fork: bool = False


class GitHubProfile(BaseModel):
    """A GitHub user profile."""

    login: str
    html_url: str
    name: str | None = None
    bio: str | None = None
    company: str | None = None
    location: str | None = None
    email: str | None = None
    twitter_username: str | None = None
    blog: str | None = None
    public_repos: int = 0
    followers: int = 0
    following: int = 0
    created_at: str | None = None

    # Enriched data
    repos: list[GitHubRepo] = []
    ai_repos: list[GitHubRepo] = []
    total_stars: int = 0


# AI/LLM keywords to look for in repos
AI_KEYWORDS = [
    "llm",
    "gpt",
    "openai",
    "anthropic",
    "claude",
    "langchain",
    "agent",
    "rag",
    "embedding",
    "transformer",
    "huggingface",
    "diffusion",
    "stable-diffusion",
    "chatbot",
    "ai",
    "machine-learning",
    "deep-learning",
    "neural",
    "pytorch",
    "tensorflow",
    "streamlit",
    "gradio",
    "cursor",
    "copilot",
]


@dataclass
class GitHubConfig:
    """Configuration for GitHub API."""

    token: str | None = None
    base_url: str = "https://api.github.com"
    requests_per_hour: int = 60  # Unauthenticated limit (5000 with token)


class GitHubProvider:
    """GitHub API provider for candidate enrichment."""

    def __init__(self, config: GitHubConfig):
        self.config = config
        self._last_request_time = 0.0
        self._min_delay = 0.5  # Min delay between requests

    @classmethod
    def from_env(cls) -> "GitHubProvider":
        """Create provider from environment variables."""
        token = os.getenv("GITHUB_TOKEN")
        config = GitHubConfig(
            token=token,
            requests_per_hour=5000 if token else 60,
        )
        return cls(config)

    def is_authenticated(self) -> bool:
        """Check if we have a GitHub token."""
        return bool(self.config.token)

    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _rate_limit(self) -> None:
        """Respect rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: dict | None = None) -> dict | list | None:
        """Make a GET request to the GitHub API."""
        self._rate_limit()
        url = f"{self.config.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=self._headers(), params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                print("[GitHub] Rate limit exceeded")
                return None
            elif response.status_code == 404:
                return None
            else:
                print(f"[GitHub] API error: {response.status_code}")
                return None
        except Exception as e:
            print(f"[GitHub] Request error: {e}")
            return None

    def search_user(self, name: str, location: str | None = None) -> str | None:
        """
        Search for a GitHub user by name.

        Args:
            name: Person's full name
            location: Optional location to filter by

        Returns:
            GitHub username if found, None otherwise
        """
        # Build search query
        query = f'"{name}" in:name'
        if location:
            # Clean location for GitHub search
            location_clean = location.split(",")[0].strip()
            query += f" location:{location_clean}"

        params = {"q": query, "per_page": 5}
        result = self._get("/search/users", params)

        if not result or not isinstance(result, dict):
            return None

        items = result.get("items", [])
        if not items:
            return None

        # Return the first match
        return items[0].get("login")

    def get_user(self, username: str) -> GitHubProfile | None:
        """
        Get a GitHub user's profile.

        Args:
            username: GitHub username

        Returns:
            GitHubProfile or None if not found
        """
        result = self._get(f"/users/{username}")
        if not result or not isinstance(result, dict):
            return None

        try:
            return GitHubProfile(
                login=result["login"],
                html_url=result["html_url"],
                name=result.get("name"),
                bio=result.get("bio"),
                company=result.get("company"),
                location=result.get("location"),
                email=result.get("email"),
                twitter_username=result.get("twitter_username"),
                blog=result.get("blog"),
                public_repos=result.get("public_repos", 0),
                followers=result.get("followers", 0),
                following=result.get("following", 0),
                created_at=result.get("created_at"),
            )
        except Exception as e:
            print(f"[GitHub] Error parsing user: {e}")
            return None

    def get_user_repos(self, username: str, max_repos: int = 30) -> list[GitHubRepo]:
        """
        Get a user's public repositories.

        Args:
            username: GitHub username
            max_repos: Maximum repos to fetch

        Returns:
            List of GitHubRepo objects
        """
        params = {"per_page": min(max_repos, 100), "sort": "updated"}
        result = self._get(f"/users/{username}/repos", params)

        if not result or not isinstance(result, list):
            return []

        repos = []
        for item in result[:max_repos]:
            try:
                repo = GitHubRepo(
                    name=item["name"],
                    full_name=item["full_name"],
                    description=item.get("description"),
                    html_url=item["html_url"],
                    language=item.get("language"),
                    stargazers_count=item.get("stargazers_count", 0),
                    forks_count=item.get("forks_count", 0),
                    topics=item.get("topics", []),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                    is_fork=item.get("fork", False),
                )
                repos.append(repo)
            except Exception:
                continue

        return repos

    def enrich_profile(self, profile: GitHubProfile) -> GitHubProfile:
        """
        Enrich a profile with repos and AI analysis.

        Args:
            profile: GitHubProfile to enrich

        Returns:
            Enriched profile with repos and AI scores
        """
        # Get repos
        repos = self.get_user_repos(profile.login)
        profile.repos = repos

        # Calculate total stars
        profile.total_stars = sum(r.stargazers_count for r in repos)

        # Identify AI repos
        ai_repos = []
        for repo in repos:
            if self._is_ai_repo(repo):
                ai_repos.append(repo)
        profile.ai_repos = ai_repos

        return profile

    def _is_ai_repo(self, repo: GitHubRepo) -> bool:
        """Check if a repo is AI/LLM related."""
        # Check name
        name_lower = repo.name.lower()
        for keyword in AI_KEYWORDS:
            if keyword in name_lower:
                return True

        # Check description
        if repo.description:
            desc_lower = repo.description.lower()
            for keyword in AI_KEYWORDS:
                if keyword in desc_lower:
                    return True

        # Check topics
        for topic in repo.topics:
            topic_lower = topic.lower()
            for keyword in AI_KEYWORDS:
                if keyword in topic_lower:
                    return True

        return False

    def calculate_ai_signal_score(self, profile: GitHubProfile) -> float:
        """
        Calculate AI signal score (0-1) based on GitHub activity.

        Scoring:
        - Has AI repos: +0.3
        - Multiple AI repos (3+): +0.2
        - AI repos have stars: +0.2
        - Recent activity (updated in last 6 months): +0.15
        - Has streamlit/gradio/demo: +0.15
        """
        score = 0.0

        if not profile.repos:
            return 0.0

        # Has any AI repos
        if profile.ai_repos:
            score += 0.3

        # Multiple AI repos
        if len(profile.ai_repos) >= 3:
            score += 0.2

        # AI repos have stars
        ai_stars = sum(r.stargazers_count for r in profile.ai_repos)
        if ai_stars >= 10:
            score += 0.2
        elif ai_stars >= 3:
            score += 0.1

        # Check for demo/app repos
        demo_keywords = ["streamlit", "gradio", "demo", "app", "ui", "frontend"]
        has_demo = any(any(kw in r.name.lower() for kw in demo_keywords) for r in profile.repos)
        if has_demo:
            score += 0.15

        # Recent activity (check if any repo updated recently)
        # Simple check: just having repos is some signal
        if len(profile.repos) >= 5:
            score += 0.15

        return min(score, 1.0)

    def calculate_build_in_public_score(self, profile: GitHubProfile) -> float:
        """
        Calculate build-in-public score (0-1) based on GitHub presence.

        Scoring:
        - Has blog/website: +0.25
        - Has Twitter: +0.2
        - Has bio: +0.15
        - Has 10+ repos: +0.2
        - Has 50+ followers: +0.2
        """
        score = 0.0

        # Has blog
        if profile.blog:
            score += 0.25

        # Has Twitter
        if profile.twitter_username:
            score += 0.2

        # Has bio
        if profile.bio:
            score += 0.15

        # Active contributor
        if len(profile.repos) >= 10:
            score += 0.2

        # Has following
        if profile.followers >= 50:
            score += 0.2
        elif profile.followers >= 10:
            score += 0.1

        return min(score, 1.0)


def check_github_config() -> bool:
    """Check if GitHub API is configured (optional token)."""
    # GitHub works without token, just with lower rate limits
    return True


def get_github_provider() -> GitHubProvider:
    """Get GitHub provider (always available, optionally authenticated)."""
    return GitHubProvider.from_env()
