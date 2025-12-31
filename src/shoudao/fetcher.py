"""
ShouDao fetcher - polite HTTP fetching with rate limiting and caching.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
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
    from_cache: bool = False


@dataclass
class FetcherConfig:
    """Fetcher configuration."""

    timeout: float = 30.0
    max_retries: int = 2
    delay_between_requests: float = 1.0  # Seconds between requests to same domain
    max_concurrent: int = 5
    user_agent: str = "ShouDao/0.1 (B2B Lead Research Tool)"
    cache_dir: Path | None = None  # If set, cache fetched pages here
    use_cache: bool = True  # Whether to use cached results if available


class Fetcher:
    """Polite HTTP fetcher with domain throttling and caching."""

    def __init__(self, config: FetcherConfig | None = None):
        self.config = config or FetcherConfig()
        self._domain_last_hit: dict[str, float] = {}
        self._cache_hits = 0
        self._cache_misses = 0

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

    def _url_to_cache_key(self, url: str) -> str:
        """Convert URL to a cache-safe filename."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _get_cache_path(self, url: str) -> Path | None:
        """Get the cache file path for a URL."""
        if not self.config.cache_dir:
            return None
        return self.config.cache_dir / f"{self._url_to_cache_key(url)}.json"

    def _load_from_cache(self, url: str) -> FetchResult | None:
        """Try to load a cached result."""
        if not self.config.use_cache:
            return None

        cache_path = self._get_cache_path(url)
        if not cache_path or not cache_path.exists():
            return None

        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            self._cache_hits += 1
            return FetchResult(
                url=data["url"],
                success=data["success"],
                status_code=data.get("status_code", 0),
                html=data.get("html", ""),
                text=data.get("text", ""),
                error=data.get("error", ""),
                from_cache=True,
            )
        except Exception:
            return None

    def _save_to_cache(self, result: FetchResult) -> None:
        """Save a result to cache."""
        cache_path = self._get_cache_path(result.url)
        if not cache_path:
            return

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "url": result.url,
                "success": result.success,
                "status_code": result.status_code,
                "html": result.html,
                "text": result.text,
                "error": result.error,
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass  # Fail silently on cache write errors

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
        """Fetch a single URL, respecting rate limits and cache."""
        # Try cache first
        cached = self._load_from_cache(url)
        if cached:
            return cached

        self._cache_misses += 1
        domain = self._get_domain(url)
        self._wait_for_domain(domain)

        try:
            resp = self._fetch_with_retry(url)
            html = resp.text
            text = self._extract_text(html)
            result = FetchResult(
                url=url,
                success=resp.status_code == 200,
                status_code=resp.status_code,
                html=html,
                text=text,
            )
            # Cache successful results
            if result.success:
                self._save_to_cache(result)
            return result
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

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache hit/miss statistics."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": self._cache_hits / max(1, self._cache_hits + self._cache_misses),
        }


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


# Common contact page paths to discover
CONTACT_PAGE_PATHS = [
    "/contact",
    "/contact-us",
    "/contactus",
    "/about",
    "/about-us",
    "/aboutus",
    "/team",
    "/our-team",
    "/leadership",
    "/management",
    "/staff",
    "/people",
    "/company",
    "/who-we-are",
]


def discover_contact_pages(base_url: str, fetcher: Fetcher | None = None) -> list[str]:
    """
    Discover contact-related pages for a given base URL.

    Tries common paths like /contact, /about, /team to find pages
    that might contain contact information.

    Args:
        base_url: The base website URL (e.g., https://example.com)
        fetcher: Optional fetcher instance to check if pages exist

    Returns:
        List of discovered contact page URLs that exist
    """
    from urllib.parse import urljoin

    # Normalize base URL
    parsed = urlparse(base_url)
    if not parsed.scheme:
        base_url = f"https://{base_url}"
        parsed = urlparse(base_url)

    # Build base without path
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Generate candidate URLs
    candidates = [urljoin(base, path) for path in CONTACT_PAGE_PATHS]

    # If no fetcher provided, return all candidates
    if fetcher is None:
        return candidates

    # Check which pages actually exist
    discovered = []
    for url in candidates:
        result = fetcher.fetch(url)
        if result.success and result.status_code == 200:
            # Check for minimum content (not just a redirect or error page)
            if len(result.text) > 500:
                discovered.append(url)

    return discovered


def extract_contact_links_from_html(html: str, base_url: str) -> list[str]:
    """
    Extract contact-related links from HTML content.

    Looks for anchor tags with text/href containing contact-related keywords.

    Args:
        html: The HTML content to parse
        base_url: Base URL for resolving relative links

    Returns:
        List of contact-related URLs found in the page
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "lxml")
    contact_keywords = {
        "contact",
        "about",
        "team",
        "staff",
        "people",
        "leadership",
        "management",
        "company",
        "who we are",
    }

    found_urls = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(strip=True).lower()

        # Check if link text or href contains contact keywords
        href_lower = href.lower()
        is_contact_link = any(kw in href_lower or kw in text for kw in contact_keywords)

        if is_contact_link:
            # Resolve relative URLs
            full_url = urljoin(base_url, href)
            # Only include same-domain links
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                found_urls.add(full_url)

    return list(found_urls)
