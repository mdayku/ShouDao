# ShouDao BACKLOG

## Document Info
| Field | Value |
|---|---|
| Project | ShouDao (销售的售 + 导游的导 = "Sales Guide") |
| Version | 0.7 |
| Last Updated | December 30, 2025 |

---

## Configuration

| Setting | Value | Env Var | Location |
|---------|-------|---------|----------|
| LLM model | gpt-4o-mini (default) | `SHOUDAO_MODEL` | `extractor.py`, `advisor.py` |
| Search provider | Serper.dev | `SERPER_API_KEY` | `search.py` |
| Rate limit | 1.5s between requests | — | `fetcher.py` |
| Max pages per run | 100 | — | `pipeline.py` |

### Model Compatibility Notes

| Model | Status | Notes |
|-------|--------|-------|
| `gpt-4o-mini` | ✅ Supported | Default, cost-effective |
| `gpt-4o` | ✅ Supported | Higher quality extraction |
| `gpt-5.2` | ⚠️ Requires migration | Needs Responses API (see Epic 12) |
| `gpt-5-mini` | ⚠️ Requires migration | Needs Responses API |

---

## Priority Map

| Priority | Focus | Outcome |
|---|---|---|
| P0 | CLI MVP | Prompt → leads.csv + report.md |
| P0 | Reproducible recipes | Save & rerun queries |
| **P0.5** | **Gauntlet Talent Discovery** | **Candidate signal extraction for Cohort 4** |
| P1 | Evidence + compliance | Every lead field is auditable |
| P1 | Dedupe + scoring | Better lead quality, fewer duplicates |
| P1.5 | Backend + Storage | Store runs, learn from queries |
| P2 | UI | View runs, filter leads, download CSV |
| P3 | Monetization | Pay-per-query / SaaS scaffolding |

---

## 🎯 Recommended Next Steps

### Talent Discovery is MVP-Ready
Core talent discovery works without LinkedIn:
- ✅ `shoudao talent` command
- ✅ Candidate model + scoring
- ✅ Talent-specific query expansion
- ✅ Age estimation + salary bands
- ✅ Page caching per run
- ✅ Rate limit handling (429 backoff)

### Next Priorities

| Task | Why | Effort |
|------|-----|--------|
| **Epic 2/4/5/6/7 Cleanup** | Complete remaining MVP tasks | 4h |
| **Task 12.1.3**: Model cost tracking | Know how much each run costs | 2h |
| **Story 13.5**: X/Twitter integration | Signal-first sourcing | 6h |

### LinkedIn Status ✅ WORKING
LinkedIn integration is now **available** via Apify:
- ✅ Apify `harvestapi/linkedin-profile-search` actor
- ✅ `shoudao talent --linkedin` command
- ✅ Same export infrastructure (JSON/CSV/Excel/MD)

**Usage:**
```bash
shoudao talent --linkedin --prompt "software engineers AI" --max-results 25
```

**Costs:** ~$0.10/search page + $0.004/profile (Full mode)

### Can Skip

| Task | Why |
|------|-----|
| Task 4.2.2 (PDF extraction) | Talent surfaces are web-native |
| Story 6.2 (Crawl policy) | Can add later if needed |

---

## MVP Exit Criteria (v0.1)

- [x] `shoudao run` produces `leads.csv` + `report.md` + `sources.json`
- [x] Recipes can be saved and rerun to refresh output
- [x] Every exported contact channel includes ≥1 evidence URL
- [x] Dedupe merges obvious duplicates by domain/name
- [x] Approach advice is present for each lead
- [x] Advice is product-context-aware (not generic)
- [ ] Operator manual cleanup ≤ 30 minutes per run

---

## Epic 1 — Project Foundations (P0) ✅ DONE

### Story 1.1 — Define lead data contract
- [x] Task 1.1.1: Define canonical Lead JSON schema (org, contacts, evidence)
- [x] Task 1.1.2: Define CSV column order + types (23 columns)
- [x] Task 1.1.3: Implement CSV exporter

