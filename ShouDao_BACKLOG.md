# ShouDao BACKLOG

## Document Info
| Field | Value |
|---|---|
| Project | ShouDao (销售的售 + 导游的导 = "Sales Guide") |
| Version | 0.4 |
| Last Updated | December 29, 2025 |

## Priority map
| Priority | Focus | Outcome |
|---|---|---|
| P0 | CLI MVP | Prompt → leads.csv + report.md |
| P0 | Reproducible recipes | Save & rerun queries |
| P1 | Evidence + compliance | Every lead field is auditable |
| P1 | Dedupe + scoring | Better lead quality, fewer duplicates |
| P1.5 | Backend + Storage | Store runs, learn from queries |
| P2 | UI | View runs, filter leads, download CSV |
| P3 | Monetization | Pay-per-query / SaaS scaffolding |

---

## MVP Exit Criteria (v0.1)
- [x] `shoudao run` produces `leads.csv` + `report.md`
- [ ] Recipes can be saved and rerun to refresh output
- [x] Every exported email/phone/contact channel includes ≥1 evidence URL
- [x] Dedupe merges obvious duplicates by domain/name
- [x] Approach advice is present for each lead or segment
- [ ] Operator manual cleanup ≤ 30 minutes per run

---

## Epic 1 — Project Foundations (P0) ✅ DONE
### Story 1.1 — Define lead data contract
- [x] Task 1.1.1: Define canonical Lead JSON schema (company, contacts, evidence)
- [x] Task 1.1.2: Define CSV column order + types
- [x] Task 1.1.3: Implement CSV exporter

### Story 1.2 — Run artifacts + folder layout
- [x] Task 1.2.1: Create run folder structure under `runs/`
- [x] Task 1.2.2: Save `sources.json` (queries, SERP URLs, fetch timestamps)
- [x] Task 1.2.3: Save `report.md` summary template

---

## Epic 2 — Recipes + Query Planner (P0) 🔶 PARTIAL
### Story 2.1 — Recipe format (YAML)
- [ ] Task 2.1.1: Define `recipes/<slug>.yml` format (prompt, filters, seeds, policy)
- [ ] Task 2.1.2: Implement `shoudao recipe create`
- [ ] Task 2.1.3: Implement `shoudao recipe run`

### Story 2.2 — Prompt → query expansion
- [x] Task 2.2.1: Implement query template library by segment + role + region
- [ ] Task 2.2.2: Optional multilingual query expansion
- [x] Task 2.2.3: Store expanded queries in run artifacts (via sources.json)

---

## Epic 3 — Source Discovery (P0) ✅ DONE
### Story 3.1 — Search API abstraction
- [x] Task 3.1.1: Create provider interface (search(query) → urls)
- [x] Task 3.1.2: Implement 1 provider (Serper.dev)
- [x] Task 3.1.3: Add seed-source mode (MockSearchProvider)

### Story 3.2 — URL triage
- [x] Task 3.2.1: Filter obvious low-signal URLs (social, irrelevant)
- [x] Task 3.2.2: Cap per-domain URLs; diversify domains
- [x] Task 3.2.3: Save triage decisions in `sources.json`

---

## Epic 4 — Fetcher (P0) ✅ DONE
### Story 4.1 — Polite fetch + caching
- [x] Task 4.1.1: HTTP fetch with retries/timeouts (tenacity)
- [x] Task 4.1.2: Domain throttling + concurrency limits (1.5s delay)
- [ ] Task 4.1.3: Cache fetched pages per run

### Story 4.2 — Content normalization
- [x] Task 4.2.1: HTML → text extraction (BeautifulSoup)
- [ ] Task 4.2.2: PDF text extraction (public PDFs only)
- [x] Task 4.2.3: Boilerplate removal / truncation strategy

---

## Epic 5 — Extraction (LLM + rules) (P0) ✅ DONE
### Story 5.1 — LLM extraction contract (structured outputs)
- [x] Task 5.1.1: Define strict JSON schema for extraction (Pydantic)
- [x] Task 5.1.2: Implement OpenAI structured outputs via beta.chat.completions.parse
- [x] Task 5.1.3: Fail-closed behavior when evidence is missing
- [x] Task 5.1.4: Lead-centric extraction (contacts nested under org)

