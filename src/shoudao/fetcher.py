"""
ShouDao fetcher - polite HTTP fetching with rate limiting.
"""

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class FetchResult:
    """Result of fetching a URL."""
    url: str
    success: bool
    status_code: int = 0
    html: str = ""
    text: str = ""
    error: str = ""


@dataclass
class FetcherConfig:
    """Fetcher configuration."""
    timeout: float = 30.0
    max_retries: int = 2
    delay_between_requests: float = 1.0  # Seconds between requests to same domain
    max_concurrent: int = 5
    user_agent: str = "ShouDao/0.1 (B2B Lead Research Tool)"


class Fetcher:
    """Polite HTTP fetcher with domain throttling."""

    def __init__(self, config: FetcherConfig | None = None):
        self.config = config or FetcherConfig()
        self._domain_last_hit: dict[str, float] = {}

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()

    def _wait_for_domain(self, domain: str) -> None:
        """Wait if we've hit this domain recently."""
        last_hit = self._domain_last_hit.get(domain, 0)
        elapsed = time.time() - last_hit
        if elapsed < self.config.delay_between_requests:
            time.sleep(self.config.delay_between_requests - elapsed)
        self._domain_last_hit[domain] = time.time()

    def _extract_text(self, html: str) -> str:
        """Extract clean text from HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator="\n", strip=True)

        # Collapse multiple newlines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_with_retry(self, url: str) -> httpx.Response:
        """Fetch URL with retry logic."""
        with httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.config.user_agent},
        ) as client:
            return client.get(url)

    def fetch(self, url: str) -> FetchResult:
        """Fetch a single URL, respecting rate limits."""
        domain = self._get_domain(url)
        self._wait_for_domain(domain)

        try:
            resp = self._fetch_with_retry(url)
            html = resp.text
            text = self._extract_text(html)
            return FetchResult(
                url=url,
                success=resp.status_code == 200,
                status_code=resp.status_code,
                html=html,
                text=text,
            )
        except Exception as e:
            return FetchResult(
                url=url,
                success=False,
                error=str(e),
            )

    def fetch_many(self, urls: list[str]) -> list[FetchResult]:
        """Fetch multiple URLs sequentially (polite mode)."""
        results = []
        for url in urls:
            result = self.fetch(url)
            results.append(result)
        return results


def filter_urls(urls: list[str]) -> list[str]:
    """
    Filter out low-signal URLs.
    Remove social media, generic aggregators, etc.
    """
    blocked_domains = {
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "tiktok.com",
        "youtube.com",
        "pinterest.com",
        "reddit.com",
        "quora.com",
        "wikipedia.org",
        "amazon.com",
        "ebay.com",
    }

    filtered = []
    for url in urls:
        try:
            domain = urlparse(url).netloc.lower()
            # Remove www prefix for matching
            if domain.startswith("www."):
                domain = domain[4:]
            # Check against blocklist
            if not any(domain.endswith(blocked) for blocked in blocked_domains):
                filtered.append(url)
        except Exception:
            continue

    return filtered


def dedupe_by_domain(urls: list[str], max_per_domain: int = 3) -> list[str]:
    """Limit URLs per domain to ensure diversity."""
    domain_counts: dict[str, int] = {}
    result = []

    for url in urls:
        domain = urlparse(url).netloc.lower()
        count = domain_counts.get(domain, 0)
        if count < max_per_domain:
            result.append(url)
            domain_counts[domain] = count + 1

    return result

