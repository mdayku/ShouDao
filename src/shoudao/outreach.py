"""
ShouDao Gmail Outreach Module

Create Gmail drafts for eligible leads (HITL - Human In The Loop).
- Reads leads.json
- Filters by email + confidence + needs_review
- Creates Gmail drafts (no sending)
- Writes/updates outreach_log.csv (idempotent)

Gmail API Calls:
1. Build service: googleapiclient.discovery.build("gmail", "v1", credentials=creds)
2. Create draft: service.users().drafts().create(userId="me", body={"message": {"raw": raw}})
3. List drafts: service.users().drafts().list(userId="me", maxResults=10)
"""

from __future__ import annotations

import base64
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

# Gmail API scope - draft-only (minimal permissions)
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


@dataclass
class DraftCandidate:
    """A lead ready for draft creation."""

    lead_id: str  # dedupe_key
    email: str
    org_name: str
    subject: str
    body: str
    confidence: float
    needs_review: bool


def utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_outreach_log(log_path: Path) -> dict[str, dict[str, str]]:
    """Load existing outreach log. Returns dict keyed by lead_id."""
    if not log_path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with log_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = (row.get("lead_id") or "").strip()
            if lid:
                out[lid] = dict(row)
    return out


def append_log_rows(log_path: Path, rows: list[dict[str, str]]) -> None:
    """Append rows to outreach_log.csv, creating file with header if needed."""
    if not rows:
        return

    fieldnames = ["lead_id", "email", "org_name", "draft_id", "message_id", "status", "created_at"]
    file_exists = log_path.exists()

    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def load_leads_json(leads_path: Path) -> list[dict[str, Any]]:
    """Load leads from JSON file."""
    with leads_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_draft_candidate(lead: dict[str, Any]) -> DraftCandidate | None:
    """Convert a lead dict to a DraftCandidate, or None if ineligible."""
    # Extract required fields
    lead_id = lead.get("dedupe_key", "")
    org = lead.get("organization", {})
    org_name = org.get("name", "")
    advice = lead.get("advice", {})
    confidence = lead.get("confidence", 0.0)
    needs_review = lead.get("needs_review", False)

    # Get primary email from contacts
    email = ""
    for contact in lead.get("contacts", []):
        for channel in contact.get("channels", []):
            if channel.get("type") == "email":
                email = channel.get("value", "")
                if email and "@" in email:
                    break
        if email:
            break

    if not email or not lead_id:
        return None

    # Build subject and body from advice fields
    subject = f"Quick question, {org_name}" if org_name else "Quick question"

    angle = advice.get("recommended_angle", "")
    offer = advice.get("recommended_first_offer", "")
    question = advice.get("qualifying_question", "")

    # Compose body
    body_parts = []
    if org_name:
        body_parts.append(f"Hi {org_name} team,")
    else:
        body_parts.append("Hi there,")

    if angle:
        body_parts.append("")
        body_parts.append(angle)

    if offer:
        body_parts.append("")
        body_parts.append(offer)

    if question:
        body_parts.append("")
        body_parts.append(question)

    body_parts.append("")
    body_parts.append("Best,")
    body_parts.append("[Your Name]")

    body = "\n".join(body_parts).strip()

    return DraftCandidate(
        lead_id=lead_id,
        email=email,
        org_name=org_name,
        subject=subject,
        body=body,
        confidence=confidence,
        needs_review=needs_review,
    )


def is_eligible(candidate: DraftCandidate, min_confidence: float) -> tuple[bool, str]:
    """Check if a candidate is eligible for draft creation."""
    if not candidate.email or "@" not in candidate.email:
        return False, "missing_email"
    if not candidate.subject or not candidate.body:
        return False, "missing_outreach_copy"
    if candidate.needs_review:
        return False, "needs_review"
    if candidate.confidence < min_confidence:
        return False, "below_confidence"
    return True, "ok"


def build_raw_email(to_email: str, subject: str, body: str, from_email: str | None = None) -> str:
    """Build RFC 2822 raw message, base64url encoded."""
    msg = EmailMessage()
    msg["To"] = to_email
    msg["Subject"] = subject
    if from_email:
        msg["From"] = from_email

    # Plain text only (lowest friction for drafts/review)
    msg.set_content(body)

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")