### Story 1.2 — Run artifacts + folder layout
- [x] Task 1.2.1: Create run folder structure under `runs/`
- [x] Task 1.2.2: Save `sources.json` (queries, URLs, fetch status, domain counts)
- [x] Task 1.2.3: Save `report.md` summary template

---

## Epic 2 — Recipes + Query Planner (P0) ✅ DONE

### Story 2.1 — Recipe format (YAML)
- [x] Task 2.1.1: Define `recipes/<slug>.yml` format (prompt, filters, seeds, policy)
- [x] Task 2.1.2: Implement `shoudao recipe create`
- [x] Task 2.1.3: Implement `shoudao recipe run`

### Story 2.2 — Prompt → query expansion
- [x] Task 2.2.1: Implement query template library by segment + role + region
- [x] Task 2.2.2: Multilingual query expansion (FR/ES/NL for Caribbean) — in `search.py`
- [x] Task 2.2.3: Store expanded queries in run artifacts (via sources.json)

---

## Epic 3 — Source Discovery (P0) ✅ DONE

### Story 3.1 — Search API abstraction
- [x] Task 3.1.1: Create provider interface (search(query) → urls)
- [x] Task 3.1.2: Implement Serper.dev provider
- [x] Task 3.1.3: Add seed-source mode (MockSearchProvider)

### Story 3.2 — URL triage
- [x] Task 3.2.1: Filter low-signal URLs (social, aggregators)
- [x] Task 3.2.2: Cap per-domain URLs; diversify domains
- [x] Task 3.2.3: Save triage decisions in `sources.json`

---

## Epic 4 — Fetcher (P0) ✅ COMPLETE

### Story 4.1 — Polite fetch + caching
- [x] Task 4.1.1: HTTP fetch with retries/timeouts (tenacity)
- [x] Task 4.1.2: Domain throttling (1.5s delay)
- [x] Task 4.1.3: Cache fetched pages per run — in `fetcher.py`

### Story 4.2 — Content normalization
- [x] Task 4.2.1: HTML → text extraction (BeautifulSoup + lxml)
- [ ] Task 4.2.2: PDF text extraction (public PDFs only) — **deferred, low priority**
- [x] Task 4.2.3: Boilerplate removal / truncation (8000 char limit)

---

## Epic 5 — Extraction (LLM + rules) (P0) ✅ DONE

### Story 5.1 — LLM extraction contract
- [x] Task 5.1.1: Define strict JSON schema (Pydantic, extra="forbid")
- [x] Task 5.1.2: Implement OpenAI structured outputs (beta.chat.completions.parse)
- [x] Task 5.1.3: Fail-closed at lead level, fail-soft at field level
- [x] Task 5.1.4: Lead-centric extraction (contacts nested under org)

### Story 5.2 — Data normalization
- [x] Task 5.2.1: `_normalize_website()` - bare domains → https://, junk filtering
- [x] Task 5.2.2: `_clean_value()` - sentinel strings ("Not provided") → None
- [x] Task 5.2.3: `_normalize_country()` - USA/U.S. → "United States"
- [x] Task 5.2.4: Email/phone regex fallback extractor

### Story 5.3 — Rules-based fallbacks
- [ ] Task 5.3.1: Contact page discovery (about/contact/team paths)
- [ ] Task 5.3.2: Merge rule-based signals with LLM output

---

## Epic 6 — Evidence + Compliance Guardrails (P1) ✅ DONE

### Story 6.1 — Evidence enforcement
- [x] Task 6.1.1: Require evidence URL per contact channel (ContactChannel model)
- [x] Task 6.1.2: Store evidence snippets (max 500 chars)
- [x] Task 6.1.3: Drop unverifiable fields automatically

### Story 6.2 — Crawl policy controls
- [x] Task 6.2.1: Blocklist by domain — `blocked_domains` in RunConfig/Recipe
- [ ] Task 6.2.2: Opt-out list (company names/domains) — not yet implemented
- [x] Task 6.2.3: Per-run crawl caps — `max_pages` in Recipe

---

## Epic 7 — Dedupe + Scoring (P1) ✅ COMPLETE

### Story 7.1 — Dedupe engine
- [x] Task 7.1.1: Normalize company key (domain/name)
- [x] Task 7.1.2: Merge contacts under company
- [x] Task 7.1.3: Duplicate contact detection (by email)

