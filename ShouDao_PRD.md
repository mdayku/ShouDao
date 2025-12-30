# ShouDao PRD (Prompt → Leads CSV + Outreach Advice)


## Document Info
| Field | Value |
|---|---|
| Project | ShouDao (销售的售 + 导游的导 = "Sales Guide") |
| Author | Marcus |
| Version | 0.3 |
| Last Updated | December 29, 2025 |
| Status | Draft |

## One-liner
A **reproducible lead-generation tool** that turns a "Google-style" prompt into a **CSV of potential B2B leads** (companies + decision makers + public contact channels), plus **advice on how to approach** each lead or segment.

## Why now
Manual lead research is slow, inconsistent, and hard to repeat. ShouDao makes a query **repeatable**, **auditable**, and **deliverable**:

**Prompt → Sources → Entities → Contacts → Evidence → CSV + Approach Notes**

---

## Goals
### MVP goals (v0.1)
1. **Prompt → CSV**: One command produces a lead list CSV with a stable schema.
2. **Reproducible**: Save a prompt + filters as a **Query Recipe** and rerun later.
3. **Evidence-first**: Every extracted email/phone/contact channel includes **source URL(s)**.
4. **Public-only**: Collect only information explicitly published on public webpages/directories.
5. **Approach advice**: Provide short, relevant “first intro” guidance per lead (or per segment).

### Non-goals (v0.1)
- No “hacking,” bypassing gated systems, or scraping behind logins.
- No automated outbound messaging/sending (LeadFinder stops at CSV + advice).
- No guarantee of verified emails beyond what’s publicly published.
- No full ZoomInfo feature set (funding, technographics, org charts, etc.).

---

## Personas
1. **Operator (you, initially)**: runs queries and delivers CSVs to clients.
2. **Client (later)**: wants leads + a playbook for initial outreach.
3. **SaaS user (later)**: self-serve UI + pay-per-query or subscription.

---

## Core user stories
- **US-1**: As an Operator, I enter a prompt and get a lead CSV in minutes.
- **US-2**: As an Operator, I can rerun the same query later for a refreshed list.
- **US-3**: As a Client, I get guidance on how to approach each lead.
- **US-4**: As an Operator, I can defend lead quality with source URLs/evidence.
- **US-5 (later)**: As a SaaS user, I use a UI to run queries and download results.

---

## Inputs
### 1) Prompt (required)
A single natural language prompt, e.g.:
- “Large contractors in coastal regions building hotels; find procurement contacts and public emails.”
- “Developers in {region} who build luxury residential; find decision makers and contact pages.”

### 2) Filters (optional but recommended)
- **Region**: countries/territories list, continent, custom polygon, or “any country bordering {sea}”
- **Industry segments**: contractors, developers, distributors, suppliers, etc.
- **Organization size proxies**: “large”, “top firms”, “projects > X” (proxy-based)
- **Contact roles**: owner/CEO/GM/procurement/ops/project director/etc.
- **Language(s)**: to guide search and extraction
- **Source policy**: allowed/blocked domains, max crawl depth, rate limits

### 3) Seed sources (optional)
Lists of known directories, associations, tender portals, or trade org pages that are high-signal.

---

## Outputs
### 1) `leads.csv` (required)
Stable schema:

**Company**
- company_name
- company_type (contractor / developer / supplier / distributor / …)
- country_or_territory
- city (optional)
- website
- phone_public (optional)
- notes_company (optional)

**Contact**
- contact_name (optional)
- contact_title (optional)
- role_category (owner / procurement / ops / PM / sales / …)
- email_public (optional)
- contact_page_url (optional)

**Evidence + Quality**
- evidence_urls (semicolon-separated)
- evidence_snippets (short)
- confidence (0.0–1.0)
- dedupe_key (domain or normalized name)

**Approach Advice**
- recommended_angle (1–2 lines)
- recommended_first_offer (1 line)
- qualifying_question (1 line)

### 2) `report.md` (required)
A short run report:
- prompt + filters + recipe path
- run timestamp, sources fetched, domains hit
- lead counts by country and company_type
- caveats (coverage gaps, low hit-rate domains, etc.)

### 3) `leads.json` (internal)
Canonical structured representation (easier for dedupe, reruns, UI).

---

## System architecture (CLI-first)
### Components
1. **Recipe Manager**
   - Saves prompt + filters + seed sources as YAML
2. **Query Planner**
   - Expands prompt into search queries (multi-lingual if needed)
3. **Source Discovery**
   - Uses a search API + optional seed sources to get candidate URLs
4. **Fetcher**
   - Polite crawling (rate limits, retries, domain throttling)
5. **Extractor**
   - Extracts orgs/contacts/evidence from fetched content
6. **Normalizer + Dedupe**
   - Merges duplicates across sources and URLs
7. **Scorer**
   - Assigns confidence based on evidence quality
8. **Advisor**
   - Generates outreach advice based on lead attributes