def get_gmail_service(credentials_json: Path, token_json: Path) -> Any:
    """
    Authenticate and return Gmail API service.

    First run will open a browser for OAuth consent.
    Subsequent runs use cached token.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        raise ImportError(
            "Gmail API dependencies not installed. Run:\n"
            "  pip install google-auth google-auth-oauthlib google-api-python-client"
        ) from e

    creds = None
    if token_json.exists():
        creds = Credentials.from_authorized_user_file(str(token_json), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_json.exists():
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {credentials_json}\n"
                    "Download from Google Cloud Console -> APIs & Services -> Credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_json), SCOPES)
            creds = flow.run_local_server(port=0)
        token_json.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def create_draft(service: Any, raw: str) -> tuple[str, str]:
    """Create a Gmail draft. Returns (draft_id, message_id)."""
    draft = (
        service.users()
        .drafts()
        .create(
            userId="me",
            body={"message": {"raw": raw}},
        )
        .execute()
    )

    draft_id = draft.get("id", "")
    message_id = (draft.get("message") or {}).get("id", "")
    return draft_id, message_id


def create_drafts_from_leads(
    leads_json: Path,
    log_csv: Path,
    credentials_json: Path,
    token_json: Path,
    min_confidence: float = 0.6,
    max_drafts: int = 0,
    from_email: str | None = None,
    dry_run: bool = False,
) -> int:
    """
    Create Gmail drafts for eligible leads.

    Args:
        leads_json: Path to leads.json file
        log_csv: Path to outreach_log.csv (idempotent)
        credentials_json: Path to Gmail OAuth credentials
        token_json: Path to cached token
        min_confidence: Minimum confidence threshold
        max_drafts: Max drafts to create (0 = no limit)
        from_email: Optional From address
        dry_run: If True, don't actually create drafts

    Returns:
        Number of drafts created
    """
    # Ensure immediate output
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore
    start_time = time.time()

    def elapsed() -> str:
        return f"{int(time.time() - start_time)}s"

    print(f"[{elapsed()}] Loading leads from {leads_json}", flush=True)
    leads = load_leads_json(leads_json)
    print(f"[{elapsed()}] Loaded {len(leads)} total leads", flush=True)

    # Convert to draft candidates
    candidates = []
    for lead in leads:
        candidate = build_draft_candidate(lead)
        if candidate:
            candidates.append(candidate)
    print(f"[{elapsed()}] {len(candidates)} leads have email addresses", flush=True)

    # Load existing log for idempotency
    existing = load_outreach_log(log_csv)
    already_done = set(existing.keys())
    print(f"[{elapsed()}] {len(already_done)} already processed (in log)", flush=True)

    # Filter eligible candidates
    eligible = []
    for c in candidates:
        if c.lead_id in already_done:
            continue
        ok, _reason = is_eligible(c, min_confidence)
        if ok:
            eligible.append(c)

    print(f"[{elapsed()}] {len(eligible)} eligible for drafting", flush=True)

    if not eligible:
        print("[outreach] No eligible leads to draft.", flush=True)
        return 0

    if dry_run:
        print(f"[DRY RUN] Would create {len(eligible)} drafts", flush=True)
        for i, c in enumerate(eligible[:10], 1):
            print(f"  {i}. {c.email} - {c.org_name}", flush=True)
        if len(eligible) > 10:
            print(f"  ... and {len(eligible) - 10} more", flush=True)
        return 0

    # Authenticate Gmail
    print(f"[{elapsed()}] Authenticating Gmail...", flush=True)
    service = get_gmail_service(credentials_json, token_json)
    print(f"[{elapsed()}] Gmail authenticated", flush=True)

    # Create drafts
    created_rows = []
    total = min(len(eligible), max_drafts) if max_drafts > 0 else len(eligible)

    for idx, candidate in enumerate(eligible[:total], start=1):
        print(f"[{elapsed()}] [{idx}/{total}] Drafting -> {candidate.email}", flush=True)

        raw = build_raw_email(
            to_email=candidate.email,
            subject=candidate.subject,
            body=candidate.body,
            from_email=from_email,
        )

        draft_id, message_id = create_draft(service, raw)
        print(f"[{elapsed()}]     Draft created (id={draft_id[:12]}...)", flush=True)

        created_rows.append(
            {
                "lead_id": candidate.lead_id,
                "email": candidate.email,
                "org_name": candidate.org_name,
                "draft_id": draft_id,
                "message_id": message_id,
                "status": "drafted",
                "created_at": utc_now_iso(),
            }
        )

    # Write log
    append_log_rows(log_csv, created_rows)
    print(f"[{elapsed()}] Created {len(created_rows)} drafts. Log: {log_csv}", flush=True)

    return len(created_rows)

