# ShouDao Architecture

> A programmable research operator that converts natural language intent into structured business artifacts.

## Overview

ShouDao is a **deep agent system** — not a chatbot, not a scraper, not a static database. It's an orchestrated pipeline that:

1. Encodes business intent (buyer discovery, geography, product)
2. Lets the model plan the search space
3. Grounds on real web sources
4. Extracts structured entities with validation
5. Iterates until constraints are satisfied
6. Delivers auditable business artifacts (CSV + report + sources)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTENT                                    │
│  "Find Caribbean window/door suppliers for hotel construction"          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      WORLD CONTEXT PROVIDER                              │
│  Injects explicit facts: countries, languages, GDP, trade relations     │
│  NOT hidden inside the LLM — auditable YAML                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         QUERY PLANNER                                    │
│  Expands intent → multilingual search queries                           │
│  Spanish (PR, DR) • French (Martinique, Guadeloupe) • Dutch (Aruba)    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        SEARCH PROVIDER                                   │
│  Serper API → real Google SERPs                                         │
│  Filters: social media, PDFs, irrelevant domains                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           FETCHER                                        │
│  Polite HTTP with rate limiting + retries                               │
│  Extracts text content from HTML                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          EXTRACTOR                                       │
│  LLM + Pydantic structured outputs                                      │
│  Page classifier: directory vs company_site                             │
│  Guardrail: 1 page = 1 company (unless directory)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      VALIDATION GATES                                    │
│  • Evidence required for all contact channels                           │
│  • Domain alignment check (org website vs source URL)                   │
│  • Fail-closed: no evidence = drop the field                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      DEDUPE + SCORING                                    │
│  Normalize by domain/name                                               │
│  Score: email (+0.25), role (+0.20), evidence (+0.20), phone (+0.15)   │
│  Penalty: domain misalignment (-0.30)                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          ADVISOR                                         │
│  LLM generates outreach advice per lead                                 │
│  Uses seller_context + product_context (NOT in search)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       BUSINESS ARTIFACTS                                 │
│  leads.csv    — flat export for sales teams                             │
│  leads.json   — canonical structured data                               │
│  sources.json — audit trail (what we searched, fetched, extracted)     │
│  report.md    — run summary with stats                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Architectural Decisions

### 1. Separation of Concerns

The system separates three distinct phases:

| Phase | Purpose | Context Used |
|-------|---------|--------------|
| **Discovery** | Find who exists | Buyer-only prompt, geography |
| **Extraction** | Structure the data | Evidence requirements, schemas |
| **Advice** | How to engage | Seller context, product context |

**Critical insight:** Search should be buyer-centric. Seller context belongs only in the advice phase. Mixing them causes exporter leakage.

### 2. World Context Provider (MCP-Style)

World knowledge is **not hidden inside the LLM**. It's explicit:

```yaml
# data/world_context.yaml
- code: JM
  name: Jamaica
  languages: [en]
  gdp_bucket: medium
  china_trade: active
  construction_activity: medium-high
```

This enables:
- Auditable query planning
- Deterministic language selection
- Controllable market targeting
- "Why did we search Spanish?" has an answer

### 3. Fail-Closed Validation

```python
# Every contact channel MUST have evidence
class ContactChannel(BaseModel):
    type: ContactChannelType
    value: str
    evidence: list[Evidence]  # Required, not optional
```

- No evidence → field is dropped
- Invalid URL → lead is flagged
- Domain mismatch → confidence penalty

### 4. Directory Discipline

The extractor classifies every page:

```python
PageType = Literal["directory", "company_site", "article", "other"]
```

**Rule:** A page may only emit multiple companies if `page_type == "directory"`.

This prevents the "Domus Windows contact page → 13 leads" problem.

### 5. Evidence-First Design

Every field that matters has provenance:

```python
class Evidence(BaseModel):
    url: HttpUrl           # Where we found it
    snippet: str | None    # The actual text
    accessed_at: datetime  # When we saw it
```

This makes the output:
- Defensible to clients
- Auditable for compliance
- Debuggable when wrong

---

## Component Map