9. **Exporter**
   - Writes CSV + report + JSON

### Run folder layout
```
runs/
  December_29,_2025_<slug>/
    leads.csv
    report.md
    leads.json
    sources.json
    logs.txt
recipes/
  <slug>.yml
```

---

## ChatGPT (OpenAI API) integration
### What we use ChatGPT for (MVP)
- **Extraction**: turn messy webpage text into structured lead objects.
- **Classification**: label company type, role category, and relevance.
- **Advice**: generate 2–3 outreach bullets and a qualifying question.
- **(Optional) Query planning**: expand prompt into multilingual search queries.

### Recommended API shape
Use the **Responses API** (recommended for new projects):
- **Structured Outputs** (strict JSON schema) for extraction/classification.
- **Function calling** to separate “LLM suggests” vs “system executes.”

### Key security rules
- API key is loaded from environment variable:
  - `OPENAI_API_KEY=...`
- Never commit keys, never put keys in client-side code.
- In SaaS mode: keep keys server-side; per-customer project keys later.

### “Model contract” for extraction
The extractor must output:
- `company`, `contacts[]`, `evidence[]`, `confidence`
and must fail closed (drop fields) if evidence is missing.

---

## Data policy & compliance (hard requirements)
- Collect only what is **publicly published** (official sites, public directories, PDFs posted publicly).
- Every contact channel must have **source URL(s)**.
- No login-required scraping, no paywall bypassing, no mass personal-email guessing.
- Respect rate limits and avoid hammering small sites.
- Maintain allowlist/blocklist + opt-out list.

---

## Lead quality (MVP heuristics)
### Confidence scoring (example)
- +0.40 email appears on company domain contact/team page
- +0.20 role/title matches target role categories
- +0.20 multiple sources corroborate company relevance
- +0.20 phone/contact page exists even if no email

### Dedupe keys
- Primary: domain
- Secondary: normalized company name + location

---

## Success metrics
- **Time-to-CSV**: minutes per query
- **Evidence completeness**: % leads with ≥1 valid evidence URL
- **Contact utility**: % leads with a usable contact channel (email or contact page or phone)
- **Duplicate rate**: % duplicates after dedupe
- **Operator time saved**: manual cleanup time per run

---

## Monetization (future)
- **Done-for-you**: sell CSV deliverables per client (fast cash path).
- **Pay-per-query**: metered usage + stored recipes.
- **SaaS**: team seats + history + exports + saved workflows.

---

## Risks & mitigations
- **Low email hit-rate** → treat contact pages and phones as valid; emphasize evidence.
- **Hallucinated contacts** → strict structured outputs + evidence required; otherwise drop.
- **Source fragility** → seed sources + caching; store run artifacts.
- **Scope creep (ZoomInfo trap)** → ship CLI MVP; UI and enrichment later.

---

## MVP scope (v0.1) — explicit
- CLI: `shoudao run --prompt "..."`
- Recipes: save/rerun YAML
- Search → fetch → extract → export
- Dedupe + confidence score
- Approach advice block
- Run artifacts saved to disk

---

## Changelog

### 2025-12-29 — v0.1.0 MVP Implementation
**Delta:** Initial MVP build complete.

**Built:**
- Python package structure (`src/shoudao/`)
- Data models: `Lead`, `Company`, `Contact`, `Evidence`, `ApproachAdvice` (Pydantic)
- CSV exporter with stable 20-column schema
- Search provider abstraction + Serper.dev integration
- Polite HTTP fetcher with domain throttling (1.5s delay)
- LLM extractor using OpenAI structured outputs (`gpt-4o-mini`)
- Dedupe engine (domain + normalized name)
- Confidence scoring (evidence-weighted heuristics)
- Outreach advice generator (per-lead LLM)
- CLI: `shoudao run --prompt "..."` and `shoudao check`
- Run artifacts: `leads.csv`, `leads.json`, `report.md` in `runs/<timestamp>/`

### 2025-12-29 — v0.1.1 Infrastructure + Strict Models
**Delta:** Hardened Pydantic models + test/CI infrastructure.

**Built:**
- Strict Pydantic models with `extra="forbid"` (fail fast on hallucinated fields)
- `ContactChannel` abstraction with required `Evidence` (no evidence = drop it)
- `QueryRecipe` model for reproducible runs
- Test suite: 45 tests covering models, exporter, dedupe (pytest)
- Pre-commit hooks (ruff lint/format, py_compile)
- GitHub Actions CI/CD (lint → test → build)
- `scripts/build_analysis_doc.py` → `SHOUDAO_ANALYSIS.md` (full codebase dump)
- Updated `.cursorrules` with ShouDao-specific rules

**Key model changes:**
- `Contact.channels: list[ContactChannel]` (each channel requires evidence)
- `Organization` replaces `Company` (more generic)
- `RoleCategory`, `OrgType`, `ContactChannelType` as Literal types

**Pending:**
- Configure API keys and run first real query
- Initialize git repo and push to GitHub
