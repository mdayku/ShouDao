"""
ShouDao sources tracker - audit trail for search/fetch decisions.
Produces sources.json for debugging and client trust.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class QueryRecord:
    """A search query that was executed."""

    query: str
    provider: str
    urls_returned: int
    executed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class UrlRecord:
    """A URL that was discovered and potentially fetched."""

    url: str
    source_query: str
    was_fetched: bool = False
    fetch_status: int | None = None
    fetch_error: str | None = None
    fetched_at: str | None = None
    content_length: int = 0
    leads_extracted: int = 0


@dataclass
class SourcesLog:
    """Complete audit log of source discovery and fetching."""

    run_id: str
    prompt: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None

    # Queries
    queries: list[QueryRecord] = field(default_factory=list)

    # URLs by domain
    urls_discovered: list[str] = field(default_factory=list)
    urls_filtered_out: list[str] = field(default_factory=list)
    urls_fetched: list[UrlRecord] = field(default_factory=list)

    # Domain stats
    domain_counts: dict[str, int] = field(default_factory=dict)

    # Summary stats
    total_queries: int = 0
    total_urls_discovered: int = 0
    total_urls_filtered: int = 0
    total_urls_fetched: int = 0
    total_fetch_success: int = 0
    total_fetch_failed: int = 0

    def add_query(self, query: str, provider: str, urls: list[str]) -> None:
        """Record a search query and its results."""
        self.queries.append(
            QueryRecord(
                query=query,
                provider=provider,
                urls_returned=len(urls),
            )
        )
        self.urls_discovered.extend(urls)
        self.total_queries += 1
        self.total_urls_discovered += len(urls)

        # Update domain counts
        for url in urls:
            domain = self._extract_domain(url)
            self.domain_counts[domain] = self.domain_counts.get(domain, 0) + 1

    def add_filtered_url(self, url: str) -> None:
        """Record a URL that was filtered out."""
        self.urls_filtered_out.append(url)
        self.total_urls_filtered += 1

    def add_fetch_result(
        self,
        url: str,
        source_query: str,
        success: bool,
        status_code: int = 0,
        error: str = "",
        content_length: int = 0,
        leads_extracted: int = 0,
    ) -> None:
        """Record a fetch attempt."""
        record = UrlRecord(
            url=url,
            source_query=source_query,
            was_fetched=True,
            fetch_status=status_code if success else None,
            fetch_error=error if not success else None,
            fetched_at=datetime.now(UTC).isoformat(),
            content_length=content_length,
            leads_extracted=leads_extracted,
        )
        self.urls_fetched.append(record)
        self.total_urls_fetched += 1
        if success:
            self.total_fetch_success += 1
        else:
            self.total_fetch_failed += 1

    def finish(self) -> None:
        """Mark the log as complete."""
        self.finished_at = datetime.now(UTC).isoformat()

    def save(self, path: Path) -> None:
        """Save to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, default=str)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse

        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return "unknown"