### Story 7.2 — Confidence scoring
- [x] Task 7.2.1: Heuristic score (email +0.25, role +0.20, evidence +0.20, phone +0.15, website +0.10)
- [x] Task 7.2.2: Explain score contributions in JSON (`score_contributions` field on Lead)
- [x] Task 7.2.3: Low-confidence flags — `needs_review` field on Lead

---

## Epic 8 — Approach Advice (P1) ✅ DONE

### Story 8.1 — Advice generator
- [x] Task 8.1.1: Lead segmentation (org_type + role_category)
- [x] Task 8.1.2: Generate recommended angle + first offer
- [x] Task 8.1.3: Generate qualifying question
- [x] Task 8.1.4: Product-context-aware advice (not generic PM software)

---

## Epic 11 — Backend + Storage (P1.5) 🆕

### Story 11.1 — Run persistence
- [ ] Task 11.1.1: Define database schema (SQLite for MVP)
- [ ] Task 11.1.2: Store RunResult + leads after each run
- [ ] Task 11.1.3: CLI command `shoudao history`
- [ ] Task 11.1.4: CLI command `shoudao show <run_id>`

### Story 11.2 — Query analytics
- [ ] Task 11.2.1: Track prompt → lead count + quality metrics
- [ ] Task 11.2.2: Identify high-performing query patterns
- [ ] Task 11.2.3: Surface "similar prompts" suggestions

### Story 11.3 — Lead database
- [ ] Task 11.3.1: Dedupe leads across runs (global lead pool)
- [ ] Task 11.3.2: Track lead quality over time
- [ ] Task 11.3.3: CLI command `shoudao leads`

### Story 11.4 — API layer (prep for UI)
- [ ] Task 11.4.1: FastAPI skeleton with `/runs`, `/leads` endpoints
- [ ] Task 11.4.2: OpenAPI spec
- [ ] Task 11.4.3: Auth placeholder (API keys)

---

## Epic 9 — UI (P2)

- [ ] Task 9.1: Run history view + download CSV
- [ ] Task 9.2: Lead table with filters (country, type, confidence)
- [ ] Task 9.3: Evidence viewer per lead

---

## Epic 10 — Monetization (P3)

- [ ] Task 10.1: Usage metering per query/run
- [ ] Task 10.2: Pay-per-query scaffolding
- [ ] Task 10.3: SaaS auth + billing integration

---

## Epic 12 — Model Configuration (P1) 🆕

### Story 12.1 — Model selection ✅ DONE
- [x] Task 12.1.1: Make extraction model configurable (`SHOUDAO_MODEL` env var)
- [x] Task 12.1.2: Make advice model configurable (same env var)
- [ ] Task 12.1.3: Add model cost tracking per run

### Story 12.2 — GPT-5.x / Responses API Migration (P2)
OpenAI's new GPT-5.x models require the **Responses API** instead of Chat Completions.

Key changes needed:
- [ ] Task 12.2.1: Migrate `extractor.py` from `client.chat.completions.parse()` to `client.responses.create()`
- [ ] Task 12.2.2: Migrate `advisor.py` to Responses API
- [ ] Task 12.2.3: Handle chain-of-thought passing via `previous_response_id`
- [ ] Task 12.2.4: Update structured output to use CFG grammars (if needed)
- [ ] Task 12.2.5: Test with `gpt-5.2` and `gpt-5-mini`

Benefits of migration:
- Better intelligence (CoT passing between turns)
- Fewer reasoning tokens, lower latency
- Higher cache hit rates
- Access to new `reasoning.effort` and `verbosity` parameters

### Story 12.3 — Deep research mode (future)
- [ ] Task 12.3.1: Define guardrails for deep research prompts
- [ ] Task 12.3.2: Integrate Perplexity API as alternative search provider
- [ ] Task 12.3.3: Multi-iteration search + synthesis pipeline

---

## Epic 14 — Recall Improvements (P0) ✅ DONE

Goal: Get from 57 leads to 100+ while maintaining quality.

