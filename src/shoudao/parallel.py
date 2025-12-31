"""
ShouDao parallel processing utilities.

Provides:
- Parallel extraction (Story 17.3)
- Streaming advice generation (Story 17.1)
- Incremental output writes (Story 17.2)
"""

import csv
import json
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import Queue
from typing import Any

# Force line buffering for immediate output
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore
except Exception:
    pass


class IncrementalCSVWriter:
    """Write CSV rows incrementally as leads come in (Story 17.2)."""

    def __init__(self, path: Path, fieldnames: list[str]):
        self.path = path
        self.fieldnames = fieldnames
        self._file = None
        self._writer = None
        self._lock = threading.Lock()
        self._count = 0

    def __enter__(self):
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.fieldnames)
        self._writer.writeheader()
        self._file.flush()
        return self

    def __exit__(self, *args):
        if self._file:
            self._file.close()

    def write_row(self, row: dict[str, Any]) -> None:
        """Write a single row (thread-safe)."""
        with self._lock:
            if self._writer:
                # Only include fields that are in fieldnames
                filtered = {k: v for k, v in row.items() if k in self.fieldnames}
                self._writer.writerow(filtered)
                self._file.flush()
                self._count += 1

    @property
    def count(self) -> int:
        return self._count


class IncrementalJSONWriter:
    """Write JSON objects incrementally as leads come in (Story 17.2).

    Uses JSON Lines format (one JSON object per line) for incremental writes.
    At close, rewrites as proper JSON array for compatibility.
    """

    def __init__(self, path: Path):
        self.path = path
        self._items: list[dict] = []
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        # Write final JSON array
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._items, f, indent=2, default=str)

    def write_item(self, item: dict) -> None:
        """Add an item (thread-safe)."""
        with self._lock:
            self._items.append(item)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._items)


def parallel_extract(
    fetch_results: list,
    extractor,
    prompt: str,
    max_workers: int = 5,
    on_lead_extracted: Callable | None = None,
) -> tuple[list, list[str]]:
    """
    Extract leads from pages in parallel (Story 17.3).

    Args:
        fetch_results: List of FetchResult objects
        extractor: Extractor instance
        prompt: The search prompt
        max_workers: Max concurrent extractions (default 5)
        on_lead_extracted: Callback(lead) called for each extracted lead

    Returns:
        Tuple of (all_leads, errors)
    """
    all_leads = []
    errors = []
    leads_lock = threading.Lock()

    def extract_one(fetch_result):
        """Extract leads from a single page."""
        try:
            extraction = extractor.extract(fetch_result, prompt)
            leads = extractor.extraction_to_leads(extraction, fetch_result.url)

            with leads_lock:
                all_leads.extend(leads)

            # Callback for each lead
            if on_lead_extracted and leads:
                for lead in leads:
                    on_lead_extracted(lead)

            return fetch_result.url, leads, None
        except Exception as e:
            return fetch_result.url, [], str(e)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(extract_one, fr): fr for fr in fetch_results}

        for future in as_completed(futures):
            url, leads, error = future.result()
            if error:
                errors.append(f"Extraction error ({url}): {error}")
                print(f"  Extraction error: {error}", flush=True)
            elif leads:
                print(f"  Found {len(leads)} lead(s) from {url[:60]}...", flush=True)

    return all_leads, errors


def parallel_advise(
    leads: list,
    advisor,
    product_context: str = "",
    seller_context: str = "",
    max_workers: int = 5,
    on_advice_generated: Callable | None = None,
) -> list:
    """
    Generate advice for leads in parallel (Story 17.1).

    Args:
        leads: List of Lead objects
        advisor: Advisor instance
        product_context: Product description
        seller_context: Seller description
        max_workers: Max concurrent advice generations
        on_advice_generated: Callback(lead) called after advice is generated

    Returns:
        List of leads with advice attached
    """
    results_lock = threading.Lock()
    completed = [0]  # Use list for mutable closure

    def advise_one(lead):
        """Generate advice for a single lead."""
        try:
            lead.advice = advisor.generate_advice(lead, product_context, seller_context)
        except Exception as e:
            print(f"  Advice error ({lead.organization.name}): {e}", flush=True)

        with results_lock:
            completed[0] += 1
            if completed[0] % 10 == 0 or completed[0] == len(leads):
                print(f"  Advice: {completed[0]}/{len(leads)} complete", flush=True)

        if on_advice_generated:
            on_advice_generated(lead)

        return lead

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(advise_one, lead) for lead in leads]

        # Wait for all to complete
        for future in as_completed(futures):
            future.result()  # Raises if error

    return leads


class StreamingPipeline:
    """
    A streaming pipeline that processes leads as they come in.

    Flow:
    1. Parallel extraction → leads queue
    2. Parallel advice generation (consumes from queue)
    3. Incremental writes (as leads complete)
    """

    def __init__(
        self,
        extractor,
        advisor,
        extraction_workers: int = 5,
        advice_workers: int = 5,
    ):
        self.extractor = extractor
        self.advisor = advisor
        self.extraction_workers = extraction_workers
        self.advice_workers = advice_workers

        self._leads_queue: Queue = Queue()
        self._advised_leads: list = []
        self._lock = threading.Lock()

    def process(
        self,
        fetch_results: list,
        prompt: str,
        product_context: str = "",
        seller_context: str = "",
        csv_writer: IncrementalCSVWriter | None = None,
        json_writer: IncrementalJSONWriter | None = None,
    ) -> list:
        """
        Process fetch results through extraction and advice in parallel.

        Returns list of advised leads.
        """
        from .dedupe import apply_buyer_gate, dedupe_all_contacts, dedupe_leads, score_all_leads

        # Phase 1: Parallel extraction
        print("  [Parallel] Starting extraction...", flush=True)
        all_leads, errors = parallel_extract(
            fetch_results,
            self.extractor,
            prompt,
            max_workers=self.extraction_workers,
        )
        print(f"  [Parallel] Extracted {len(all_leads)} raw leads", flush=True)

        # Phase 2: Dedupe and score (must be sequential)
        leads = dedupe_leads(all_leads)
        leads = dedupe_all_contacts(leads)
        leads = apply_buyer_gate(leads)
        leads = score_all_leads(leads)
        print(f"  [Parallel] After dedupe/scoring: {len(leads)} leads", flush=True)

        # Phase 3: Parallel advice with incremental writes
        def on_advice_done(lead):
            if csv_writer:
                csv_writer.write_row(lead.to_csv_row())
            if json_writer:
                json_writer.write_item(lead.model_dump())

        print("  [Parallel] Starting advice generation...", flush=True)
        leads = parallel_advise(
            leads,
            self.advisor,
            product_context=product_context,
            seller_context=seller_context,
            max_workers=self.advice_workers,
            on_advice_generated=on_advice_done,
        )

        return leads
