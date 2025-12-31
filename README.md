# ShouDao

> 销售的售 + 导游的导 = "Sales Guide"

B2B lead generation and talent discovery tool that turns prompts into actionable CSVs.

## Quick Start

```bash
# Install
pip install -e .

# Configure API keys
cp env.example .env
# Edit .env with your OPENAI_API_KEY, SERPER_API_KEY, and optionally APIFY_API_KEY

# Check configuration
shoudao check

# Run a lead generation query
shoudao run --prompt "Large construction contractors in Florida building hotels"

# Run a talent discovery query
shoudao talent --prompt "software engineers with AI experience"

# Run talent discovery with LinkedIn
shoudao talent --linkedin --prompt "ML engineers startup experience" --max-results 25
```

## Commands

### Lead Generation
```bash
shoudao run --prompt "..."           # Generate B2B leads
shoudao recipe create --prompt "..." # Save query as recipe
shoudao recipe run <slug>            # Rerun saved recipe
```

### Talent Discovery
```bash
shoudao talent --prompt "..."                    # Web-sourced candidates
shoudao talent --linkedin --prompt "..."         # LinkedIn-sourced candidates
shoudao talent --linkedin --linkedin-mode Full   # Detailed profile scraping
```

### Outreach (Gmail Drafts)
```bash
shoudao outreach drafts --leads ./runs/XYZ/leads.json --dry-run  # Preview
shoudao outreach drafts --leads ./runs/XYZ/leads.json            # Create drafts
```

## Output

Each run creates a folder in `runs/` with:
- `leads.csv` / `candidates.csv` - Lead/candidate list
- `leads.json` / `candidates.json` - Canonical JSON format
- `leads.xlsx` / `candidates.xlsx` - Excel format
- `report.md` - Run summary

## Lead CSV Schema

| Column | Description |
|--------|-------------|
| company_name | Company name |
| company_type | contractor/developer/supplier/distributor/other |
| country_or_territory | Location |
| website | Primary domain |
| contact_name | Contact full name |
| email_public | Public email if found |
| evidence_urls | Source URLs (semicolon-separated) |
| confidence | Quality score 0-1 |
| recommended_angle | Outreach angle |
| qualifying_question | Question to qualify |

## Candidate CSV Schema

| Column | Description |
|--------|-------------|
| name | Candidate name |
| linkedin_url | LinkedIn profile |
| current_role | Job title |
| current_company | Employer |
| location | Geographic location |
| degree_signal | Education (degree, school) |
| years_experience | Estimated experience |
| tier | A/B/C fit classification |
| score | Quality score 0-1 |
| salary_band | Estimated salary range |

## Requirements

- Python 3.11+
- OpenAI API key (required)
- Serper.dev API key (for web search)
- Apify API key (for LinkedIn, optional)
- Gmail OAuth credentials (for outreach, optional)

## Gmail Outreach Setup

To use `shoudao outreach drafts`, you need Gmail API credentials:

### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Gmail API** (APIs & Services → Library → Gmail API)

### 2. Create OAuth Credentials
1. Go to APIs & Services → Credentials
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: **Desktop app**
4. Download the JSON file as `gmail_credentials.json`

### 3. First Run (OAuth Consent)
```bash
shoudao outreach drafts \
  --leads ./runs/XYZ/leads.json \
  --credentials gmail_credentials.json \
  --dry-run
```

On first run, a browser will open for OAuth consent. After approval, a `gmail_token.json` is cached for future runs.

### 4. Create Drafts
```bash
shoudao outreach drafts \
  --leads ./runs/XYZ/leads.json \
  --credentials gmail_credentials.json \
  --min-confidence 0.6 \
  --max-drafts 25
```

**Options:**
| Flag | Description |
|------|-------------|
| `--leads` | Path to leads.json file |
| `--credentials` | Path to Gmail OAuth credentials JSON |
| `--token` | Path to cached token (default: gmail_token.json) |
| `--log` | Path to outreach log CSV (default: outreach_log.csv) |
| `--min-confidence` | Minimum confidence threshold (default: 0.6) |
| `--max-drafts` | Max drafts to create (0 = no limit) |
| `--from-email` | Optional From address |
| `--dry-run` | Preview without creating drafts |

**Note:** Drafts are created in the "Drafts" folder of your Gmail. Review and send manually (HITL = Human In The Loop).