```
src/shoudao/
├── cli.py           # Command-line interface
├── pipeline.py      # Orchestrates the full run
├── world_context.py # MCP-style world knowledge provider
├── search.py        # Query expansion + Serper API
├── fetcher.py       # Polite HTTP fetching
├── extractor.py     # LLM extraction + page classification
├── dedupe.py        # Deduplication + scoring
├── advisor.py       # Outreach advice generation
├── exporter.py      # CSV/JSON export with fallbacks
├── models.py        # Pydantic schemas (Lead, Organization, etc.)
└── sources.py       # Audit trail generation

data/
└── world_context.yaml  # Authoritative country/language facts
```

---

## Data Models

### Lead (Canonical Unit)

```python
class Lead(BaseModel):
    organization: Organization
    contacts: list[Contact]
    confidence: float           # 0-1 score
    evidence: list[Evidence]
    advice: ApproachAdvice | None
    
    # Source tracking
    extracted_from_url: str     # Audit trail
    domain_aligned: bool        # Org domain matches source?
    needs_review: bool          # Flagged for manual check
```

### Organization

```python
class Organization(BaseModel):
    name: str
    org_type: OrgType           # supplier, distributor, contractor, etc.
    industries: list[str]
    country: str | None
    region: str | None
    website: HttpUrl | None
    evidence: list[Evidence]    # Required
```

### Contact Channel

```python
class ContactChannel(BaseModel):
    type: ContactChannelType    # email, phone, linkedin, etc.
    value: str
    evidence: list[Evidence]    # Every channel needs proof
```

---

## Quality Gates

### Gate 1: Page Classification
```
If page_type != "directory" and len(leads) > 1:
    leads = leads[:1]  # Force single company
```

### Gate 2: Domain Alignment
```
If org_website_domain != source_url_domain:
    domain_aligned = False
    needs_review = True
    confidence -= 0.30
```

### Gate 3: Evidence Requirement
```
If contact_channel has no evidence:
    drop the channel (fail-soft)

If lead has no evidence at all:
    drop the lead (fail-closed)
```

### Gate 4: Region Anchoring
```
Prompt includes: "Exclude China-based exporters"
Result: China leakage dropped from 8 to 0
```

---

## Why This Differs From "Agent Demos"

| Typical Demo | ShouDao |
|--------------|---------|
| Generates text | Produces structured data |
| Maybe browses once | Fetches 50+ real pages |
| Hallucinates confidently | Drops fields without evidence |
| No grounding | Every fact has a source URL |
| No validation | Pydantic schemas, fail-closed |
| No accountability | Full audit trail (sources.json) |
| Can't explain decisions | World context is explicit YAML |

---

## Extension Points

### Adding a New Region

1. Add countries to `data/world_context.yaml`
2. Run: `shoudao world --region <name>`
3. Verify derived prompt makes sense

### Adding a New Data Source

1. Implement `SearchProvider` interface in `search.py`
2. Add to `get_search_provider()` factory
3. Update `RunConfig.search_provider` type

### Adding a New Language

1. Add to `languages:` section in `world_context.yaml`
2. Include keyword translations
3. System auto-expands queries for countries using that language

---

## Performance Characteristics

| Metric | Typical Value |
|--------|---------------|
| Queries generated | 29 (multilingual expansion) |
| URLs discovered | 200 |
| Pages fetched | 54 (rate limited) |
| Leads extracted | 70-90 |
| Leads after dedupe | 65-85 |
| Total runtime | 8-10 minutes |
| Cost per run | ~$0.50-1.00 (GPT-4o) |

---

## Future Architecture (API Mode)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│ Orchestrator│────▶│   Workers   │
│   (API)     │     │  (queues)   │     │ (parallel)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Cache     │
                    │ (search +   │
                    │  fetch)     │
                    └─────────────┘
```

Benefits:
- Parallelized search/fetch per country
- Cached results across runs
- Memory: "what changed since last month?"
- Refinement loops: learn which sources are high-yield

---

## Summary

ShouDao is a **programmable research operator** that:

1. Takes natural language intent
2. Injects explicit world context (not LLM assumptions)
3. Plans multilingual search strategies
4. Grounds on real web sources
5. Extracts with strict validation
6. Produces auditable business artifacts

It's not a demo. It's leverage.

