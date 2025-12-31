"""
ShouDao structured logging - operator-grade telemetry for long runs.

Answers three questions:
1. Is it alive or stuck?
2. What phase is it in?
3. What is the unit of progress?
"""

import sys
from datetime import UTC, datetime

# Force line buffering for immediate output (important on Windows/PowerShell)
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore
except Exception:
    pass  # Fallback for non-reconfigurable streams


def _print(*args: object, **kwargs: object) -> None:
    """Print with immediate flush."""
    print(*args, **kwargs, flush=True)


def _eprint(*args: object, **kwargs: object) -> None:
    """Print to stderr with immediate flush."""
    print(*args, **kwargs, file=sys.stderr, flush=True)


class ProgressLogger:
    """
    Structured progress logger for ShouDao pipeline runs.

    Provides clear visibility into multi-country, multi-language runs
    without flooding the console with noise.
    """

    def __init__(self, run_id: str, verbose: bool = False):
        self.run_id = run_id
        self.verbose = verbose
        self.start_time = datetime.now(UTC)
        self.last_heartbeat = self.start_time
        self.phase_times: dict[str, datetime] = {}

    def phase(self, name: str, detail: str = "") -> None:
        """Log a major phase transition."""
        now = datetime.now(UTC)
        self.phase_times[name] = now
        elapsed = (now - self.start_time).total_seconds()

        if detail:
            _print(f"[Phase] {name}: {detail} ({elapsed:.1f}s)")
        else:
            _print(f"[Phase] {name} ({elapsed:.1f}s)")

    def progress(
        self,
        item: str,
        current: int,
        total: int,
        detail: str = "",
    ) -> None:
        """Log a progress update (e.g., country 3/12)."""
        pct = (current / total * 100) if total > 0 else 0
        if detail:
            _print(f"  [{item} {current}/{total}] {detail} ({pct:.0f}%)")
        else:
            _print(f"  [{item} {current}/{total}] ({pct:.0f}%)")

    def country(
        self,
        country: str,
        index: int,
        total: int,
        languages: list[str],
    ) -> None:
        """Log progress for a country."""
        lang_str = ", ".join(languages) if languages else "en"
        _print(f"  [Country {index}/{total}] {country} [{lang_str}]")

    def query(
        self,
        query: str,
        index: int,
        total: int,
        language: str = "en",
    ) -> None:
        """Log a search query (verbose only)."""
        if self.verbose:
            truncated = query[:60] + "..." if len(query) > 60 else query
            _print(f"    [Query {index}/{total}] ({language}) {truncated}")

    def sources(self, serp_count: int, accepted: int, rejected: int) -> None:
        """Log SERP results summary."""
        _print(f"    [SERP] {serp_count} results -> {accepted} accepted, {rejected} filtered")

    def pages(self, fetched: int, total: int) -> None:
        """Log page fetch progress."""
        _print(f"    [Pages] {fetched}/{total} fetched")

    def extracted(self, companies: int, kept: int, dropped: int = 0) -> None:
        """Log extraction results."""
        if dropped > 0:
            _print(f"    [Extracted] {companies} companies ({kept} kept, {dropped} dropped)")
        else:
            _print(f"    [Extracted] {companies} companies ({kept} kept)")

    def deduped(self, before: int, after: int) -> None:
        """Log deduplication results."""
        _print(f"  [Deduped] {before} -> {after} companies")

    def tier_distribution(self, tiers: dict[str, int]) -> None:
        """Log tier distribution."""
        tier_str = ", ".join(f"{k}={v}" for k, v in sorted(tiers.items()))
        _print(f"  [Tiers] {tier_str}")

    def skip(self, reason: str, detail: str) -> None:
        """Log a skip/drop with reason (verbose only)."""
        if self.verbose:
            _print(f"    [Skip] {reason}: {detail[:60]}...")

    def heartbeat(self, activity: str = "Working") -> None:
        """
        Emit a heartbeat if nothing has happened recently.
        Call this periodically during long waits.
        """
        now = datetime.now(UTC)
        elapsed_since_last = (now - self.last_heartbeat).total_seconds()

        if elapsed_since_last >= 30:  # Heartbeat every 30s
            total_elapsed = (now - self.start_time).total_seconds()
            _print(f"  [Heartbeat] {activity}... ({total_elapsed:.0f}s elapsed)")
            self.last_heartbeat = now

    def finish(self, leads: int, output_dir: str = "") -> None:
        """Log run completion."""
        elapsed = (datetime.now(UTC) - self.start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        _print(f"\n[ShouDao] Run complete in {minutes}m{seconds}s")
        _print(f"  Leads: {leads}")
        if output_dir:
            _print(f"  Output: {output_dir}")

    def error(self, msg: str) -> None:
        """Log an error."""
        _eprint(f"[Error] {msg}")

    def warning(self, msg: str) -> None:
        """Log a warning."""
        _eprint(f"[Warning] {msg}")