### Story 14.1 — Tiered Buyer Classification ✅ DONE
Replace hard buyer gate with tiered scoring.

- [x] Task 14.1.1: Add `buyer_tier` field to Lead model (A/B/C)
- [x] Task 14.1.2: Add `buyer_likelihood` score (0-1)
- [x] Task 14.1.3: Keep uncertain buyers as Tier B/C instead of dropping
- [x] Task 14.1.4: Add tier breakdown to report.md

Tier definitions:
- **Tier A**: Caribbean-based, clear buyer type (distributor/installer/contractor)
- **Tier B**: Caribbean-based, unclear type OR weak website
- **Tier C**: Related industry, potential buyer, needs verification

### Story 14.2 — Contractor/Builder Expansion ✅ DONE
Add queries to find builders who use windows/doors (not just sell them).

- [x] Task 14.2.1: Add expansion queries: "construction company hotel resort [island]"
- [x] Task 14.2.2: Add expansion queries: "general contractor commercial [island]"
- [x] Task 14.2.3: Add expansion queries: "building contractor [island]"
- [x] Task 14.2.4: Add "design build" and "hotel renovation" queries

### Story 14.3 — Directory Harvesting ✅ DONE
Increase directory/list page discovery.

- [x] Task 14.3.1: Add chamber of commerce directory queries
- [x] Task 14.3.2: Add trade association member list queries
- [x] Task 14.3.3: Add "top contractors [island]" queries
- [x] Task 14.3.4: Increase page fetch limit (now 100)

### Story 14.4 — Logging & Observability ✅ DONE
Add structured logging for long runs.

- [x] Task 14.4.1: Add phase logs (Step 1/6, etc.)
- [x] Task 14.4.2: Add country/language progress logs (`ProgressLogger` class)
- [x] Task 14.4.3: Add heartbeat logs for long waits
- [x] Task 14.4.4: Log dropped leads with reason

---

## Epic 15 — Gauntlet Talent Discovery (P0.5) 🆕

Goal: Adapt ShouDao to find high-likelihood applicants for Gauntlet AI Cohort 4.

**Use case:** Signal discovery for talent, not spam outreach. Gauntlet staff handles all contact.

### Qualification Signals (encode these)

A candidate is interesting if they show ≥3 of these:

| Signal | Weight | Source |
|--------|--------|--------|
| CS degree from good school | 0.20 | LinkedIn, personal site |
| Engineering experience (2+ years) | 0.20 | LinkedIn, GitHub, bio |
| Public AI/LLM project | 0.25 | GitHub, HuggingFace, Streamlit |
| Build-in-public posts | 0.15 | Blog, Substack, Twitter |
| Agent/tooling curiosity | 0.10 | Cursor, LangChain, OpenAI mentions |
| Salary likely <$150k | 0.10 | LinkedIn title/company, geography |

### Story 15.1 — Candidate Model ✅ DONE

- [x] Task 15.1.1: Define `Candidate` Pydantic model
  ```python
  class Candidate(BaseModel):
      name: str
      primary_profile: str  # GitHub, personal site
      linkedin_url: str | None
      degree_signal: str | None  # "CS, MIT" or "Self-taught"
      engineering_experience: str | None  # "2 years SWE at startup"
      current_role: str | None
      current_company: str | None
      estimated_salary_band: str | None  # "under_100k", "100k_150k", "150k_plus"
      public_work: list[str]  # repo links, demos, blogs
      ai_signal_score: float  # 0-1
      build_in_public_score: float  # 0-1
      overall_fit_tier: Literal["A", "B", "C"]
      why_flagged: str  # human-readable justification
      evidence: list[Evidence]
  ```
- [x] Task 15.1.2: Define `CandidateSignal` for individual signals (integrated into Candidate)
- [x] Task 15.1.3: Add candidate exporter (CSV/Excel/JSON)

### Story 15.2 — GitHub Integration ✅ DONE

- [x] Task 15.2.1: GitHub API client (with token auth)
- [x] Task 15.2.2: Extract: repos, stars, languages, commit frequency
- [x] Task 15.2.3: Identify AI/LLM repos (keywords: agent, llm, openai, langchain)
- [x] Task 15.2.4: AI signal scoring based on repo analysis
- [x] Task 15.2.5: Build-in-public scoring based on GitHub presence
- [x] Task 15.2.6: Rate limit handling (5000 req/hr with token)

