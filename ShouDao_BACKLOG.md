# ShouDao BACKLOG

## Document Info
| Field | Value |
|---|---|
| Project | ShouDao (销售的售 + 导游的导 = "Sales Guide") |
| Version | 0.5 |
| Last Updated | December 29, 2025 |

---

## Configuration

| Setting | Value | Env Var | Location |
|---------|-------|---------|----------|
| LLM model | gpt-4o-mini (default) | `SHOUDAO_MODEL` | `extractor.py`, `advisor.py` |
| Search provider | Serper.dev | `SERPER_API_KEY` | `search.py` |
| Rate limit | 1.5s between requests | — | `fetcher.py` |
| Max pages per run | 30 | — | `pipeline.py` |

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
| P1 | Evidence + compliance | Every lead field is auditable |
| P1 | Dedupe + scoring | Better lead quality, fewer duplicates |
| P1.5 | Backend + Storage | Store runs, learn from queries |
| P2 | UI | View runs, filter leads, download CSV |
| P3 | Monetization | Pay-per-query / SaaS scaffolding |

---

## MVP Exit Criteria (v0.1)

- [x] `shoudao run` produces `leads.csv` + `report.md` + `sources.json`
- [ ] Recipes can be saved and rerun to refresh output
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

## Epic 2 — Recipes + Query Planner (P0) 🔶 PARTIAL

### Story 2.1 — Recipe format (YAML)
- [ ] Task 2.1.1: Define `recipes/<slug>.yml` format (prompt, filters, seeds, policy)
- [ ] Task 2.1.2: Implement `shoudao recipe create`
- [ ] Task 2.1.3: Implement `shoudao recipe run`

### Story 2.2 — Prompt → query expansion
- [x] Task 2.2.1: Implement query template library by segment + role + region
- [ ] Task 2.2.2: Optional multilingual query expansion (FR/ES/NL for Caribbean)
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

## Epic 4 — Fetcher (P0) ✅ DONE

### Story 4.1 — Polite fetch + caching
- [x] Task 4.1.1: HTTP fetch with retries/timeouts (tenacity)
- [x] Task 4.1.2: Domain throttling (1.5s delay)
- [ ] Task 4.1.3: Cache fetched pages per run

### Story 4.2 — Content normalization
- [x] Task 4.2.1: HTML → text extraction (BeautifulSoup + lxml)
- [ ] Task 4.2.2: PDF text extraction (public PDFs only)
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
- [ ] Task 6.2.1: Allowlist/blocklist by domain (in RunConfig)
- [ ] Task 6.2.2: Opt-out list (company names/domains)
- [ ] Task 6.2.3: Per-run crawl caps (max pages, max domains)

---

## Epic 7 — Dedupe + Scoring (P1) ✅ DONE

### Story 7.1 — Dedupe engine
- [x] Task 7.1.1: Normalize company key (domain/name)
- [x] Task 7.1.2: Merge contacts under company
- [ ] Task 7.1.3: Duplicate contact detection (by email)

### Story 7.2 — Confidence scoring
- [x] Task 7.2.1: Heuristic score (email +0.25, role +0.20, evidence +0.20, phone +0.15, website +0.10)
- [ ] Task 7.2.2: Explain score contributions in JSON
- [ ] Task 7.2.3: Low-confidence flags for operator review

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

## Epic 13 — Data Source Expansion (P1) 🆕

### Story 13.1 — LinkedIn Integration
- [ ] Task 13.1.1: LinkedIn Sales Navigator API (requires subscription)
- [ ] Task 13.1.2: LinkedIn public profile scraping via Proxycurl/PhantomBuster
- [ ] Task 13.1.3: LinkedIn company page extraction
- [ ] Task 13.1.4: Cross-reference LinkedIn contacts with extracted leads

### Story 13.2 — Expanded Search Sources
- [ ] Task 13.2.1: Bing Search API (diversify from Google/Serper)
- [ ] Task 13.2.2: DuckDuckGo API (privacy-respecting, different index)
- [ ] Task 13.2.3: Industry-specific directories (ThomasNet, Kompass, etc.)
- [ ] Task 13.2.4: Trade association member lists
- [ ] Task 13.2.5: Chamber of Commerce directories
- [ ] Task 13.2.6: Government contractor registries