### Story 5.2 — Rules-based fallbacks
- [x] Task 5.2.1: Email/phone regex fallback extractor
- [ ] Task 5.2.2: Contact page discovery (about/contact/team paths)
- [ ] Task 5.2.3: Merge rule-based signals with LLM output

---

## Epic 6 — Evidence + Compliance Guardrails (P1)
### Story 6.1 — Evidence enforcement
- [x] Task 6.1.1: Require evidence URL per exported email/phone/contact
- [x] Task 6.1.2: Store evidence snippets (short) for auditability
- [x] Task 6.1.3: Drop unverifiable fields automatically (fail-soft)

### Story 6.2 — Crawl policy controls
- [ ] Task 6.2.1: Allowlist/blocklist by domain
- [ ] Task 6.2.2: Opt-out list (company names/domains)
- [ ] Task 6.2.3: Per-run crawl caps (max pages, max domains, max depth)

---

## Epic 7 — Dedupe + Scoring (P1) ✅ DONE
### Story 7.1 — Dedupe engine
- [x] Task 7.1.1: Normalize company key (domain/name)
- [x] Task 7.1.2: Merge contacts under company
- [ ] Task 7.1.3: Duplicate contact detection

### Story 7.2 — Confidence scoring
- [x] Task 7.2.1: Implement heuristic score (evidence-weighted)
- [ ] Task 7.2.2: Explain "why score" in JSON (optional)
- [ ] Task 7.2.3: Add low-confidence flags for operator review

---

## Epic 8 — Approach Advice (P1) ✅ DONE
### Story 8.1 — Advice generator
- [x] Task 8.1.1: Lead segmentation (company_type + role_category)
- [x] Task 8.1.2: Generate recommended angle + first offer
- [x] Task 8.1.3: Generate 1 qualifying question per lead/segment

---

## Epic 11 — Backend + Storage (P1.5) 🆕 NEW
> Store run results to learn from queries, improve UX, and enable future features.

### Story 11.1 — Run persistence
- [ ] Task 11.1.1: Define database schema (SQLite for MVP, Postgres-ready)
- [ ] Task 11.1.2: Store RunResult + leads after each run
- [ ] Task 11.1.3: CLI command `shoudao history` to list past runs
- [ ] Task 11.1.4: CLI command `shoudao show <run_id>` to view run details

### Story 11.2 — Query analytics
- [ ] Task 11.2.1: Track prompt → lead count + quality metrics
- [ ] Task 11.2.2: Identify high-performing query patterns
- [ ] Task 11.2.3: Surface "similar prompts" suggestions

### Story 11.3 — Lead database
- [ ] Task 11.3.1: Dedupe leads across runs (global lead pool)
- [ ] Task 11.3.2: Track lead quality over time (was it contacted? converted?)
- [ ] Task 11.3.3: CLI command `shoudao leads` to search all leads

### Story 11.4 — API layer (prep for UI)
- [ ] Task 11.4.1: FastAPI skeleton with `/runs`, `/leads` endpoints
- [ ] Task 11.4.2: OpenAPI spec for frontend integration
- [ ] Task 11.4.3: Auth placeholder (API keys for now)

---

## Epic 9 — UI (P2)
- [ ] Task 9.1: Run history view + download CSV
- [ ] Task 9.2: Lead table with filters (country, type, confidence)
- [ ] Task 9.3: Evidence viewer per lead

---

## Epic 10 — Monetization (P3)
- [ ] Task 10.1: Usage metering per query/run
- [ ] Task 10.2: Pay-per-query scaffolding
- [ ] Task 10.3: SaaS auth + billing integration (later)

---

## Technical Debt / Improvements
- [ ] Switch `datetime.utcnow()` → `datetime.now(timezone.utc)` (done in models)
- [ ] Add EmailStr validation for email fields
- [ ] Add phone number normalization
- [ ] Make confidence scoring explainable (log contributions)
- [ ] Add retry/backoff for search API 429s
- [ ] Per-run request budget knobs