### Story 15.3 — LinkedIn Integration ✅ DONE

**Status:** LinkedIn integration working via Apify.

- ✅ Apify `harvestapi/linkedin-profile-search` — Full profile search with filters
- ✅ Apify `harvestapi/linkedin-profile-scraper` — Individual profile enrichment
- ✅ Integrated into talent pipeline via `--linkedin` flag
- ✅ Same Candidate model and export infrastructure

**Implementation:**
- [x] Task 15.3.1: Evaluate LinkedIn data providers — Apify selected
- [x] Task 15.3.2: Create `LinkedInProvider` class with search/scrape methods
- [x] Task 15.3.3: Define `LinkedInProfile` model for raw data
- [x] Task 15.3.4: Create `linkedin_profile_to_candidate()` converter
- [x] Task 15.3.5: Integrate into `TalentPipeline` with `--linkedin` flag

**Costs:** ~$0.10/search page + $0.004/profile (Full mode), $5 free credits on signup

### Story 15.4 — Talent Query Expansion ✅ DONE

- [x] Task 15.4.1: Define talent-specific query templates
  ```python
  TALENT_QUERIES = [
      'site:github.com "agent" "openai"',
      'site:github.com "streamlit" "llm"',
      '"built with gpt" project',
      '"learning in public" ai',
      '"openai api" project demo',
      '"huggingface spaces" personal',
      '"cursor ai" workflow',
      '"LLM agent" side project',
      'site:substack.com "building" "ai"',
  ]
  ```
- [x] Task 15.4.2: Add "gauntlet ai cohort" adjacent query
- [x] Task 15.4.3: Add university-specific queries (top CS programs)

### Story 15.5 — Candidate Scoring ✅ DONE

- [x] Task 15.5.1: Implement `score_candidate()` function
- [x] Task 15.5.2: Implement `classify_candidate_tier()` (A/B/C)
- [x] Task 15.5.3: Implement salary band estimation logic
- [x] Task 15.5.4: Add `score_contributions` explanation

Tier definitions:
- **Tier A**: CS/eng background + public AI project + likely <$150k
- **Tier B**: Good repos, fewer demos, strong learning trajectory
- **Tier C**: Early but promising, might pass with mentorship

### Story 15.6 — Talent Extraction Prompt ✅ DONE

- [x] Task 15.6.1: Design LLM extraction prompt for candidate signals
- [x] Task 15.6.2: Extract: name, education, experience, project links
- [x] Task 15.6.3: Generate `why_flagged` justification
- [x] Task 15.6.4: Skip advice generation (Gauntlet handles outreach)

### Story 15.7 — CLI Integration ✅ DONE

- [x] Task 15.7.1: Add `shoudao talent` command (not flag)
- [x] Task 15.7.2: Load talent-specific query templates
- [x] Task 15.7.3: Use candidate schema instead of lead schema
- [x] Task 15.7.4: Output `candidates.csv` / `candidates.xlsx` / `candidates.json`

### Story 15.8 — Discovery Surfaces

Priority order:
1. GitHub (repos, READMEs, profiles)
2. LinkedIn (education, experience, salary signals)
3. Personal websites/blogs
4. Substack/Medium (technical writing)
5. Hugging Face Spaces
6. Streamlit demos
7. Twitter/X (optional, low priority)

### Ethical Guardrails (Hard Rules)