### Story 13.3 — Media & News Sources
- [ ] Task 13.3.1: Google News API for company mentions
- [ ] Task 13.3.2: Press release aggregators (PR Newswire, BusinessWire)
- [ ] Task 13.3.3: Trade publication scrapers
- [ ] Task 13.3.4: Industry award/recognition lists
- [ ] Task 13.3.5: Conference speaker/exhibitor lists

### Story 13.4 — Business Data APIs
- [ ] Task 13.4.1: Clearbit API for company enrichment
- [ ] Task 13.4.2: Hunter.io for email discovery
- [ ] Task 13.4.3: Apollo.io API integration
- [ ] Task 13.4.4: Crunchbase for company data
- [ ] Task 13.4.5: OpenCorporates for legal entity data

### Story 13.5 — Social & Alternative Sources
- [ ] Task 13.5.1: Twitter/X company account extraction
- [ ] Task 13.5.2: Facebook business page scraping
- [ ] Task 13.5.3: Instagram business profiles
- [ ] Task 13.5.4: YouTube channel/video descriptions
- [ ] Task 13.5.5: Podcast guest databases
- [ ] Task 13.5.6: Glassdoor/Indeed for company info

### Story 13.6 — Geographic & Import/Export Data
- [ ] Task 13.6.1: Import/export databases (ImportGenius, Panjiva)
- [ ] Task 13.6.2: Customs/shipping records APIs
- [ ] Task 13.6.3: Port authority manifests
- [ ] Task 13.6.4: Business license registries by country
- [ ] Task 13.6.5: Real estate development permit databases

---

## Technical Debt

| Issue | Status | Notes |
|-------|--------|-------|
| datetime.utcnow() deprecated | ✅ Fixed | Now using datetime.now(timezone.utc) |
| EmailStr validation | ⏳ TODO | Use Pydantic EmailStr for email fields |
| Phone normalization | ⏳ TODO | Standardize phone formats |
| Industry deduplication | ⏳ TODO | Lowercase + synonym map |
| Retry/backoff for search API 429s | ⏳ TODO | Add to SerperProvider |
| Per-run request budget | ⏳ TODO | max_search_queries, max_pages configs |

---

## Session Log

### 2025-12-29 Session 2
**Commits:** 307906d → f2423d6

**Built:**
- Source-lead validity gate (domain alignment check)
- `extracted_from_url` field on Lead model
- `domain_aligned` and `needs_review` flags
- Configurable LLM model via `SHOUDAO_MODEL` env var
- **Directory page classifier** (directory/company_site/article/other)
- **1-page-1-company guardrail** for non-directory pages
- **Multilingual query expansion** with country → language mapping
- Keyword packs for Spanish, French, Dutch

**Best Run: 91 leads from 51 domains**
| Metric | Value |
|--------|-------|
| Total Leads | 91 |
| Sources | 54 |
| Domains | 51 |
| Queries Generated | 29 |
| Time | ~9 minutes |
| Puerto Rico (ES) | 22 leads |
| Guadeloupe (FR) | 3 leads |

**Guardrails working:**
```
[Guardrail] https://www.artisanwindowsanddoors.com/: page_type=company_site, limiting from 2 to 1 lead
[Guardrail] https://www.martiniquemenuiseries.fr/: page_type=company_site, limiting from 2 to 1 lead
```

**Added to CSV:**
- `extracted_from_url` — the URL that produced this lead
- `domain_aligned` — yes/no if org domain matches source domain
- `needs_review` — flagged for manual review if misaligned

**Documented:**
- GPT-5.x migration path (Story 12.2)
- Model compatibility table

---

### 2025-12-29 Session 1
**Commits:** 5 (281de5a → bae49b2)

**Built:**
- Full MVP pipeline (25 files)
- First successful runs (Florida contractors, Caribbean windows)

**Fixed:**
- Lead-centric extraction (contacts nested under org)
- URL normalization (bare domains, junk filtering)
- Sentinel value cleaning
- Country normalization
- Product-context-aware advice

**Learned:**
- Product/seller context dramatically improves advice quality
- sources.json is essential for debugging
- Ruff lint should be pre-commit, not post-commit