- ❌ No email guessing
- ❌ No private contact scraping
- ✅ Only publicly listed contact info
- ✅ Preference for GitHub/Twitter/website contact
- ✅ Clear opt-out language in any outreach (Gauntlet's responsibility)
- ✅ "Saw your public work" justification required

---

## Epic 13 — Data Source Expansion (P2) 🔮 FUTURE

> **Note:** This epic is a wishlist of potential integrations. Most are speculative and depend on API availability, cost, and ToS compliance. Prioritize based on actual need.

### Story 13.1 — LinkedIn Integration ✅ DONE
See Story 15.3 — Implemented via Apify actors.

### Story 13.2 — GitHub API ✅ DONE
- [x] Task 13.2.1: GitHub API client with token auth
- [x] Task 13.2.2: Extract repos, stars, languages, AI repo detection
- [x] Task 13.2.3: Rate limit handling (5000 req/hr with token)
- [x] Task 13.2.4: AI signal scoring based on repo analysis
- [x] Task 13.2.5: Build-in-public scoring

### Story 13.3 — Alternative Search Sources (Low Priority)
- [ ] Task 13.3.1: Bing Search API
- [ ] Task 13.3.2: DuckDuckGo API

### Story 13.5 — X/Twitter Signal-First Flow (v0.8+ Future)
> **Concept:** Prioritize candidates by their X/Twitter activity first, as it's a stronger builder-in-public signal. Then enrich with LinkedIn/GitHub.

**Proposed Flow:**
```
X/Twitter search (AI builders, LLM enthusiasts)
    ↓
LinkedIn enrichment (professional context, education)
    ↓
GitHub enrichment (technical validation, AI repos)
    ↓
Backfill with LinkedIn search (fill quota)
```

**Why X-First?**
- Builder-in-public signal is strongest on X
- AI/ML community is very active on X
- Can find people *before* they update their LinkedIn

**Tasks (not started):**
- [ ] Task 13.5.1: Evaluate X API v2 costs and rate limits
- [ ] Task 13.5.2: Search by keywords (LLM, AI agents, Cursor, etc.)
- [ ] Task 13.5.3: Extract profile → find LinkedIn → enrich
- [ ] Task 13.5.4: Integrate into talent pipeline as primary source option

### Story 13.4 — Business Data APIs (Evaluate as needed)
Potential integrations if budget allows:
- Hunter.io (email discovery)
- Apollo.io (sales intelligence)
- Clearbit (company enrichment)
- Crunchbase (company data)

---

## Technical Debt

| Issue | Status | Notes |
|-------|--------|-------|
| datetime.utcnow() deprecated | ✅ Fixed | Now using datetime.now(timezone.utc) |
| Retry/backoff for API 429s | ✅ Fixed | Added to search, extractor, fetcher |
| Rate limit handling for gpt-4o | ✅ Fixed | Backoff with exponential retry |
| Page caching per run | ✅ Fixed | Cache in run folder, reuse on retry |
| EmailStr validation | ⏳ TODO | Use Pydantic EmailStr for email fields |
| Phone normalization | ⏳ TODO | Standardize phone formats |
| Industry deduplication | ⏳ TODO | Lowercase + synonym map |
| Per-run request budget | ⏳ TODO | max_search_queries, max_pages configs |

---

## Best Practices Learned

### Prompt Separation (Critical)

**Problem:** Conflating buyer discovery with seller intent causes exporter leakage.

**Solution:** Separate concerns into two phases:

| Phase | Purpose | Example |
|-------|---------|---------|
| **Search prompt** | Buyer-only, geography-anchored | "Caribbean-based suppliers, installers. Exclude China exporters." |
| **Seller context** | Post-extraction advice only | "Chinese manufacturer seeking distributors..." |
| **Product context** | Split: search-relevant vs sales-only | Search: "windows, doors, hotels" / Sales: "MOQs, certifications" |

**Result:** China leakage dropped from 1 to 0, US from 8 to 2, Contractors up from 3 to 18.

---

## Session Log

> **Note:** Detailed session logs are maintained in `ShouDao_PRD.md` changelog.
> This section contains only high-level milestones.

| Date | Focus | Key Outcome |
|------|-------|-------------|
| 2025-12-30 | GitHub + LinkedIn + Scoring | Full talent pipeline: LinkedIn → GitHub → Score → Export |
| 2025-12-30 | Recipe system | `shoudao recipe` CRUD commands |
| 2025-12-30 | Talent discovery | Epic 15 complete, `shoudao talent` command |
| 2025-12-29 | Recall improvements | 252 leads per run, tier breakdown |
| 2025-12-29 | MVP build | First successful runs, 25 files |
